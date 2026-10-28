"""ETL 00 - Catalogo maestro de municipios (DIVIPOLA) con coordenadas GPS reales."""
from __future__ import annotations

import sys
from pathlib import Path
import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    PROCESSED_DIR,
    config,
    get_logger,
    llave_norm,
)

COLUMNAS = ["cod_dpto", "dpto", "cod_mpio", "nom_mpio", "tipo_municipio", "longitud", "latitud"]


def main() -> None:
    log = get_logger("etl_00_divipola")
    view_id = config()["datasets"]["divipola"]
    log(f"Consultando DIVIPOLA ({view_id}) ...")
    
    url = f"https://www.datos.gov.co/api/views/{view_id}/rows.json"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    raw_data = resp.json()
    
    # Las columnas del dataset comienzan a partir del índice 8 en rows.json
    rows = [r[8:] for r in raw_data.get("data", [])]
    df = pd.DataFrame(rows, columns=COLUMNAS)
    
    df["cod_mpio"] = df["cod_mpio"].astype(str).str.strip().str.zfill(5)
    df["cod_dpto"] = df["cod_dpto"].astype(str).str.strip().str.zfill(2)
    df["llave_norm"] = [llave_norm(d, m) for d, m in zip(df["dpto"], df["nom_mpio"])]
    
    # Corrección clave: las coordenadas vienen con coma decimal en datos.gov.co
    df["latitud"] = pd.to_numeric(df["latitud"].astype(str).str.replace(",", "."), errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"].astype(str).str.replace(",", "."), errors="coerce")
    
    # Imputación para Nuevo Belén de Bajirá (27493) si no vino poblado en el catálogo histórico
    df.loc[df["cod_mpio"] == "27493", "latitud"] = df.loc[df["cod_mpio"] == "27493", "latitud"].fillna(7.3000)
    df.loc[df["cod_mpio"] == "27493", "longitud"] = df.loc[df["cod_mpio"] == "27493", "longitud"].fillna(-76.8500)
    
    df = df.drop_duplicates(subset=["cod_mpio"]).sort_values("cod_mpio")

    salida = PROCESSED_DIR / "dim_municipio.csv"
    df.to_csv(salida, index=False, encoding="utf-8")
    
    valid_coords = df["latitud"].notna().sum()
    log(f"OK -> {salida.name}: {len(df):,} municipios ({df['cod_dpto'].nunique()} departamentos)")
    log(f"   Municipios con coordenadas GPS validas: {valid_coords:,} de {len(df):,} ({valid_coords/len(df)*100:.1f}%)")


if __name__ == "__main__":
    main()
