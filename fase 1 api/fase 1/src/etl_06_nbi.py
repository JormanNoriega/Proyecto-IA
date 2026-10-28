"""ETL 06 - Indicadores de Necesidades Basicas Insatisfechas (NBI) Censo DANE 2018.

Fuente: Censo Nacional de Poblacion y Vivienda (CNPV) 2018 - Medida de NBI.
Aporta vulnerabilidad multidimensional desagregada para la zona rural dispersa.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    PROCESSED_DIR,
    RAW_DIR,
    get_logger,
)


def main() -> None:
    log = get_logger("etl_06_nbi")
    ruta_excel = RAW_DIR / "CNPV-2018-NBI-DIVIPOLA-2021.xlsx"
    if not ruta_excel.exists():
        # Fallback a la raíz si no estuviese en raw
        ruta_excel = RAW_DIR.parent.parent.parent / "CNPV-2018-NBI-DIVIPOLA-2021.xlsx"
    
    log(f"Leyendo NBI desde {ruta_excel.name} ...")
    df_raw = pd.read_excel(ruta_excel, sheet_name="Municipios", skiprows=10, header=None)
    df_raw = df_raw.dropna(subset=[0, 2])
    
    cod_dpto = df_raw[0].astype(str).str.strip().str.split(".").str[0].str.zfill(2)
    cod_mpio_3 = df_raw[2].astype(float).astype(int).astype(str).str.zfill(3)
    cod_mpio = cod_dpto + cod_mpio_3
    
    df_nbi = pd.DataFrame({
        "cod_mpio": cod_mpio,
        # Indicadores Municipales Totales
        "nbi_total": pd.to_numeric(df_raw[4], errors="coerce").round(2),
        "nbi_miseria": pd.to_numeric(df_raw[5], errors="coerce").round(2),
        "nbi_vivienda": pd.to_numeric(df_raw[6], errors="coerce").round(2),
        "nbi_servicios": pd.to_numeric(df_raw[7], errors="coerce").round(2),
        "nbi_hacinamiento": pd.to_numeric(df_raw[8], errors="coerce").round(2),
        "nbi_inasistencia": pd.to_numeric(df_raw[9], errors="coerce").round(2),
        "nbi_dependencia": pd.to_numeric(df_raw[10], errors="coerce").round(2),
        # Indicadores Especificos de Zona Rural Dispersa (Foco del proyecto)
        "nbi_rural": pd.to_numeric(df_raw[18], errors="coerce").round(2),
        "nbi_rural_miseria": pd.to_numeric(df_raw[19], errors="coerce").round(2),
        "nbi_rural_vivienda": pd.to_numeric(df_raw[20], errors="coerce").round(2),
        "nbi_rural_servicios": pd.to_numeric(df_raw[21], errors="coerce").round(2),
        "nbi_rural_hacinamiento": pd.to_numeric(df_raw[22], errors="coerce").round(2),
        "nbi_rural_inasistencia": pd.to_numeric(df_raw[23], errors="coerce").round(2),
        "nbi_rural_dependencia": pd.to_numeric(df_raw[24], errors="coerce").round(2),
    })
    
    # Excluir fila nacional '00000' si existe
    df_nbi = df_nbi[df_nbi["cod_mpio"] != "00000"].drop_duplicates(subset=["cod_mpio"])
    
    # Asegurar cruce completo con el catalogo DIM (1.122 municipios)
    dim = pd.read_csv(PROCESSED_DIR / "dim_municipio.csv", dtype={"cod_mpio": str, "cod_dpto": str})
    merged = dim[["cod_mpio", "cod_dpto", "nom_mpio"]].merge(df_nbi, on="cod_mpio", how="left")
    
    # Para municipios nuevos creados post-2018 (ej: 27493 Nuevo Belén de Bajirá), imputar con la mediana de su dpto
    num_cols = [c for c in df_nbi.columns if c != "cod_mpio"]
    for col in num_cols:
        dpto_median = merged.groupby("cod_dpto")[col].transform("median")
        merged[col] = merged[col].fillna(dpto_median)
    
    salida = PROCESSED_DIR / "nbi_municipio.csv"
    merged[["cod_mpio"] + num_cols].to_csv(salida, index=False, encoding="utf-8")
    
    log(f"OK -> {salida.name}: {len(merged):,} municipios con NBI procesado")
    log(f"   Media NBI Total: {merged['nbi_total'].mean():.2f}% | Media NBI Rural Disperso: {merged['nbi_rural'].mean():.2f}%")
    log(f"   Media Miseria Rural: {merged['nbi_rural_miseria'].mean():.2f}% | Media Sin Servicios Rural: {merged['nbi_rural_servicios'].mean():.2f}%")


if __name__ == "__main__":
    main()
