"""Utilidades compartidas de Fase 2 (Rutas a data/modelo compartida, Logging, Modelos)."""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _find_base_dir() -> Path:
    """Encuentra la raíz de 'fase 1 api' buscando 'config/fuentes.json' o 'data/modelo' hacia arriba."""
    curr = Path(__file__).resolve()
    while curr != curr.parent:
        if (curr / "config" / "fuentes.json").exists() or (curr / "data" / "modelo").exists():
            return curr
        curr = curr.parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = _find_base_dir()      # fase 1 api
DATA_DIR = BASE_DIR / "data"     # fase 1 api/data
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODEL_DIR = DATA_DIR / "modelo"

LOG_DIR = BASE_DIR / "logs"

FASE2_DIR = BASE_DIR / "fase 2"
MODELOS_DIR = FASE2_DIR / "modelos"
REPORTES_DIR = FASE2_DIR / "reportes"

for _d in (LOG_DIR, MODELOS_DIR, REPORTES_DIR):
    _d.mkdir(parents=True, exist_ok=True)


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
