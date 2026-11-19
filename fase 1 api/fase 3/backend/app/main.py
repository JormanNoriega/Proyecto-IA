"""API local de apoyo territorial. No sustituye una evaluación sanitaria."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import secrets
import sqlite3
import threading
import time
import httpx
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from scipy.optimize import Bounds, LinearConstraint, milp
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from . import geography

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT.parent
STORAGE = Path(os.environ.get("BRIGADAS_STORAGE", ROOT / "storage"))
DB = STORAGE / "database" / "brigadas.sqlite3"
DATASET = PROJECT / "data" / "modelo" / "municipio_anio.csv"
TERRITORY_SOURCE = PROJECT / "data" / "processed" / "dim_municipio.csv"
LEGACY_MODEL = PROJECT / "fase 2" / "modelos" / "modelo_gradient_boosting.joblib"
FEATURES = [
    "latitud", "longitud", "poblacion", "pct_rural_disperso", "banda_pob",
    "nbi_total", "nbi_miseria", "nbi_vivienda", "nbi_servicios", "nbi_hacinamiento",
    "nbi_inasistencia", "nbi_dependencia", "nbi_rural", "nbi_rural_miseria",
    "nbi_rural_servicios", "nbi_rural_hacinamiento", "n_sedes", "n_sedes_ese",
    "sedes_10k_hab", "n_resguardos", "pob_resguardos", "n_comunidades",
    "pct_cap_O", "pct_cap_A", "pct_cap_J", "pct_cap_K", "pct_cap_Z",
]

app = FastAPI(title="Territorio Salud API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def check_origin(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in {"http://localhost:5173", "http://127.0.0.1:5173"}:
            return Response(status_code=403, content="Origen no permitido")
    return await call_next(request)


@contextmanager
def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def initialize():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, code TEXT NOT NULL, year INTEGER NOT NULL, data TEXT NOT NULL, UNIQUE(code,year));
        CREATE TABLE IF NOT EXISTS operational_records (id INTEGER PRIMARY KEY, code TEXT NOT NULL, year INTEGER NOT NULL, data TEXT NOT NULL, source TEXT NOT NULL, reference_date TEXT NOT NULL, created TEXT NOT NULL, created_by TEXT NOT NULL, batch TEXT NOT NULL, UNIQUE(code,year));
        CREATE TABLE IF NOT EXISTS operational_record_revisions (id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL, data TEXT NOT NULL, changed_at TEXT NOT NULL, changed_by TEXT NOT NULL, action TEXT NOT NULL, FOREIGN KEY(record_id) REFERENCES operational_records(id));
        CREATE TABLE IF NOT EXISTS exploratory_predictions (id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL, created TEXT NOT NULL, created_by TEXT NOT NULL, data TEXT NOT NULL, model TEXT NOT NULL, model_sha256 TEXT NOT NULL, probability REAL NOT NULL, warning TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS data_previews (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, created TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dataset_versions (id INTEGER PRIMARY KEY, created TEXT NOT NULL, author TEXT NOT NULL, records INTEGER NOT NULL, checksum TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dataset_operational_inputs (dataset_id INTEGER NOT NULL, record_id INTEGER NOT NULL, record_sha256 TEXT NOT NULL, label INTEGER NOT NULL, label_source TEXT NOT NULL, record_data TEXT NOT NULL, PRIMARY KEY(dataset_id,record_id));
        CREATE TABLE IF NOT EXISTS experiments (id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL, created TEXT NOT NULL, author TEXT NOT NULL, status TEXT NOT NULL, info TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS territories (code TEXT PRIMARY KEY, department_code TEXT NOT NULL, department TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS territory_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS journey_drafts (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created TEXT NOT NULL, data TEXT NOT NULL, saved_plan_id INTEGER);
        CREATE TABLE IF NOT EXISTS bases (id INTEGER PRIMARY KEY, name TEXT NOT NULL, municipality_code TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL, coordinate_source TEXT NOT NULL, created TEXT NOT NULL, created_by TEXT NOT NULL, FOREIGN KEY(municipality_code) REFERENCES territories(code));
        """)
        existing_columns = {row["name"] for row in con.execute("PRAGMA table_info(bases)")}
        for column in ("nit", "address", "phone", "contact_name"):
            if column not in existing_columns:
                con.execute(f"ALTER TABLE bases ADD COLUMN {column} TEXT")
        for column in ("geo_status", "geo_version", "geo_validated_at"):
            if column not in existing_columns:
                con.execute(f"ALTER TABLE bases ADD COLUMN {column} TEXT")
        con.execute("UPDATE experiments SET status='interrumpido' WHERE status IN ('pendiente','ejecutando')")
        if not con.execute("SELECT 1 FROM territories LIMIT 1").fetchone() and TERRITORY_SOURCE.exists():
            raw = TERRITORY_SOURCE.read_bytes()
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
            entries = []
            for row in rows:
                code, dept = row["cod_mpio"].strip(), row["cod_dpto"].strip()
                if len(code) != 5 or not code.isdigit() or len(dept) != 2 or not dept.isdigit() or not code.startswith(dept):
                    raise ValueError("El catálogo territorial contiene códigos inválidos.")
                entries.append((code, dept, row["dpto"].strip(), row["nom_mpio"].strip(), row["tipo_municipio"].strip()))
            if not entries:
                raise ValueError("El catálogo territorial está vacío.")
            con.executemany("INSERT INTO territories VALUES (?,?,?,?,?)", entries)
            metadata = {
                "source": "DANE, DIVIPOLA gdxc-w37w; copia procesada en fase 1",
                "url": "https://www.datos.gov.co/d/gdxc-w37w",
                "license": "CC BY-SA 4.0",
                "cutoff": "No verificado para esta copia local",
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            con.executemany("INSERT INTO territory_metadata VALUES (?,?)", metadata.items())


initialize()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        return secrets.compare_digest(password_hash(password, stored.split("$")[0]), stored)
    except (ValueError, IndexError):
        return False


def current_user(session: str | None = Cookie(default=None)):
    if not session:
        raise HTTPException(401, "Inicia sesión para continuar.")
    digest = hashlib.sha256(session.encode()).hexdigest()
    with db() as con:
        user = con.execute("SELECT users.id,username,role FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?", (digest, datetime.now(timezone.utc).isoformat())).fetchone()
    if not user:
        raise HTTPException(401, "La sesión ha vencido.")
    return dict(user)


def admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Esta acción requiere perfil administrador.")
    return user


class Login(BaseModel):
    username: str
    password: str


class UserCreate(Login):
    role: str = Field(pattern="^(admin|operador)$")


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/login")
def login(body: Login, response: Response):
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE username=?", (body.username.strip(),)).fetchone()
        if not user or not verify_password(body.password, user["password"]):
            raise HTTPException(401, "Usuario o contraseña incorrectos.")
        token = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sessions VALUES (?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()))
    response.set_cookie("session", token, httponly=True, samesite="strict", max_age=43200)
    return {"username": user["username"], "role": user["role"]}


@app.post("/api/v1/auth/logout")
def logout(response: Response, session: str | None = Cookie(default=None)):
    if session:
        with db() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(session.encode()).hexdigest(),))
    response.delete_cookie("session")
    return {"ok": True}


@app.get("/api/v1/auth/me")
def me(user=Depends(current_user)):
    return user


@app.post("/api/v1/users")
def create_user(body: UserCreate, user=Depends(admin)):
    if len(body.username.strip()) < 3 or len(body.password) < 10:
        raise HTTPException(422, "El usuario requiere 3 caracteres y la contraseña al menos 10.")
    try:
        with db() as con:
            con.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)", (body.username.strip(), password_hash(body.password), body.role))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "El usuario ya existe.")
    return {"ok": True}


def source_data():
    if not DATASET.exists():
        raise HTTPException(503, "No se encontró el dataset de la fase 1.")
    return pd.read_csv(DATASET, dtype={"cod_mpio": str, "cod_dpto": str}, low_memory=False)


def safe(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def version_path(version_id: int):
    return STORAGE / "datasets" / f"dataset_{version_id}.csv"


def model_path(experiment_id: int):
    return STORAGE / "models" / f"model_{experiment_id}.joblib"


def active_model():
    with db() as con:
        setting = con.execute("SELECT value FROM settings WHERE key='active_model'").fetchone()
    return int(setting["value"]) if setting else None


def operational_data():
    model_id = active_model()
    if model_id is None:
        return source_data()
    with db() as con:
        exp = con.execute("SELECT dataset_id FROM experiments WHERE id=?", (model_id,)).fetchone()
    if not exp or not version_path(exp["dataset_id"]).exists():
        raise HTTPException(503, "No se encontró el dataset del modelo publicado.")
    return load_version(exp["dataset_id"])


def predict_active(df):
    model_id = active_model()
    if model_id is None:
        return legacy_predictions(df), "HistGradientBoosting · fase 2", "Modelo heredado: faltantes reemplazados por cero; probabilidades no calibradas."
    try:
        model = joblib.load(model_path(model_id))
        values = df.reindex(columns=FEATURES).apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
        return model.predict_proba(values)[:, 1], f"Experimento #{model_id}", "Probabilidades no calibradas; las etiquetas históricas pueden contener contaminación por construcción previa."
    except Exception:
        raise HTTPException(503, "No se pudo cargar el modelo publicado.")


def legacy_predictions(df):
    if not LEGACY_MODEL.exists():
        raise HTTPException(503, "No se encontró el modelo heredado.")
    try:
        model = joblib.load(LEGACY_MODEL)
        # La fase 2 usó cero en su demo de inferencia; no es el pipeline de entrenamiento.
        x = df.reindex(columns=FEATURES).apply(pd.to_numeric, errors="coerce").fillna(0)
        return model.predict_proba(x)[:, 1]
    except Exception as exc:
        raise HTTPException(503, f"No se pudo cargar el modelo heredado; verifica la versión de scikit-learn. {exc}")


@app.get("/api/v1/priorities")
def priorities(department: str = "20", year: int = 2021, user=Depends(current_user)):
    df = operational_data()
    df = df[(df.cod_dpto == department.zfill(2)) & (df.a_o == year)].copy()
    # Incomplete imported rows remain available in the snapshot but do not
    # receive a misleading score based almost entirely on imputed values.
    if active_model() is not None:
        inputs = df.reindex(columns=FEATURES).apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
        df = df[inputs.notna().sum(axis=1) >= 20].copy()
    if df.empty:
        return {"items": [], "model": "Fase 2 · heredado"}
    probabilities, model, warning = predict_active(df)
    df["probability"] = probabilities
    cols = ["cod_mpio", "cod_dpto", "nom_mpio", "a_o", "latitud", "longitud", "poblacion", "pct_rural_disperso", "nbi_rural", "n_resguardos", "pob_resguardos", "es_hub", "probability"]
    items = [{k: safe(v) for k, v in row.items()} for row in df[cols].sort_values("probability", ascending=False).to_dict("records")]
    return {"items": items, "model": model, "warning": warning}

@app.get("/api/v1/operational-priorities")
def operational_priorities(department: str, year: int, user=Depends(current_user)):
    if len(department) != 2 or not department.isascii() or not department.isdigit() or not 1900 <= year <= 2100:
        raise HTTPException(422, "Departamento o año inválido.")
    with db() as con:
        rows = con.execute("SELECT * FROM operational_records WHERE substr(code,1,2)=? AND year=? ORDER BY code", (department, year)).fetchall()
    valid = []
    for row in rows:
        data = json.loads(row["data"])
        if all(isinstance(data.get(f), (int, float)) and not isinstance(data.get(f), bool) and math.isfinite(data[f]) for f in FEATURES):
            valid.append((row, data))
    warning = ("Estimación exploratoria con datos declarados, no validada temporalmente; "
               "verifique los resultados antes de cualquier decisión. Probabilidades no calibradas.")
    if not valid:
        return {"items": [], "model": None, "warning": warning, "source": "operativo", "incomplete": len(rows)}
    model_id = active_model()
    path = model_path(model_id) if model_id is not None else LEGACY_MODEL
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise HTTPException(503, "No se encontró el archivo del modelo activo.")
    probabilities, model, model_warning = predict_active(pd.DataFrame([data for _, data in valid], columns=FEATURES))
    try:
        if active_model() != model_id or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise HTTPException(409, "El modelo cambió durante la consulta; inténtelo de nuevo.")
    except OSError:
        raise HTTPException(503, "No se pudo verificar el modelo activo.")
    items = []
    for (row, data), probability in zip(valid, probabilities):
        score = float(probability)
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise HTTPException(503, "El modelo devolvió una probabilidad inválida.")
        items.append({**data, "es_hub": None, "probability": score, "operational_record_id": row["id"],
                      "record_sha256": hashlib.sha256(row["data"].encode("utf-8")).hexdigest()})
    items.sort(key=lambda item: item["probability"], reverse=True)
    return {"items": items, "model": model, "model_sha256": digest, "warning": warning + " " + model_warning,
            "source": "operativo", "incomplete": len(rows)-len(valid)}


@app.get("/api/v1/operational-catalog")
def operational_catalog(user=Depends(current_user)):
    with db() as con:
        rows = con.execute("SELECT DISTINCT substr(code,1,2) AS department,year FROM operational_records ORDER BY year DESC").fetchall()
    return {"departments": sorted({row["department"] for row in rows}), "years": sorted({row["year"] for row in rows}, reverse=True)}


@app.get("/api/v1/catalog")
def catalog(user=Depends(current_user)):
    df = operational_data()
    return {"departments": sorted(df.cod_dpto.dropna().unique().tolist()), "years": sorted(df.a_o.dropna().astype(int).unique().tolist(), reverse=True)}


@app.get("/api/v1/territories")
def territories(department: str | None = None, user=Depends(current_user)):
    with db() as con:
        metadata = dict(con.execute("SELECT key,value FROM territory_metadata").fetchall())
        departments = [dict(r) for r in con.execute("SELECT department_code AS code, department AS name FROM territories GROUP BY department_code, department ORDER BY department")]
        if not departments:
            raise HTTPException(503, "No está disponible la copia local del catálogo territorial.")
        items = []
        if department is not None:
            if len(department) != 2 or not department.isdigit():
                raise HTTPException(422, "El código de departamento debe tener dos dígitos.")
            items = [dict(r) for r in con.execute("SELECT code,name,kind FROM territories WHERE department_code=? ORDER BY name", (department,))]
    return {"departments": departments, "items": items, "metadata": metadata}


class BaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    municipality_code: str = Field(pattern=r"^\d{5}$")
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    coordinate_source: str = Field(min_length=1, max_length=200)
    coordinates_confirmed: bool
    nit: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    contact_name: str | None = Field(default=None, max_length=160)


class LocationCheck(BaseModel):
    municipality_code: str = Field(pattern=r"^\d{5}$")
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


@app.get("/api/v1/geography/departments/{code}")
def department_outline(code: str, user=Depends(current_user)):
    if len(code) != 2 or not code.isdigit():
        raise HTTPException(422, "Código de departamento inválido.")
    feature = geography.outline(code)
    if feature is None:
        raise HTTPException(404, "Contorno departamental no disponible.")
    return feature


@app.get("/api/v1/geography/municipalities/{code}")
def municipality_outline(code: str, user=Depends(current_user)):
    if len(code) != 5 or not code.isdigit():
        raise HTTPException(422, "Código de municipio inválido.")
    feature = geography.municipality_outline(code)
    if feature is None:
        raise HTTPException(404, "Contorno municipal no disponible.")
    return feature


@app.get("/api/v1/geography/departments/{code}/municipalities")
def department_municipalities(code: str, user=Depends(current_user)):
    if len(code) != 2 or not code.isdigit():
        raise HTTPException(422, "Código de departamento inválido.")
    with db() as con:
        territories = [dict(row) for row in con.execute(
            "SELECT code,name FROM territories WHERE department_code=? ORDER BY name", (code,))]
    if not territories or not geography.source_verified():
        raise HTTPException(404, "Geometrías municipales no disponibles.")
    outlines = geography.municipality_outlines(tuple(territory["code"] for territory in territories))
    if outlines is None:
        raise HTTPException(503, "No están disponibles todas las geometrías municipales del departamento.")
    features = [{**outlines[t["code"]], "properties": {"code": t["code"], "name": t["name"]}}
                for t in territories]
    return {"type": "FeatureCollection", "features": features}


@app.post("/api/v1/geography/validate")
def validate_location(body: LocationCheck, user=Depends(current_user)):
    with db() as con:
        if not con.execute("SELECT 1 FROM territories WHERE code=?", (body.municipality_code,)).fetchone():
            raise HTTPException(422, "El municipio no existe en el catálogo territorial local.")
    return geography.validate(body.municipality_code, body.latitude, body.longitude)


@app.get("/api/v1/bases")
def list_bases(user=Depends(current_user)):
    with db() as con:
        bases = [dict(row) for row in con.execute("""SELECT bases.*, territories.name AS municipality,
            territories.department_code, territories.department FROM bases
            JOIN territories ON territories.code=bases.municipality_code ORDER BY bases.name, bases.id""")]
    for base in bases:
        if not base["geo_status"]:
            check = geography.validate(base["municipality_code"], base["latitude"], base["longitude"])
            base["geo_status"] = "PENDIENTE_REVISION"
            base["geo_review"] = check
    return bases


@app.post("/api/v1/bases")
def create_base(body: BaseCreate, user=Depends(current_user)):
    name, source = body.name.strip(), body.coordinate_source.strip()
    if not name or not source or not body.coordinates_confirmed:
        raise HTTPException(422, "Indica nombre y fuente, y confirma las coordenadas de la base.")
    with db() as con:
        if not con.execute("SELECT 1 FROM territories WHERE code=?", (body.municipality_code,)).fetchone():
            raise HTTPException(422, "El municipio no existe en el catálogo territorial local.")
        validation = geography.validate(body.municipality_code, body.latitude, body.longitude)
        if validation["status"] != "VALIDADA":
            raise HTTPException(422, validation["message"])
        optional = [(getattr(body, key) or "").strip() or None for key in ("nit", "address", "phone", "contact_name")]
        now = datetime.now(timezone.utc).isoformat()
        cur = con.execute("INSERT INTO bases(name,municipality_code,latitude,longitude,coordinate_source,created,created_by,nit,address,phone,contact_name,geo_status,geo_version,geo_validated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (name, body.municipality_code, body.latitude, body.longitude, source, now, user["username"], *optional, validation["status"], validation["version"], now))
        return {"id": cur.lastrowid}


@app.get("/api/v1/statistics")
def statistics(user=Depends(admin)):
    df = source_data()
    with db() as con:
        added = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    return {"records": len(df), "municipalities": int(df.cod_mpio.nunique()), "years": int(df.a_o.nunique()), "missing_percent": round(float(df.isna().mean().mean() * 100), 2), "added_records": added, "population_median": safe(df.poblacion.median()), "rural_median": safe(df.pct_rural_disperso.median())}


def validate_record(row):
    errors = []
    code = str(row.get("cod_mpio", "")).strip()
    if not (len(code) == 5 and code.isdigit()):
        errors.append("cod_mpio debe tener cinco dígitos.")
    try:
        year = int(row.get("a_o", ""))
        if not 1900 <= year <= 2100:
            raise ValueError()
    except (ValueError, TypeError):
        year = None
        errors.append("a_o debe ser un año válido.")
    try:
        if float(row.get("poblacion", "")) <= 0 or not math.isfinite(float(row.get("poblacion", ""))):
            raise ValueError()
    except (ValueError, TypeError):
        errors.append("poblacion debe ser un número positivo.")
    if not str(row.get("nom_mpio", "")).strip():
        errors.append("nom_mpio es obligatorio.")
    for name in FEATURES + ["prioridad_alta", "es_hub"]:
        value = row.get(name)
        if value is None or value == "":
            continue
        try:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError()
            if name.startswith(("pct_", "nbi_")) and not 0 <= number <= 100:
                raise ValueError()
            if name in ("prioridad_alta", "es_hub") and number not in (0, 1):
                raise ValueError()
            if name in ("n_sedes", "n_sedes_ese", "n_resguardos", "pob_resguardos", "n_comunidades") and (number < 0 or not number.is_integer()):
                raise ValueError()
            if name == "latitud" and not -90 <= number <= 90:
                raise ValueError()
            if name == "longitud" and not -180 <= number <= 180:
                raise ValueError()
        except (ValueError, TypeError):
            errors.append(f"{name} contiene un valor inválido.")
    return code, year, errors


from .data_management import register_data_routes
register_data_routes(app, db, admin, FEATURES, source_data, predict_active, active_model, model_path, LEGACY_MODEL)


@app.post("/api/v1/records")
def add_record(row: dict, user=Depends(admin)):
    code, year, errors = validate_record(row)
    if errors:
        raise HTTPException(422, errors)
    try:
        with db() as con:
            con.execute("INSERT INTO records(code,year,data) VALUES(?,?,?)", (code, year, json.dumps(row, ensure_ascii=False)))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "El registro municipio-año ya existe en los datos importados.")
    return {"ok": True, "message": "Guardado en registros adicionales; no modifica el dataset histórico ni el modelo."}


@app.post("/api/v1/imports")
async def import_csv(file: UploadFile = File(...), user=Depends(admin)):
    content = await file.read(2_000_001)
    if len(content) > 2_000_000:
        raise HTTPException(413, "El archivo supera 2 MB.")
    try:
        text = content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
    except (UnicodeDecodeError, csv.Error):
        raise HTTPException(422, "Usa un CSV UTF-8 válido.")
    if len(rows) > 10000:
        raise HTTPException(413, "Máximo 10.000 filas.")
    accepted, rejected = 0, []
    with db() as con:
        for index, row in enumerate(rows, 2):
            code, year, errors = validate_record(row)
            if not errors:
                try:
                    con.execute("INSERT INTO records(code,year,data) VALUES(?,?,?)", (code, year, json.dumps(row, ensure_ascii=False)))
                    accepted += 1
                except sqlite3.IntegrityError:
                    errors.append("Municipio-año duplicado entre registros adicionales.")
            if errors:
                rejected.append({"fila": index, "errores": errors})
    return {"accepted": accepted, "rejected": rejected, "notice": "Los registros se guardaron por separado. No modifican el modelo ni el dataset histórico."}


@app.get("/api/v1/dataset-versions")
def list_versions(user=Depends(admin)):
    with db() as con:
        return [dict(r) for r in con.execute("SELECT v.*, (SELECT COUNT(*) FROM dataset_operational_inputs i WHERE i.dataset_id=v.id) AS operational_count FROM dataset_versions v ORDER BY v.id DESC").fetchall()]

class TrainingInput(BaseModel):
    record_id: int = Field(gt=0)
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    label: Literal[0, 1]
    label_source: str = Field(min_length=1, max_length=500)


class DatasetCreate(BaseModel):
    operational_inputs: list[TrainingInput] = Field(default_factory=list, max_length=2000)

@app.post("/api/v1/dataset-versions")
def create_version(body: DatasetCreate = DatasetCreate(), user=Depends(admin)):
    historical = source_data()
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        rows = con.execute("SELECT data FROM records ORDER BY id").fetchall()
        selected = []
        seen = set()
        for item in body.operational_inputs:
            if item.record_id in seen:
                raise HTTPException(422, "No seleccione el mismo registro dos veces.")
            seen.add(item.record_id)
            row = con.execute("SELECT * FROM operational_records WHERE id=?", (item.record_id,)).fetchone()
            if not row or hashlib.sha256(row["data"].encode("utf-8")).hexdigest() != item.data_sha256:
                raise HTTPException(409, "Un registro seleccionado cambió o ya no existe; actualice la lista.")
            label_source = item.label_source.strip()
            if not label_source:
                raise HTTPException(422, "Indique el origen de cada etiqueta.")
            data = json.loads(row["data"])
            if any(not isinstance(data.get(f), (int, float)) or isinstance(data.get(f), bool) or not math.isfinite(data[f]) for f in FEATURES):
                raise HTTPException(422, f"El registro {row['code']} · {row['year']} necesita los 27 predictores.")
            # Training excludes hubs. Use the existing historical classification rather
            # than silently inventing a classification for newly captured rows.
            hub = historical[historical["cod_mpio"].astype(str) == row["code"]]["es_hub"].dropna()
            if hub.empty or not (pd.to_numeric(hub, errors="coerce") == 0).all():
                raise HTTPException(422, f"El municipio {row['code']} es hub o no tiene clasificación histórica inequívoca; el entrenamiento actual lo excluye.")
            selected.append((row, item, label_source, {**data, "prioridad_alta": item.label, "es_hub": 0}))
    added = pd.DataFrame([json.loads(row["data"]) for row in rows])
    if selected:
        added = pd.concat([added, pd.DataFrame([entry[3] for entry in selected])], ignore_index=True)
    if not added.empty:
        known = set(zip(historical["cod_mpio"], historical["a_o"].astype(int)))
        duplicates = [(str(r["cod_mpio"]), int(r["a_o"])) for _, r in added.iterrows() if (str(r["cod_mpio"]), int(r["a_o"])) in known]
        if added.duplicated(subset=["cod_mpio", "a_o"]).any():
            raise HTTPException(409, "Hay registros adicionales duplicados para municipio y año.")
        if duplicates:
            raise HTTPException(409, f"Los registros adicionales duplican datos históricos: {duplicates[:5]}. No se creó la versión.")
        # Preserve the authoritative historical schema. A partial row is useful for
        # exploration but is not automatically eligible for supervised training.
        added["cod_dpto"] = added["cod_mpio"].astype(str).str[:2]
        combined = pd.concat([historical, added.reindex(columns=historical.columns)], ignore_index=True)
    else:
        combined = historical
    contents = combined.to_csv(index=False).encode("utf-8")
    checksum = hashlib.sha256(contents).hexdigest()
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        for row, item, _, _ in selected:
            fresh = con.execute("SELECT data FROM operational_records WHERE id=?", (item.record_id,)).fetchone()
            if not fresh or hashlib.sha256(fresh["data"].encode("utf-8")).hexdigest() != item.data_sha256:
                raise HTTPException(409, "Un registro seleccionado cambió; actualice la lista.")
        cur = con.execute("INSERT INTO dataset_versions(created,author,records,checksum) VALUES(?,?,?,?)", (datetime.now(timezone.utc).isoformat(), user["username"], len(combined), checksum))
        version_id = cur.lastrowid
        for row, item, label_source, _ in selected:
            con.execute("INSERT INTO dataset_operational_inputs VALUES(?,?,?,?,?,?)", (version_id, item.record_id, item.data_sha256, item.label, label_source, row["data"]))
        path = version_path(version_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    return {"id": version_id, "records": len(combined), "checksum": checksum, "operational_count": len(selected)}


@app.get("/api/v1/dataset-versions/{version_id}/operational-inputs")
def version_operational_inputs(version_id: int, user=Depends(admin)):
    with db() as con:
        if not con.execute("SELECT 1 FROM dataset_versions WHERE id=?", (version_id,)).fetchone():
            raise HTTPException(404, "No se encontró la versión del dataset.")
        rows = con.execute("SELECT * FROM dataset_operational_inputs WHERE dataset_id=? ORDER BY record_id", (version_id,)).fetchall()
    return [{**dict(row), "record_data": json.loads(row["record_data"])} for row in rows]


def load_version(version_id):
    with db() as con:
        row = con.execute("SELECT * FROM dataset_versions WHERE id=?", (version_id,)).fetchone()
    if not row or not version_path(version_id).exists():
        raise HTTPException(404, "No se encontró la versión del dataset.")
    data = version_path(version_id).read_bytes()
    if hashlib.sha256(data).hexdigest() != row["checksum"]:
        raise HTTPException(409, "El dataset no coincide con su checksum; no se puede utilizar.")
    return pd.read_csv(io.BytesIO(data), dtype={"cod_mpio": str, "cod_dpto": str}, low_memory=False)


def metrics(y, probabilities):
    pred = (probabilities >= .5).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, probabilities)), 4) if len(np.unique(y)) == 2 else None,
        "pr_auc": round(float(average_precision_score(y, probabilities)), 4) if len(np.unique(y)) == 2 else None,
        "matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
        "rows": len(y),
    }


def update_experiment(experiment_id, status, info):
    with db() as con:
        con.execute("UPDATE experiments SET status=?, info=? WHERE id=?", (status, json.dumps(info, ensure_ascii=False), experiment_id))


def train_experiment(experiment_id, dataset_id):
    try:
        update_experiment(experiment_id, "ejecutando", {})
        df = load_version(dataset_id)
        for column in FEATURES + ["prioridad_alta", "es_hub"]:
            df[column] = pd.to_numeric(df[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
        # Do not turn unlabelled/partial imports into fabricated training examples.
        eligible = df[df["prioridad_alta"].isin([0, 1]) & (df["es_hub"] == 0) & df["cod_mpio"].notna()].copy()
        eligible = eligible[eligible[FEATURES].notna().sum(axis=1) >= 20].copy()
        if eligible["cod_mpio"].nunique() < 20 or eligible["prioridad_alta"].nunique() < 2:
            raise ValueError("Se necesitan al menos 20 municipios elegibles y ambas clases.")
        groups = eligible.groupby("cod_mpio")["prioridad_alta"].max()
        train_groups, remaining = train_test_split(groups.index.to_numpy(), test_size=.30, random_state=42, stratify=groups.to_numpy())
        val_groups, test_groups = train_test_split(remaining, test_size=.50, random_state=42, stratify=groups.loc[remaining].to_numpy())
        splits = {"train": eligible[eligible.cod_mpio.isin(train_groups)], "val": eligible[eligible.cod_mpio.isin(val_groups)], "test": eligible[eligible.cod_mpio.isin(test_groups)]}
        for name, subset in splits.items():
            if subset["prioridad_alta"].nunique() != 2:
                raise ValueError(f"El conjunto {name} no contiene ambas clases.")
        train, val = splits["train"], splits["val"]
        candidates = {
            "HistGradientBoosting": Pipeline([("imputer", SimpleImputer(strategy="median", keep_empty_features=True)), ("classifier", HistGradientBoostingClassifier(random_state=42))]),
            "Baseline": Pipeline([("imputer", SimpleImputer(strategy="median", keep_empty_features=True)), ("classifier", DummyClassifier(strategy="prior"))]),
        }
        scores = {}
        for name, pipeline in candidates.items():
            pipeline.fit(train[FEATURES], train["prioridad_alta"].astype(int))
            scores[name] = metrics(val["prioridad_alta"].astype(int), pipeline.predict_proba(val[FEATURES])[:, 1])
        # Fixed candidate and threshold, selected before seeing test results.
        selected = max(scores, key=lambda name: scores[name]["f1"])
        path = model_path(experiment_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(candidates[selected], path)
        info = {"selected": selected, "threshold": .5, "seed": 42, "split": {name: {"records": len(part), "municipalities": int(part.cod_mpio.nunique())} for name, part in splits.items()}, "validation": scores, "test": None, "test_codes": sorted(map(str, test_groups)), "warning": "Las etiquetas históricas fueron calculadas antes de la partición; la evaluación puede contener contaminación y no es una prueba ciega rigurosa."}
        update_experiment(experiment_id, "completado", info)
    except Exception as exc:
        update_experiment(experiment_id, "fallido", {"error": str(exc)})


class ExperimentCreate(BaseModel):
    dataset_id: int


@app.post("/api/v1/experiments", status_code=202)
def create_experiment(body: ExperimentCreate, user=Depends(admin)):
    load_version(body.dataset_id)
    with db() as con:
        if con.execute("SELECT 1 FROM experiments WHERE status IN ('pendiente','ejecutando')").fetchone():
            raise HTTPException(409, "Ya hay un entrenamiento en curso.")
        cur = con.execute("INSERT INTO experiments(dataset_id,created,author,status,info) VALUES(?,?,?,?,?)", (body.dataset_id, datetime.now(timezone.utc).isoformat(), user["username"], "pendiente", "{}"))
        experiment_id = cur.lastrowid
    threading.Thread(target=train_experiment, args=(experiment_id, body.dataset_id), daemon=True).start()
    return {"id": experiment_id, "status": "pendiente"}


@app.get("/api/v1/experiments")
def list_experiments(user=Depends(admin)):
    with db() as con:
        rows = con.execute("SELECT * FROM experiments ORDER BY id DESC").fetchall()
    return [{**dict(row), "info": {k: v for k, v in json.loads(row["info"]).items() if k != "test_codes"}} for row in rows]


@app.post("/api/v1/experiments/{experiment_id}/test")
def evaluate_test(experiment_id: int, user=Depends(admin)):
    with db() as con:
        row = con.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
    if not row or row["status"] != "completado":
        raise HTTPException(404, "Experimento completado no encontrado.")
    info = json.loads(row["info"])
    if info.get("test") is not None:
        return info["test"]
    df = load_version(row["dataset_id"])
    for column in FEATURES + ["prioridad_alta", "es_hub"]:
        df[column] = pd.to_numeric(df[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    test = df[df.cod_mpio.isin(info["test_codes"]) & df.prioridad_alta.isin([0, 1]) & (df.es_hub == 0)].copy()
    test = test[test[FEATURES].notna().sum(axis=1) >= 20]
    pipeline = joblib.load(model_path(experiment_id))
    info["test"] = metrics(test.prioridad_alta.astype(int), pipeline.predict_proba(test[FEATURES])[:, 1])
    update_experiment(experiment_id, "completado", info)
    return info["test"]


@app.post("/api/v1/experiments/{experiment_id}/publish")
def publish_model(experiment_id: int, user=Depends(admin)):
    with db() as con:
        row = con.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        if not row or row["status"] != "completado" or not json.loads(row["info"]).get("test") or not model_path(experiment_id).exists():
            raise HTTPException(409, "Primero completa el entrenamiento y la evaluación de prueba.")
        con.execute("INSERT INTO settings(key,value) VALUES('active_model',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(experiment_id),))
    return {"active_model": experiment_id}


@app.get("/api/v1/models/active")
def get_active_model(user=Depends(current_user)):
    value = active_model()
    return {"id": value, "name": f"Experimento #{value}" if value else "HistGradientBoosting · fase 2", "threshold": .5}


@app.get("/api/v1/predictions/template")
def prediction_template(code: str, year: int, user=Depends(current_user)):
    df = operational_data()
    rows = df[(df.cod_mpio == code) & (df.a_o == year)]
    if rows.empty:
        raise HTTPException(404, "Municipio y año no encontrados.")
    row = rows.iloc[0]
    return {"name": row["nom_mpio"], "features": {key: safe(row.get(key)) for key in FEATURES}}


@app.post("/api/v1/predictions")
def manual_prediction(features: dict, user=Depends(current_user)):
    errors = []
    values = {}
    for name in FEATURES:
        value = features.get(name)
        if value is None or value == "":
            values[name] = np.nan
            continue
        try:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError()
            if name.startswith(("pct_", "nbi_")) and not 0 <= number <= 100:
                raise ValueError()
            if name == "latitud" and not -90 <= number <= 90:
                raise ValueError()
            if name == "longitud" and not -180 <= number <= 180:
                raise ValueError()
            if name == "poblacion" and number <= 0:
                raise ValueError()
            if name in ("n_sedes", "n_sedes_ese", "n_resguardos", "pob_resguardos", "n_comunidades") and (number < 0 or not number.is_integer()):
                raise ValueError()
            values[name] = number
        except (TypeError, ValueError):
            errors.append(name)
    if errors:
        raise HTTPException(422, f"Valores inválidos: {', '.join(errors)}.")
    if sum(pd.notna(v) for v in values.values()) < 20 or pd.isna(values["poblacion"]):
        raise HTTPException(422, "Se necesitan al menos 20 variables y población válida para una predicción.")
    if pd.notna(values["n_sedes_ese"]) and pd.notna(values["n_sedes"]) and values["n_sedes_ese"] > values["n_sedes"]:
        raise HTTPException(422, "Las sedes ESE no pueden superar las sedes totales.")
    probabilities, name, warning = predict_active(pd.DataFrame([values], columns=FEATURES))
    probability = float(probabilities[0])
    return {"probability": probability, "priority_high": probability >= .5, "threshold": .5, "model": name, "warning": warning}


class PlanRequest(BaseModel):
    department: str = "20"
    year: int = 2021
    brigades: int = Field(default=4, ge=1, le=100)
    max_km: float = Field(default=350, gt=0, le=2000)
    min_resguardos: int = Field(default=0, ge=0, le=100)
    lat: float = Field(default=10.460472, ge=-90, le=90)
    lon: float = Field(default=-73.259398, ge=-180, le=180)


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1 - a)))


class JourneyBase(BaseModel):
    id: int = Field(gt=0)
    brigades: int = Field(ge=1, le=100)


class JourneyRequest(BaseModel):
    date: date
    department: str = Field(pattern=r"^\d{2}$")
    year: int = Field(ge=1900, le=2100)
    bases: list[JourneyBase] = Field(min_length=1, max_length=50)
    max_km: float = Field(gt=0, le=2000, allow_inf_nan=False)
    distance_provider: str = Field(default="Haversine", pattern="^(Haversine|OSRM)$")
    expected_candidates_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    data_source: Literal["historico", "operativo"] = "historico"


def candidates_hash(prediction):
    content = json.dumps({"items": prediction["items"], "model": prediction.get("model"), "model_sha256": prediction.get("model_sha256"), "source": prediction.get("source")}, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@app.get("/api/v1/journeys/candidates")
def journey_candidates(department: str, data_source: Literal["historico", "operativo"] = "historico", year: int | None = None, user=Depends(current_user)):
    if len(department) != 2 or not department.isdigit():
        raise HTTPException(422, "Departamento inválido.")
    if data_source == "operativo":
        if year is None:
            raise HTTPException(422, "Indique el año de los registros operativos.")
        prediction = operational_priorities(department, year, user)
    else:
        data = operational_data()
        subset = data[data.cod_dpto == department]
        years = pd.to_numeric(subset.a_o, errors="coerce").dropna()
        if years.empty:
            raise HTTPException(422, "No hay datos para obtener prioridades en este departamento.")
        year = int(years.max()) if year is None else year
        prediction = priorities(department, year, user)
    with db() as con:
        territories = [dict(row) for row in con.execute("SELECT code,name FROM territories WHERE department_code=?", (department,))]
    predicted = {row["cod_mpio"] for row in prediction["items"]}
    missing = [row for row in territories if row["code"] not in predicted]
    return {**prediction, "year": year, "missing": missing, "candidates_hash": candidates_hash(prediction),
            "notice": ("Registros operativos declarados; solo se incluyen los que tienen 27 indicadores completos." if data_source == "operativo" else "Datos históricos del conjunto asociado al modelo activo; no representan necesariamente la situación actual.")}


osrm_lock = threading.Lock()
osrm_last_request = 0.0


def journey_distances(bases, candidates, provider):
    global osrm_last_request
    if provider == "Haversine":
        return [[haversine(b["latitude"], b["longitude"], c["latitud"], c["longitud"])
                 for c in candidates] for b in bases]
    if len(bases) + len(candidates) > 100:
        raise HTTPException(422, "La prueba OSRM admite hasta 100 puntos en total. Elige Haversine o reduce el escenario.")
    if not candidates:
        return [[] for _ in bases]
    coords = ";".join(f'{p["longitude"]},{p["latitude"]}' for p in bases)
    coords += ";" + ";".join(f'{c["longitud"]},{c["latitud"]}' for c in candidates)
    params = {"sources": ";".join(str(i) for i in range(len(bases))),
              "destinations": ";".join(str(i) for i in range(len(bases), len(bases) + len(candidates))),
              "annotations": "distance"}
    try:
        with osrm_lock:
            now = time.monotonic()
            if now - osrm_last_request < 1.1:
                raise HTTPException(429, "Espera un momento antes de volver a consultar el servidor OSRM de demostración.")
            osrm_last_request = now
        response = httpx.get(f"https://router.project-osrm.org/table/v1/driving/{coords}", params=params, timeout=20)
        data = response.json()
        if data.get("code") == "NoSegment":
            raise HTTPException(422, "OSRM no pudo localizar uno o más puntos en la red vial. Revisa las coordenadas o elige Haversine.")
        response.raise_for_status()
        matrix = data.get("distances")
        if data.get("code") != "Ok" or not isinstance(matrix, list) or len(matrix) != len(bases) or any(len(row) != len(candidates) for row in matrix):
            raise ValueError("Respuesta OSRM incompleta")
        sources, destinations = data.get("sources"), data.get("destinations")
        if not isinstance(sources, list) or len(sources) != len(bases) or not isinstance(destinations, list) or len(destinations) != len(candidates):
            raise ValueError("Puntos ajustados OSRM ausentes")
        snap_distances = [float(p["distance"]) for p in sources + destinations]
        values = [float(value) for row in matrix for value in row if value is not None]
        if any(not math.isfinite(v) or v < 0 for v in snap_distances + values):
            raise ValueError("Distancias OSRM inválidas")
        # A distant snap cannot be treated as a verified road connection.
        return [[None if value is None or float(sources[bi]["distance"]) > 1000 or float(destinations[mi]["distance"]) > 1000
                 else float(value) / 1000 for mi, value in enumerate(row)] for bi, row in enumerate(matrix)]
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        raise HTTPException(503, "No se pudo consultar OSRM. Reintenta o selecciona explícitamente Haversine.")


def calculate_journey(body: JourneyRequest, user):
    ids = [item.id for item in body.bases]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Una base no puede seleccionarse más de una vez.")
    if sum(item.brigades for item in body.bases) > 500:
        raise HTTPException(422, "El máximo es 500 brigadas por jornada.")
    with db() as con:
        rows = con.execute(
            f"SELECT * FROM bases WHERE id IN ({','.join('?' for _ in ids)})", ids
        ).fetchall()
    indexed = {row["id"]: dict(row) for row in rows}
    if len(indexed) != len(ids):
        raise HTTPException(422, "Una o más bases ya no existen.")
    bases = [{**indexed[item.id], "brigades": item.brigades} for item in body.bases]
    prediction = operational_priorities(body.department, body.year, user) if body.data_source == "operativo" else priorities(body.department, body.year, user)
    if body.expected_candidates_hash and candidates_hash(prediction) != body.expected_candidates_hash:
        raise HTTPException(409, "Cambió el modelo o los datos desde la consulta. Vuelve a consultar las prioridades.")
    records = prediction["items"]
    if len({r["cod_mpio"] for r in records}) != len(records):
        raise HTTPException(422, "Hay registros municipales duplicados para el período seleccionado.")
    candidates, excluded = [], []
    for row in records:
        lat, lon, population = row["latitud"], row["longitud"], row["poblacion"]
        if (lat is None or lon is None or population is None or
            not all(math.isfinite(float(v)) for v in (lat, lon, population)) or
            not (-90 <= lat <= 90 and -180 <= lon <= 180) or population < 0):
            excluded.append({"code": row["cod_mpio"], "name": row["nom_mpio"], "reason": "Coordenadas o población no disponibles o inválidas."})
        else:
            candidates.append(row)
    distances = journey_distances(bases, candidates, body.distance_provider)
    pairs = []
    for bi, base in enumerate(bases):
        for mi, municipality in enumerate(candidates):
            distance = distances[bi][mi]
            if distance is not None and math.isfinite(distance) and distance >= 0 and distance <= body.max_km:
                benefit = municipality["probability"] * math.log1p(max(0, municipality["poblacion"] * (municipality["pct_rural_disperso"] or 0) / 100 + (municipality["pob_resguardos"] or 0)))
                pairs.append((bi, mi, distance, benefit - .005 * distance))
    selected = []
    if pairs:
        matrix = np.zeros((len(bases) + len(candidates), len(pairs)))
        for i, (bi, mi, _, _) in enumerate(pairs):
            matrix[bi, i] = 1
            matrix[len(bases) + mi, i] = 1
        upper = [b["brigades"] for b in bases] + [1] * len(candidates)
        result = milp(c=-np.array([pair[3] for pair in pairs]), integrality=np.ones(len(pairs)),
                      bounds=Bounds(np.zeros(len(pairs)), np.ones(len(pairs))),
                      constraints=LinearConstraint(matrix, np.zeros(len(upper)), upper))
        if not result.success or result.x is None:
            raise HTTPException(422, "No se pudo resolver el escenario; revisa las restricciones.")
        for i, chosen in enumerate(result.x):
            if chosen > .5:
                bi, mi, distance, score = pairs[i]
                selected.append({**candidates[mi], "base_id": bases[bi]["id"], "base_name": bases[bi]["name"],
                                 "distance_km": round(distance, 2), "objective_score": round(score, 6)})
    used = {b["id"]: sum(s["base_id"] == b["id"] for s in selected) for b in bases}
    assigned_codes = {s["cod_mpio"] for s in selected}
    accessible_codes = {candidates[mi]["cod_mpio"] for _, mi, _, _ in pairs}
    remaining = []
    for mi, c in enumerate(candidates):
        if c["cod_mpio"] in assigned_codes:
            continue
        connected = any(distances[bi][mi] is not None for bi in range(len(bases)))
        reason = ("Sin conexión vial o punto ajustado a más de 1 km de la red OSRM." if not connected and body.distance_provider == "OSRM"
                  else "Sin base dentro de la distancia máxima." if c["cod_mpio"] not in accessible_codes
                  else "No seleccionado por el optimizador.")
        remaining.append({"code": c["cod_mpio"], "name": c["nom_mpio"], "reason": reason})
    created = datetime.now(timezone.utc).isoformat()
    plan = {
        "kind": "journey_multibase", "created": created, "author": user["username"],
        "parameters": body.model_dump(mode="json"), "bases": [
            {**b, "assigned": used[b["id"]], "unused": b["brigades"] - used[b["id"]]} for b in bases],
        "selected": selected, "unassigned_municipalities": remaining, "excluded": excluded,
        "candidates": records, "distance_provider": body.distance_provider, "distance_direction": "ida",
        "distance_calculated_at": created,
        "distance_service": "router.project-osrm.org (demostración)" if body.distance_provider == "OSRM" else "cálculo local",
        "distance_matrix": [{"base_id": b["id"], "municipality_code": c["cod_mpio"], "distance_km": distances[bi][mi]}
                            for bi, b in enumerate(bases) for mi, c in enumerate(candidates)],
        "model": prediction.get("model"), "model_sha256": prediction.get("model_sha256"), "model_warning": prediction.get("warning"),
        "objective": "Provisional: probabilidad × log(1 + población rural dispersa + población de resguardos) − 0.005 × km; se permiten asignaciones vacías.",
        "warning": ("Datos operativos declarados; estimación exploratoria. " if body.data_source == "operativo" else "Datos históricos. ") + "Probabilidades no calibradas y fórmula sin validación. " + ("Distancia en línea recta, no carretera." if body.distance_provider == "Haversine" else "OSRM es una estimación vial; no confirma transitabilidad ni acceso."),
    }
    return plan


@app.post("/api/v1/journeys")
def create_journey(body: JourneyRequest, user=Depends(current_user)):
    plan = calculate_journey(body, user)
    with db() as con:
        cur = con.execute("INSERT INTO plans(user_id,created,data) VALUES(?,?,?)",
                          (user["id"], plan["created"], json.dumps(plan, ensure_ascii=False, allow_nan=False)))
        plan["id"] = cur.lastrowid
    return plan


@app.post("/api/v1/journeys/preview")
def preview_journey(body: JourneyRequest, user=Depends(current_user)):
    plan = calculate_journey(body, user)
    token = secrets.token_urlsafe(32)
    with db() as con:
        con.execute("INSERT INTO journey_drafts(token,user_id,created,data) VALUES(?,?,?,?)",
                    (token, user["id"], plan["created"], json.dumps(plan, ensure_ascii=False, allow_nan=False)))
    return {**plan, "draft_token": token}


class ManualAssignment(BaseModel):
    base_id: int = Field(gt=0)
    municipality_code: str


class JourneyAssignments(BaseModel):
    assignments: list[ManualAssignment] = Field(max_length=500)


@app.put("/api/v1/journeys/drafts/{token}/assignments")
def update_journey_assignments(token: str, body: JourneyAssignments, user=Depends(current_user)):
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM journey_drafts WHERE token=? AND user_id=?", (token, user["id"])).fetchone()
        if row is None:
            raise HTTPException(404, "No se encontró esta propuesta.")
        if row["saved_plan_id"]:
            raise HTTPException(409, "El plan ya fue guardado; crea una nueva propuesta para modificarlo.")
        plan = json.loads(row["data"])
        bases = {b["id"]: b for b in plan["bases"]}
        candidates = {c["cod_mpio"]: c for c in plan["candidates"]}
        distances = {(d["base_id"], d["municipality_code"]): d["distance_km"] for d in plan["distance_matrix"]}
        excluded = {c["code"] for c in plan["excluded"]}
        selected, used, codes = [], {base_id: 0 for base_id in bases}, set()
        for assignment in body.assignments:
            base_id, code = assignment.base_id, assignment.municipality_code
            if base_id not in bases or code not in candidates or code in excluded or code in codes:
                raise HTTPException(422, "Base o municipio inválido, excluido o repetido.")
            distance = distances.get((base_id, code))
            if distance is None or distance > plan["parameters"]["max_km"]:
                raise HTTPException(422, "La asignación no tiene una conexión válida dentro de la distancia máxima.")
            used[base_id] += 1
            if used[base_id] > bases[base_id]["brigades"]:
                raise HTTPException(422, "La asignación supera la capacidad de una base.")
            codes.add(code)
            selected.append({**candidates[code], "base_id": base_id, "base_name": bases[base_id]["name"],
                             "distance_km": round(distance, 2)})
        for base in plan["bases"]:
            base["assigned"] = used[base["id"]]
            base["unused"] = base["brigades"] - base["assigned"]
        old_reasons = {m["code"]: m for m in plan["unassigned_municipalities"]}
        plan["unassigned_municipalities"] = [
            old_reasons.get(c["cod_mpio"], {"code": c["cod_mpio"], "name": c["nom_mpio"],
                                           "reason": "Retirado durante la revisión manual."})
            for c in plan["candidates"] if c["cod_mpio"] not in codes and c["cod_mpio"] not in excluded
        ]
        plan["selected"] = selected
        plan["manually_reviewed"] = True
        con.execute("UPDATE journey_drafts SET data=? WHERE token=?",
                    (json.dumps(plan, ensure_ascii=False, allow_nan=False), token))
        return {**plan, "draft_token": token}


@app.post("/api/v1/journeys/drafts/{token}/save")
def save_journey_draft(token: str, user=Depends(current_user)):
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM journey_drafts WHERE token=? AND user_id=?", (token, user["id"])).fetchone()
        if row is None:
            raise HTTPException(404, "No se encontró esta propuesta.")
        plan = json.loads(row["data"])
        if row["saved_plan_id"]:
            return {**plan, "id": row["saved_plan_id"]}
        cur = con.execute("INSERT INTO plans(user_id,created,data) VALUES(?,?,?)", (user["id"], row["created"], row["data"]))
        con.execute("UPDATE journey_drafts SET saved_plan_id=? WHERE token=?", (cur.lastrowid, token))
        return {**plan, "id": cur.lastrowid}


@app.post("/api/v1/plans")
def create_plan(body: PlanRequest, user=Depends(current_user)):
    data = priorities(body.department, body.year, user)["items"]
    candidates = [r for r in data if r["es_hub"] != 1 and r["latitud"] is not None and r["longitud"] is not None and r["poblacion"] is not None]
    if not candidates:
        raise HTTPException(422, "No hay municipios candidatos para ese departamento y año.")
    distances = np.array([haversine(body.lat, body.lon, r["latitud"], r["longitud"]) for r in candidates])
    indigenous = np.array([int((r["n_resguardos"] or 0) > 0) for r in candidates])
    benefit = np.array([r["probability"] * math.log1p(max(0, r["poblacion"] * (r["pct_rural_disperso"] or 0) / 100 + (r["pob_resguardos"] or 0))) for r in candidates])
    result = milp(c=-(benefit - .005 * distances), integrality=np.ones(len(candidates)), bounds=Bounds(np.zeros(len(candidates)), (distances <= body.max_km).astype(float)), constraints=LinearConstraint(np.array([np.ones(len(candidates)), indigenous]), [0, body.min_resguardos], [body.brigades, np.inf]))
    if not result.success or result.x is None:
        raise HTTPException(422, "No existe un plan factible con esas restricciones. Ajusta la distancia o el mínimo de resguardos.")
    selected = []
    for idx, chosen in enumerate(result.x):
        if chosen > .5:
            selected.append({**candidates[idx], "distance_km": round(float(distances[idx]), 1)})
    current = active_model()
    plan = {"parameters": body.model_dump(), "selected": selected, "distance_provider": "Haversine", "model": f"Experimento #{current}" if current else "HistGradientBoosting · fase 2"}
    with db() as con:
        cur = con.execute("INSERT INTO plans(user_id,created,data) VALUES(?,?,?)", (user["id"], datetime.now(timezone.utc).isoformat(), json.dumps(plan, ensure_ascii=False)))
        plan["id"] = cur.lastrowid
    return plan


@app.get("/api/v1/plans")
def plans(user=Depends(current_user)):
    with db() as con:
        if user["role"] == "admin":
            rows = con.execute("SELECT * FROM plans ORDER BY id DESC LIMIT 30").fetchall()
        else:
            rows = con.execute("SELECT * FROM plans WHERE user_id=? ORDER BY id DESC LIMIT 30", (user["id"],)).fetchall()
    return [{"id": r["id"], "created": r["created"], **json.loads(r["data"])} for r in rows]
