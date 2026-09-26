"""Utilidades compartidas del pipeline de datos (SODA 3.0, normalizacion, logging)."""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODEL_DIR = DATA_DIR / "modelo"
LOG_DIR = BASE_DIR / "logs"
CONFIG_PATH = BASE_DIR / "config" / "fuentes.json"

for _d in (RAW_DIR, PROCESSED_DIR, MODEL_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})
_CONFIG: dict | None = None


def config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            _CONFIG = json.load(fh)
    return _CONFIG


def anios() -> list[str]:
    return [str(a) for a in config()["anios"]]


def where_anios(columna: str = "a_o") -> str:
    lista = ", ".join(f"'{a}'" for a in anios())
    return f"{columna} in ({lista})"


class Logger:
    def __init__(self, nombre: str):
        self.path = LOG_DIR / f"{nombre}.log"
        self.fh = open(self.path, "a", encoding="utf-8")

    def __call__(self, msg) -> None:
        texto = str(msg)
        print(texto, flush=True)
        self.fh.write(texto + "\n")
        self.fh.flush()

    def close(self) -> None:
        self.fh.close()


def get_logger(nombre: str) -> Logger:
    return Logger(nombre)


def soda_query(view_id: str, sql: str, timeout: int = 300, reintentos: int = 4):
    url = f"{config()['dominio']}/api/v3/views/{view_id}/query.json"
    for intento in range(1, reintentos + 1):
        try:
            resp = _SESSION.post(url, json={"query": sql}, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            if intento == reintentos:
                raise
            time.sleep(2 * intento)
    return None


def fetch_agregado(
    view_id: str,
    base_sql: str,
    salida: Path,
    columnas: list[str],
    log: Logger,
    page_size: int | None = None,
    max_paginas: int | None = None,
    reanudar: bool = True,
) -> int:
    """Descarga un agregado paginando con LIMIT/OFFSET y escribe por lotes (append + checkpoint)."""
    page_size = page_size or int(config().get("page_size", 100000))
    salida = Path(salida)
    ckpt = Path(str(salida) + ".ckpt")
    offset, total = 0, 0
    modo, primero = "w", True
    if reanudar and salida.exists() and ckpt.exists():
        try:
            estado = json.loads(ckpt.read_text(encoding="utf-8"))
            offset, total = int(estado["offset"]), int(estado["total"])
            modo, primero = "a", False
            log(f"  reanudando desde offset {offset:,} ({total:,} filas)")
        except Exception:  # noqa: BLE001
            offset, total, modo, primero = 0, 0, "w", True
    pagina = 0
    while True:
        pagina += 1
        data = soda_query(view_id, f"{base_sql} LIMIT {page_size} OFFSET {offset}")
        filas = data if isinstance(data, list) else []
        if not filas:
            break
        df = pd.DataFrame(filas)
        for col in columnas:
            if col not in df.columns:
                df[col] = None
        df = df[columnas]
        df.to_csv(salida, mode=modo, header=primero, index=False, encoding="utf-8")
        modo, primero = "a", False
        total += len(filas)
        offset += len(filas)
        ckpt.write_text(json.dumps({"offset": offset, "total": total}), encoding="utf-8")
        log(f"  pagina {pagina}: +{len(filas):,} (acumulado {total:,})")
        if len(filas) < page_size:
            break
        if max_paginas and pagina >= max_paginas:
            log(f"  corte por max_paginas={max_paginas}")
            break
        time.sleep(0.3)
    if ckpt.exists() and not max_paginas:
        ckpt.unlink()
    log(f"OK -> {salida.name} ({total:,} filas)")
    return total


def normaliza(texto) -> str:
    if texto is None:
        return ""
    if isinstance(texto, float) and pd.isna(texto):
        return ""
    s = str(texto).strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    for ch in (".", ",", "-", "_", "(", ")", "/"):
        s = s.replace(ch, " ")
    return " ".join(s.split())


def llave_norm(departamento, municipio) -> str:
    return f"{normaliza(departamento)}|{normaliza(municipio)}"


def separa_codigo(valor) -> tuple[str | None, str | None]:
    """Separa '05001 - Medellin' -> ('05001', 'Medellin')."""
    if valor is None:
        return None, None
    if isinstance(valor, float) and pd.isna(valor):
        return None, None
    s = str(valor).strip()
    if " - " in s:
        cod, nom = s.split(" - ", 1)
        return cod.strip(), nom.strip()
    return None, s or None
