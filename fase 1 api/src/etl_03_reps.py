"""ETL 03 - REPS: conteo de sedes habilitadas por municipio."""
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
    llave_norm,
)

COLUMNAS = ["departamentodededesc", "municipiosededesc", "claseprestador", "ese", "n"]


def main() -> None:
    log = get_logger("etl_03_reps")
    view_id = config()["datasets"]["reps"]
    base_sql = (
        "SELECT departamentodededesc, municipiosededesc, claseprestador, ese, count(*) as n "
        "GROUP BY departamentodededesc, municipiosededesc, claseprestador, ese "
        "ORDER BY departamentodededesc, municipiosededesc, claseprestador, ese"
    )
    crudo = PROCESSED_DIR / "reps_sedes_detalle.csv"
    log(f"Descargando REPS agregado ({view_id}) ...")
    fetch_agregado(view_id, base_sql, crudo, COLUMNAS, log)

    det = pd.read_csv(crudo, dtype=str)
    det["n"] = pd.to_numeric(det["n"], errors="coerce").fillna(0).astype("int64")
    det["ese_norm"] = det["ese"].str.strip().str.upper()
    det["clase"] = det["claseprestador"].str.strip().str.upper()
    det["llave_norm"] = [llave_norm(d, m) for d, m in zip(det["departamentodededesc"], det["municipiosededesc"])]

    agrupado = det.groupby("llave_norm").agg(
        n_sedes=("n", "sum"),
        n_clases=("clase", "nunique"),
    )
    ese = det[det["ese_norm"].isin(["SI", "S", "1"])].groupby("llave_norm")["n"].sum()
    agrupado["n_sedes_ese"] = ese
    agrupado = agrupado.fillna({"n_sedes_ese": 0}).reset_index()
    agrupado["n_sedes_ese"] = agrupado["n_sedes_ese"].astype("int64")

    dim = pd.read_csv(PROCESSED_DIR / "dim_municipio.csv", dtype={"cod_mpio": str, "cod_dpto": str})
    dim = dim[["cod_mpio", "cod_dpto", "nom_mpio", "llave_norm"]].drop_duplicates("llave_norm")
    salida_df = dim.merge(agrupado, on="llave_norm", how="left")
    salida_df["n_sedes"] = salida_df["n_sedes"].fillna(0).astype("int64")
    salida_df["n_sedes_ese"] = salida_df["n_sedes_ese"].fillna(0).astype("int64")
    salida_df = salida_df[["cod_mpio", "cod_dpto", "nom_mpio", "n_sedes", "n_sedes_ese"]]

    salida = PROCESSED_DIR / "reps_sedes_municipio.csv"
    salida_df.to_csv(salida, index=False, encoding="utf-8")
    log(f"OK -> {salida.name}: {len(salida_df):,} municipios | "
        f"sin sede: {int((salida_df['n_sedes'] == 0).sum()):,} | total sedes: {int(salida_df['n_sedes'].sum()):,}")
    log(f"   valores 'ese': {sorted(det['ese_norm'].dropna().unique().tolist())}")
    log(f"   valores 'claseprestador': {sorted(det['clase'].dropna().unique().tolist())[:12]}")


if __name__ == "__main__":
    main()
