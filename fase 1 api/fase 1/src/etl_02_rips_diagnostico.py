"""ETL 02 - RIPS: atenciones por municipio x capitulo CIE-10 (perfil 2017-2021).

Los PROCEDIMIENTOS usan codigos CUPS (numericos) y contaminan el perfil, por eso
se excluyen. El sentinel "1 - NO DEFINIDO" tambien se descarta.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    PROCESSED_DIR,
    config,
    fetch_agregado,
    get_logger,
    separa_codigo,
    where_anios,
)

COLUMNAS = ["municipio", "capitulo", "numeroatenciones"]


def main() -> None:
    log = get_logger("etl_02_rips_diagnostico")
    view_id = config()["datasets"]["rips"]
    base_sql = (
        "SELECT municipio, substring(diagnostico,1,1) as capitulo, "
        "sum(numeroatenciones::number) as numeroatenciones "
        f"WHERE {where_anios()} AND tipoatencion in "
        "('CONSULTAS', 'URGENCIAS', 'HOSPITALIZACIONES') "
        "GROUP BY municipio, capitulo "
        "ORDER BY municipio, capitulo"
    )
    crudo = PROCESSED_DIR / "rips_municipio_capitulo.csv"
    log(f"Descargando RIPS perfil de diagnostico ({view_id}) ...")
    fetch_agregado(view_id, base_sql, crudo, COLUMNAS, log)

    df = pd.read_csv(crudo, dtype=str)
    df["cod_mpio"] = [x[0] for x in df["municipio"].map(separa_codigo)]
    df["capitulo"] = df["capitulo"].fillna("?").astype(str).str.upper()
    df["atenciones"] = pd.to_numeric(df["numeroatenciones"], errors="coerce").fillna(0).astype("int64")
    df = df[["cod_mpio", "capitulo", "atenciones"]].dropna(subset=["cod_mpio"])
    df = df[df["capitulo"].isin(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))]

    total = df.groupby("cod_mpio")["atenciones"].transform("sum")
    df["pct"] = (df["atenciones"] / total * 100).round(4)
    df = df.sort_values(["cod_mpio", "capitulo"])

    salida = PROCESSED_DIR / "rips_municipio_capitulo.csv"
    df.to_csv(salida, index=False, encoding="utf-8")
    log(f"OK -> {salida.name}: {len(df):,} filas | {df['capitulo'].nunique()} capitulos | "
        f"{df['cod_mpio'].nunique():,} municipios")


if __name__ == "__main__":
    main()
