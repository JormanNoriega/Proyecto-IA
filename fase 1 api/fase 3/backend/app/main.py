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
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT.parent
STORAGE = Path(os.environ.get("BRIGADAS_STORAGE", ROOT / "storage"))
DB = STORAGE / "database" / "brigadas.sqlite3"
DATASET = PROJECT / "data" / "modelo" / "municipio_anio.csv"
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
        CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, created TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dataset_versions (id INTEGER PRIMARY KEY, created TEXT NOT NULL, author TEXT NOT NULL, records INTEGER NOT NULL, checksum TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS experiments (id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL, created TEXT NOT NULL, author TEXT NOT NULL, status TEXT NOT NULL, info TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        con.execute("UPDATE experiments SET status='interrumpido' WHERE status IN ('pendiente','ejecutando')")


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


@app.get("/api/v1/catalog")
def catalog(user=Depends(current_user)):
    df = operational_data()
    return {"departments": sorted(df.cod_dpto.dropna().unique().tolist()), "years": sorted(df.a_o.dropna().astype(int).unique().tolist(), reverse=True)}


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
        return [dict(r) for r in con.execute("SELECT * FROM dataset_versions ORDER BY id DESC").fetchall()]


@app.post("/api/v1/dataset-versions")
def create_version(user=Depends(admin)):
    historical = source_data()
    with db() as con:
        rows = con.execute("SELECT data FROM records ORDER BY id").fetchall()
    added = pd.DataFrame([json.loads(row["data"]) for row in rows])
    if not added.empty:
        known = set(zip(historical["cod_mpio"], historical["a_o"].astype(int)))
        duplicates = [(str(r["cod_mpio"]), int(r["a_o"])) for _, r in added.iterrows() if (str(r["cod_mpio"]), int(r["a_o"])) in known]
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
        cur = con.execute("INSERT INTO dataset_versions(created,author,records,checksum) VALUES(?,?,?,?)", (datetime.now(timezone.utc).isoformat(), user["username"], len(combined), checksum))
        version_id = cur.lastrowid
        path = version_path(version_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    return {"id": version_id, "records": len(combined), "checksum": checksum}


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
