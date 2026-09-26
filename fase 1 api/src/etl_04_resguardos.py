"""ETL 04 - Contexto etnico: resguardos y comunidades indigenas por municipio."""
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


def descargar(view_id: str, columnas: list[str], log) -> pd.DataFrame:
    datos = soda_query(view_id, f"SELECT {', '.join(columnas)}")
    df = pd.DataFrame(datos)
    for col in columnas:
        if col not in df.columns:
            df[col] = None
    return df[columnas]


def main() -> None:
    log = get_logger("etl_04_resguardos")
    ds = config()["datasets"]

    log(f"Descargando resguardos ({ds['resguardos']}) ...")
    res = descargar(
        ds["resguardos"],
        ["nombre_del_departamento", "nombre_del_municipio", "c_digo_del_resguardo_dane",
         "nombre_del_resguardo", "total_poblaci_n_proyecci"],
        log,
    )
    res["pob"] = pd.to_numeric(res["total_poblaci_n_proyecci"], errors="coerce").fillna(0)
    res["llave_norm"] = [llave_norm(d, m) for d, m in zip(res["nombre_del_departamento"], res["nombre_del_municipio"])]
    agr_res = res.groupby("llave_norm").agg(
        n_resguardos=("nombre_del_resguardo", "nunique"),
        pob_resguardos=("pob", "sum"),
    ).reset_index()

    log(f"Descargando comunidades fuera de resguardo ({ds['comunidades']}) ...")
    com = descargar(
        ds["comunidades"],
        ["nombre_del_departamento", "nombre_del_municipio", "nombre_de_la_comunidad"],
        log,
    )
    com["llave_norm"] = [llave_norm(d, m) for d, m in zip(com["nombre_del_departamento"], com["nombre_del_municipio"])]
    agr_com = com.groupby("llave_norm").agg(n_comunidades=("nombre_de_la_comunidad", "nunique")).reset_index()

    dim = pd.read_csv(PROCESSED_DIR / "dim_municipio.csv", dtype={"cod_mpio": str, "cod_dpto": str})
    dim = dim[["cod_mpio", "cod_dpto", "nom_mpio", "llave_norm"]].drop_duplicates("llave_norm")
    salida_df = dim.merge(agr_res, on="llave_norm", how="left").merge(agr_com, on="llave_norm", how="left")
    for col in ("n_resguardos", "pob_resguardos", "n_comunidades"):
        salida_df[col] = salida_df[col].fillna(0).astype("int64")
    salida_df = salida_df[["cod_mpio", "cod_dpto", "nom_mpio", "n_resguardos", "pob_resguardos", "n_comunidades"]]

    salida = PROCESSED_DIR / "etnico_municipio.csv"
    salida_df.to_csv(salida, index=False, encoding="utf-8")
    log(f"OK -> {salida.name}: {len(salida_df):,} municipios | "
        f"con resguardo: {int((salida_df['n_resguardos'] > 0).sum()):,} | "
        f"con comunidades: {int((salida_df['n_comunidades'] > 0).sum()):,}")


if __name__ == "__main__":
    main()
