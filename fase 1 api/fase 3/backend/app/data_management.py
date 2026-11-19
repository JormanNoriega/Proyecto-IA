"""Captura operativa independiente: las previsualizaciones nunca son entrenamiento."""
import csv
import hashlib
import io
import json
import math
import secrets
import sqlite3
import zipfile
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from .data_dictionary import PREDICTORS, META as META_DICTIONARY

MAX_BYTES = 2_000_000
MAX_ROWS = 2000
META = ["cod_mpio", "a_o", "fuente", "fecha_referencia", "consultas"]
COUNTS = {"poblacion", "n_sedes", "n_sedes_ese", "n_resguardos", "pob_resguardos", "n_comunidades"}


def register_data_routes(app, db, admin, features, source_data, predict_active, active_model, model_path, legacy_model):
    columns = META + features
    dictionary_rows = [
        {"campo": name, "descripcion": definition[0], "unidad": definition[1],
         "origen_historico": definition[2],
         "estado": "opcional; requerido para etiquetar" if name == "consultas" else "obligatorio" if name in META else "opcional; verificar equivalencia y fecha"}
        for name in columns for definition in [(META_DICTIONARY | PREDICTORS)[name]]
    ]

    def inspect(rows, con, editing_key=None):
        catalog = {r["code"]: dict(r) for r in con.execute("SELECT code,name,department_code FROM territories")}
        existing = {(r["code"], r["year"]) for r in con.execute("SELECT code,year FROM operational_records")}
        legacy = {(r["code"], r["year"]) for r in con.execute("SELECT code,year FROM records")}
        historic = source_data()
        historical = set(zip(historic.cod_mpio.astype(str), historic.a_o.astype(int)))
        seen = set()
        result = []
        for number, raw in enumerate(rows, 2):
            errors, warnings = [], []
            unknown = set(raw) - set(columns)
            if unknown:
                errors.append("Columnas desconocidas: " + ", ".join(sorted(unknown)))
            code = str(raw.get("cod_mpio") or "").strip()
            if not (len(code) == 5 and code.isascii() and code.isdigit() and code in catalog):
                errors.append("Código DIVIPOLA inválido o inexistente; use cinco dígitos como texto.")
            year_raw = str(raw.get("a_o") or "").strip()
            year = int(year_raw) if year_raw.isascii() and year_raw.isdigit() and len(year_raw) == 4 else None
            if year is None or not 1900 <= year <= 2100:
                errors.append("a_o debe ser un año entre 1900 y 2100.")
            source = str(raw.get("fuente") or "").strip()
            if not source or len(source) > 500 or source.startswith(("=", "+", "-", "@")):
                errors.append("Indique una fuente válida (máximo 500 caracteres).")
            ref = raw.get("fecha_referencia")
            ref = ref.date().isoformat() if isinstance(ref, datetime) else str(ref or "").strip()
            try:
                reference = date.fromisoformat(ref)
                if reference.year > date.today().year:
                    warnings.append("La fecha de referencia es futura; verifique si corresponde a una proyección.")
                if year and reference.year < year:
                    warnings.append("La fecha de referencia es anterior al año del registro.")
            except ValueError:
                errors.append("fecha_referencia debe tener formato AAAA-MM-DD.")
            key = (code, year)
            if key in seen:
                errors.append("Municipio y año duplicados dentro del archivo.")
            seen.add(key)
            if key in existing and key != editing_key:
                errors.append("Ya existe un registro operativo para este municipio y año; no se sobrescribirá.")
            if key in legacy:
                errors.append("Ya existe un registro adicional anterior para este municipio y año; no se sobrescribirá.")
            if key in historical:
                errors.append("Ya existe un registro histórico para este municipio y año.")
            values = {}
            raw_consultas = raw.get("consultas")
            consultas = None
            if raw_consultas is not None and str(raw_consultas).strip():
                try:
                    consultas = float(raw_consultas)
                    if not math.isfinite(consultas) or consultas < 0 or not consultas.is_integer():
                        raise ValueError()
                    consultas = int(consultas)
                except (ValueError, TypeError, OverflowError):
                    errors.append("consultas: debe ser un número entero no negativo.")
                    consultas = None
            if consultas is None:
                warnings.append("Sin consultas no se puede calcular la etiqueta de entrenamiento.")
            for name in features:
                value = raw.get(name)
                if value is None or str(value).strip() == "":
                    values[name] = None
                    continue
                try:
                    if isinstance(value, str) and value.strip().startswith(("=", "@")):
                        raise ValueError()
                    n = float(value)
                    if not math.isfinite(n):
                        raise ValueError()
                    if name.startswith(("pct_", "nbi_")) and not 0 <= n <= 100:
                        raise ValueError()
                    if name in COUNTS and (n < 0 or not n.is_integer()):
                        raise ValueError()
                    if name == "poblacion" and n <= 0:
                        raise ValueError()
                    if name == "latitud" and not -90 <= n <= 90 or name == "longitud" and not -180 <= n <= 180:
                        raise ValueError()
                    if name == "sedes_10k_hab" and n < 0:
                        raise ValueError()
                    if name == "banda_pob" and (not n.is_integer() or not 0 <= n <= 4):
                        raise ValueError()
                    values[name] = n
                except (ValueError, TypeError, OverflowError):
                    errors.append(f"{name}: valor numérico inválido.")
                    values[name] = None
            if values["n_sedes"] is not None and values["n_sedes_ese"] is not None and values["n_sedes_ese"] > values["n_sedes"]:
                errors.append("n_sedes_ese no puede superar n_sedes.")
            if values["poblacion"] and values["n_sedes"] is not None and values["sedes_10k_hab"] is not None:
                expected = values["n_sedes"] * 10000 / values["poblacion"]
                if abs(values["sedes_10k_hab"] - expected) > max(.01, expected * .01):
                    errors.append("sedes_10k_hab no coincide con n_sedes / poblacion × 10.000.")
            missing = [name for name, value in values.items() if value is None]
            if missing:
                warnings.append(f"Faltan {len(missing)} de {len(features)} predictores; no se habilita inferencia.")
            if values["banda_pob"] is not None:
                warnings.append("banda_pob es un quintil histórico nacional (0–4), no una categoría libre; revise su compatibilidad temporal.")
            name = catalog.get(code, {}).get("name", "")
            result.append({"fila": number, "cod_mpio": code, "municipio": name, "a_o": year,
                           "errores": errors, "advertencias": warnings,
                           "elegibilidad": "incompleto" if missing else "requiere_revision",
                           "data": {"cod_mpio": code, "cod_dpto": code[:2], "nom_mpio": name,
                                     "a_o": year, "fuente": source, "fecha_referencia": ref, "consultas": consultas, **values}})
        return result

    @app.get("/api/v1/data/template/{format}")
    def template(format: str, user=Depends(admin)):
        if format == "diccionario.csv":
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=list(dictionary_rows[0]))
            writer.writeheader()
            writer.writerows(dictionary_rows)
            return Response(content=("\ufeff" + output.getvalue()).encode("utf-8"), media_type="text/csv",
                            headers={"Content-Disposition": 'attachment; filename="diccionario_municipal.csv"'})
        if format == "csv":
            out = io.StringIO(newline="")
            csv.writer(out).writerow(columns)
            return Response(content=("\ufeff" + out.getvalue()).encode("utf-8"), media_type="text/csv",
                            headers={"Content-Disposition": 'attachment; filename="plantilla_municipios.csv"'})
        if format != "xlsx":
            raise HTTPException(404, "Formato no disponible.")
        wb = Workbook()
        ws = wb.active
        ws.title = "Registros"
        ws.append(columns)
        ws.freeze_panes = "B2"
        ws.column_dimensions["A"].width = 16
        for row in range(2, 1002):
            ws.cell(row, 1).number_format = "@"
        instructions = wb.create_sheet("Instrucciones")
        for line in ["Una fila por municipio y año.", "cod_mpio: cinco dígitos como texto, incluidos ceros iniciales.",
                     "fecha_referencia: AAAA-MM-DD. Indique la fuente; no use fórmulas.",
                     "Los campos vacíos se guardan incompletos. No se calculan predicciones ni se entrena automáticamente.",
                     "Revise unidades, definiciones y procedencia antes de usar para inferencia."]:
            instructions.append([line])
        instructions.column_dimensions["A"].width = 110
        dictionary = wb.create_sheet("Diccionario")
        dictionary.append(["Campo", "Descripción", "Unidad", "Origen histórico", "Estado"])
        for entry in dictionary_rows:
            dictionary.append(list(entry.values()))
        dictionary.column_dimensions["A"].width = 25
        dictionary.column_dimensions["B"].width = 75
        dictionary.column_dimensions["C"].width = 30
        dictionary.column_dimensions["D"].width = 60
        dictionary.column_dimensions["E"].width = 40
        territory = wb.create_sheet("Territorios")
        territory.append(["cod_mpio", "municipio", "departamento"])
        with db() as con:
            for row in con.execute("SELECT code,name,department FROM territories ORDER BY code"):
                territory.append(list(row))
        territory.column_dimensions["A"].width = 16
        territory.column_dimensions["B"].width = 32
        territory.column_dimensions["C"].width = 25
        output = io.BytesIO()
        wb.save(output)
        return Response(output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="plantilla_municipios.xlsx"'})

    @app.get("/api/v1/data/schema")
    def schema(user=Depends(admin)):
        return {"columns": columns, "features": features, "dictionary": dictionary_rows,
                "instructions": "Una fila por municipio y año. Código DIVIPOLA de cinco dígitos, fecha AAAA-MM-DD, fuente y predictores numéricos. Campos vacíos se guardan incompletos. No se admiten fórmulas."}

    async def make_preview(rows, user):
        if not rows:
            raise HTTPException(422, "El archivo no contiene registros.")
        if len(rows) > MAX_ROWS:
            raise HTTPException(413, f"Máximo {MAX_ROWS} filas.")
        with db() as con:
            checked = inspect(rows, con)
            token = secrets.token_urlsafe(24)
            con.execute("INSERT INTO data_previews VALUES (?,?,?,?)",
                        (token, user["id"], datetime.now(timezone.utc).isoformat(), json.dumps(rows, ensure_ascii=False, default=str)))
        return {"token": token, "rows": [{k: v for k, v in row.items() if k != "data"} for row in checked]}

    @app.post("/api/v1/data/preview")
    async def preview(file: UploadFile = File(...), user=Depends(admin)):
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "El archivo supera 2 MB.")
        filename = (file.filename or "").lower()
        try:
            if filename.endswith(".csv"):
                reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
                headers = reader.fieldnames or []
                if len(set(headers)) != len(headers) or not set(META[:4]).issubset(headers):
                    raise ValueError("Encabezados duplicados o faltan columnas obligatorias.")
                rows = []
                for row in reader:
                    if None in row:
                        raise ValueError("Una fila contiene más valores que encabezados.")
                    if any(str(v or "").strip() for v in row.values()):
                        rows.append(row)
                    if len(rows) > MAX_ROWS:
                        raise HTTPException(413, f"Máximo {MAX_ROWS} filas.")
            elif filename.endswith(".xlsx"):
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    if sum(item.file_size for item in archive.infolist()) > 30_000_000:
                        raise ValueError("El contenido descomprimido es demasiado grande.")
                wb = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
                if "Registros" not in wb.sheetnames:
                    raise ValueError("Falta la hoja Registros.")
                ws = wb["Registros"]
                if ws.max_row > MAX_ROWS + 1 or ws.max_column > len(columns):
                    raise ValueError("La hoja excede el límite de filas o columnas.")
                lines = ws.iter_rows()
                headers = [str(c.value or "").strip() for c in next(lines)]
                if len(set(headers)) != len(headers) or not set(META[:4]).issubset(headers):
                    raise ValueError("Encabezados duplicados o faltan columnas obligatorias.")
                rows = []
                for cells in lines:
                    if any(c.data_type == "f" for c in cells):
                        raise ValueError("No se permiten fórmulas.")
                    row = dict(zip(headers, (c.value for c in cells)))
                    if any(v is not None and str(v).strip() for v in row.values()):
                        rows.append(row)
                wb.close()
            else:
                raise ValueError("Seleccione un archivo .csv o .xlsx.")
        except (ValueError, UnicodeError, csv.Error, zipfile.BadZipFile, KeyError, StopIteration, OSError) as exc:
            raise HTTPException(422, f"No se pudo leer el archivo: {exc}")
        return await make_preview(rows, user)

    @app.post("/api/v1/data/preview-record")
    async def preview_record(row: dict, user=Depends(admin)):
        return await make_preview([row], user)

    @app.post("/api/v1/data/confirm/{token}")
    def confirm(token: str, user=Depends(admin)):
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            preview = con.execute("SELECT * FROM data_previews WHERE token=? AND user_id=?", (token, user["id"])).fetchone()
            if not preview:
                raise HTTPException(404, "Vista previa no encontrada o ya confirmada.")
            if datetime.fromisoformat(preview["created"]) < datetime.now(timezone.utc) - timedelta(hours=2):
                raise HTTPException(410, "La vista previa venció; vuelva a validar.")
            saved = json.loads(preview["data"])
            if not isinstance(saved, list):
                raise HTTPException(409, "Esta vista previa corresponde a una corrección.")
            checked = inspect(saved, con)
            valid = [row for row in checked if not row["errores"]]
            if not valid:
                raise HTTPException(409, "No hay filas válidas para guardar.")
            now = datetime.now(timezone.utc).isoformat()
            next_id = con.execute("SELECT MAX(value) FROM (SELECT COALESCE(MAX(id),0) AS value FROM operational_records UNION ALL SELECT COALESCE(MAX(record_id),0) FROM operational_record_deletions)").fetchone()[0] + 1
            try:
                for row in valid:
                    data = row["data"]
                    con.execute("INSERT INTO operational_records(id,code,year,data,source,reference_date,created,created_by,batch) VALUES (?,?,?,?,?,?,?,?,?)",
                                (next_id, data["cod_mpio"], data["a_o"], json.dumps(data, ensure_ascii=False),
                                  data["fuente"], data["fecha_referencia"], now, user["username"], token))
                    next_id += 1
            except sqlite3.IntegrityError:
                raise HTTPException(409, "Los registros cambiaron; vuelva a validar el archivo.")
            con.execute("DELETE FROM data_previews WHERE token=?", (token,))
        return {"guardados": len(valid), "rechazados": len(checked) - len(valid)}

    @app.get("/api/v1/data/records")
    def records(user=Depends(admin)):
        with db() as con:
            rows = con.execute("SELECT id,code,year,data,source,reference_date,created,created_by,batch FROM operational_records ORDER BY id DESC LIMIT 500").fetchall()
        return [{"id": r["id"], "code": r["code"], "year": r["year"], "source": r["source"],
                 "reference_date": r["reference_date"], "created": r["created"], "created_by": r["created_by"],
                  "batch": r["batch"], "data": json.loads(r["data"]),
                  "data_sha256": hashlib.sha256(r["data"].encode("utf-8")).hexdigest()} for r in rows]

    @app.delete("/api/v1/data/batches/{batch}")
    def delete_batch(batch: str, user=Depends(admin)):
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            rows = con.execute("SELECT * FROM operational_records WHERE batch=? ORDER BY id", (batch,)).fetchall()
            if not rows:
                raise HTTPException(404, "Lote no encontrado o ya eliminado.")
            now = datetime.now(timezone.utc).isoformat()
            con.executemany("INSERT INTO operational_record_deletions VALUES (?,?,?,?)", [
                (r["id"], json.dumps(dict(r), ensure_ascii=False), now, user["username"]) for r in rows
            ])
            con.execute("DELETE FROM operational_records WHERE batch=?", (batch,))
        return {"eliminados": len(rows)}

    @app.get("/api/v1/data/territorial-records")
    def territorial_records(department: str, year: int, user=Depends(admin)):
        if len(department) != 2 or not department.isascii() or not department.isdigit() or not 1900 <= year <= 2100:
            raise HTTPException(422, "Departamento o año inválido.")
        with db() as con:
            rows = con.execute(
                "SELECT id,code,year,data,source,reference_date,created,created_by FROM operational_records "
                "WHERE substr(code,1,2)=? AND year=? ORDER BY code", (department, year)
            ).fetchall()
        return [{"id": r["id"], "code": r["code"], "year": r["year"], "source": r["source"],
                 "reference_date": r["reference_date"], "created": r["created"],
                 "created_by": r["created_by"], "data": json.loads(r["data"])} for r in rows]

    @app.post("/api/v1/data/records/{record_id}/preview")
    def preview_correction(record_id: int, row: dict, user=Depends(admin)):
        with db() as con:
            current = con.execute("SELECT * FROM operational_records WHERE id=?", (record_id,)).fetchone()
            if not current:
                raise HTTPException(404, "Registro operativo no encontrado.")
            if str(row.get("cod_mpio", "")).strip() != current["code"] or str(row.get("a_o", "")).strip() != str(current["year"]):
                raise HTTPException(422, "No se puede cambiar el municipio ni el año de un registro.")
            checked = inspect([row], con, (current["code"], current["year"]))
            token = secrets.token_urlsafe(24)
            payload = {"record_id": record_id, "row": row, "original_hash": hashlib.sha256(current["data"].encode()).hexdigest()}
            con.execute("INSERT INTO data_previews VALUES (?,?,?,?)",
                        (token, user["id"], datetime.now(timezone.utc).isoformat(), json.dumps(payload, ensure_ascii=False)))
        return {"token": token, "rows": [{k: v for k, v in item.items() if k != "data"} for item in checked]}

    @app.post("/api/v1/data/corrections/{token}/confirm")
    def confirm_correction(token: str, user=Depends(admin)):
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            preview = con.execute("SELECT * FROM data_previews WHERE token=? AND user_id=?", (token, user["id"])).fetchone()
            if not preview:
                raise HTTPException(404, "Vista previa no encontrada o ya confirmada.")
            if datetime.fromisoformat(preview["created"]) < datetime.now(timezone.utc) - timedelta(hours=2):
                raise HTTPException(410, "La vista previa venció; vuelva a validar.")
            payload = json.loads(preview["data"])
            if not isinstance(payload, dict) or "record_id" not in payload:
                raise HTTPException(409, "Esta vista previa no corresponde a una corrección.")
            current = con.execute("SELECT * FROM operational_records WHERE id=?", (payload["record_id"],)).fetchone()
            if not current or hashlib.sha256(current["data"].encode()).hexdigest() != payload["original_hash"]:
                raise HTTPException(409, "El registro cambió desde la revisión; vuelva a validar.")
            checked = inspect([payload["row"]], con, (current["code"], current["year"]))[0]
            if checked["errores"]:
                raise HTTPException(409, "La corrección ya no es válida: " + " ".join(checked["errores"]))
            now = datetime.now(timezone.utc).isoformat()
            if not con.execute("SELECT 1 FROM operational_record_revisions WHERE record_id=?", (current["id"],)).fetchone():
                con.execute("INSERT INTO operational_record_revisions(record_id,data,changed_at,changed_by,action) VALUES (?,?,?,?,?)",
                            (current["id"], current["data"], current["created"], current["created_by"], "registro inicial"))
            data = checked["data"]
            serialized = json.dumps(data, ensure_ascii=False)
            con.execute("INSERT INTO operational_record_revisions(record_id,data,changed_at,changed_by,action) VALUES (?,?,?,?,?)",
                        (current["id"], serialized, now, user["username"], "corrección"))
            con.execute("UPDATE operational_records SET data=?,source=?,reference_date=? WHERE id=?",
                        (serialized, data["fuente"], data["fecha_referencia"], current["id"]))
            con.execute("DELETE FROM data_previews WHERE token=?", (token,))
        return {"ok": True}

    @app.get("/api/v1/data/records/{record_id}/history")
    def record_history(record_id: int, user=Depends(admin)):
        with db() as con:
            record = con.execute("SELECT * FROM operational_records WHERE id=?", (record_id,)).fetchone()
            if not record:
                raise HTTPException(404, "Registro operativo no encontrado.")
            revisions = con.execute("SELECT data,changed_at,changed_by,action FROM operational_record_revisions WHERE record_id=? ORDER BY id", (record_id,)).fetchall()
        if not revisions:
            return [{"data": json.loads(record["data"]), "changed_at": record["created"], "changed_by": record["created_by"], "action": "registro inicial"}]
        return [{**dict(r), "data": json.loads(r["data"])} for r in revisions]

    @app.post("/api/v1/data/records/{record_id}/exploratory-prediction")
    def exploratory_prediction(record_id: int, user=Depends(admin)):
        with db() as con:
            current = con.execute("SELECT * FROM operational_records WHERE id=?", (record_id,)).fetchone()
        if not current:
            raise HTTPException(404, "Registro operativo no encontrado.")
        data = json.loads(current["data"])
        missing = [field for field in features if data.get(field) is None]
        if missing:
            raise HTTPException(422, "Faltan predictores: " + ", ".join(missing))
        model_id = active_model()
        path = model_path(model_id) if model_id is not None else legacy_model
        try:
            model_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            raise HTTPException(503, "No se encontró el archivo del modelo activo.")
        probability, model, model_warning = predict_active(pd.DataFrame([data], columns=features))
        score = float(probability[0])
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise HTTPException(503, "El modelo devolvió una probabilidad inválida.")
        if active_model() != model_id:
            raise HTTPException(409, "El modelo cambió durante el cálculo; inténtelo de nuevo.")
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != model_hash:
                raise HTTPException(409, "El archivo del modelo cambió durante el cálculo.")
        except OSError:
            raise HTTPException(503, "No se pudo verificar el modelo.")
        warning = ("Prueba exploratoria, no validada temporalmente ni apta para decisiones sanitarias. "
                   "La integridad de los 27 campos no demuestra que sean comparables al entrenamiento; "
                   "verifique fuentes y fechas por indicador. " + model_warning)
        now = datetime.now(timezone.utc).isoformat()
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            fresh = con.execute("SELECT data FROM operational_records WHERE id=?", (record_id,)).fetchone()
            if not fresh or fresh["data"] != current["data"]:
                raise HTTPException(409, "El registro cambió durante el cálculo; inténtelo de nuevo.")
            result = con.execute(
                "INSERT INTO exploratory_predictions(record_id,created,created_by,data,model,model_sha256,probability,warning) VALUES (?,?,?,?,?,?,?,?)",
                (record_id, now, user["username"], current["data"], model, model_hash, score, warning))
        return {"id": result.lastrowid, "created": now, "created_by": user["username"], "data": data,
                "model": model, "model_sha256": model_hash, "probability": score, "warning": warning}

    @app.get("/api/v1/data/records/{record_id}/exploratory-predictions")
    def exploratory_predictions(record_id: int, user=Depends(admin)):
        with db() as con:
            if not con.execute("SELECT 1 FROM operational_records WHERE id=?", (record_id,)).fetchone():
                raise HTTPException(404, "Registro operativo no encontrado.")
            rows = con.execute("SELECT * FROM exploratory_predictions WHERE record_id=? ORDER BY id DESC LIMIT 50", (record_id,)).fetchall()
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]
