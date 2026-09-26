"""ETL 01 - RIPS: atenciones por municipio x anio x tipo (agregado en servidor)."""
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

COLUMNAS = ["departamento", "municipio", "a_o", "tipoatencion", "numeroatenciones"]


def main() -> None:
    log = get_logger("etl_01_rips_principal")
    view_id = config()["datasets"]["rips"]
    base_sql = (
        "SELECT departamento, municipio, a_o, tipoatencion, "
        "sum(numeroatenciones::number) as numeroatenciones "
        f"WHERE {where_anios()} "
        "GROUP BY departamento, municipio, a_o, tipoatencion "
        "ORDER BY departamento, municipio, a_o, tipoatencion"
    )
    crudo = PROCESSED_DIR / "rips_municipio_anio_tipo.csv"
    log(f"Descargando RIPS principal ({view_id}) ...")
    fetch_agregado(view_id, base_sql, crudo, COLUMNAS, log)

    df = pd.read_csv(crudo, dtype=str)
    dpto = df["departamento"].map(separa_codigo)
    mpio = df["municipio"].map(separa_codigo)
    df["cod_dpto"] = [x[0] for x in dpto]
    df["nom_dpto"] = [x[1] for x in dpto]
    df["cod_mpio"] = [x[0] for x in mpio]
    df["nom_mpio"] = [x[1] for x in mpio]
    df["a_o"] = df["a_o"].astype(int)
    df["atenciones"] = pd.to_numeric(df["numeroatenciones"], errors="coerce").fillna(0).astype("int64")
    df = df[["cod_dpto", "nom_dpto", "cod_mpio", "nom_mpio", "a_o", "tipoatencion", "atenciones"]]
    df = df.dropna(subset=["cod_mpio"]).sort_values(["cod_mpio", "a_o", "tipoatencion"])

    salida = PROCESSED_DIR / "rips_municipio_anio_tipo.csv"
    df.to_csv(salida, index=False, encoding="utf-8")
    log(f"OK -> {salida.name}: {len(df):,} filas | {df['cod_mpio'].nunique():,} municipios | "
        f"{df['a_o'].min()}-{df['a_o'].max()}")
    log(f"   tipos: {sorted(df['tipoatencion'].unique().tolist())}")


if __name__ == "__main__":
    main()
