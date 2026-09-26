"""ETL 00 - Catalogo maestro de municipios (DIVIPOLA) como llave del dataset."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    PROCESSED_DIR,
    config,
    get_logger,
    llave_norm,
    soda_query,
)

COLUMNAS = ["cod_dpto", "dpto", "cod_mpio", "nom_mpio", "tipo_municipio", "longitud", "latitud"]


def main() -> None:
    log = get_logger("etl_00_divipola")
    view_id = config()["datasets"]["divipola"]
    log(f"Consultando DIVIPOLA ({view_id}) ...")
    data = soda_query(
        view_id,
        "SELECT cod_dpto, dpto, cod_mpio, nom_mpio, tipo_municipio, longitud, latitud "
        "ORDER BY cod_mpio",
    )
    df = pd.DataFrame(data)
    for col in COLUMNAS:
        if col not in df.columns:
            df[col] = None
    df = df[COLUMNAS].copy()
    df["cod_mpio"] = df["cod_mpio"].astype(str).str.strip()
    df["cod_dpto"] = df["cod_dpto"].astype(str).str.strip()
    df["llave_norm"] = [llave_norm(d, m) for d, m in zip(df["dpto"], df["nom_mpio"])]
    df["latitud"] = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
    df = df.drop_duplicates(subset=["cod_mpio"]).sort_values("cod_mpio")

    salida = PROCESSED_DIR / "dim_municipio.csv"
    df.to_csv(salida, index=False, encoding="utf-8")
    log(f"OK -> {salida.name}: {len(df):,} municipios ({df['cod_dpto'].nunique()} departamentos)")
    log(f"   municipios: {int((df['tipo_municipio'].str.upper() == 'MUNICIPIO').sum()):,}")


if __name__ == "__main__":
    main()
