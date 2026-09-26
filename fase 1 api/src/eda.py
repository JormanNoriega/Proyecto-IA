"""eda - Reporte de calidad y distribuciones de la tabla modelo."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LOG_DIR, MODEL_DIR, get_logger  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)


def main() -> None:
    log = get_logger("eda")
    df = pd.read_csv(MODEL_DIR / "municipio_anio.csv", dtype={"cod_mpio": str, "cod_dpto": str})
    log(f"Tabla: {df.shape[0]:,} filas x {df.shape[1]} columnas")

    log("\n== Nulos por columna (solo con nulos) ==")
    nulos = df.isna().sum()
    log(nulos[nulos > 0].to_string() if (nulos > 0).any() else "  (sin nulos)")

    log("\n== RIPS presente ==")
    log(f"  filas con RIPS: {int((~df['sin_rips']).sum()):,} / {len(df):,} "
        f"({(~df['sin_rips']).mean()*100:.1f}%)")

    con = df[~df["sin_rips"]].copy()

    log("\n== consultas_1000hab: percentiles ==")
    log(con["consultas_1000hab"].describe(percentiles=[.1, .25, .5, .75, .9, .99]).round(2).to_string())

    log("\n== Correlacion consultas_1000hab vs poblacion (sospecha 'prestador') ==")
    log(f"  pearson={con['consultas_1000hab'].corr(con['poblacion']):.3f} | "
        f"spearman={con['consultas_1000hab'].corr(con['poblacion'], method='spearman'):.3f}")

    log("\n== Top 10 municipios por consultas_1000hab (2021) ==")
    t = con[con["a_o"] == 2021].nlargest(10, "consultas_1000hab")
    log(t[["cod_mpio", "nom_mpio", "poblacion", "consultas", "consultas_1000hab", "brecha_consultas"]].to_string(index=False))

    log("\n== Bottom 10 municipios por consultas_1000hab (2021) ==")
    b = con[(con["a_o"] == 2021) & (con["poblacion"] > 0)].nsmallest(10, "consultas_1000hab")
    log(b[["cod_mpio", "nom_mpio", "poblacion", "consultas", "consultas_1000hab", "brecha_consultas"]].to_string(index=False))

    log("\n== Hubs (marcados; excluidos del ranking) ==")
    h = df[df["es_hub"] == 1]
    log(f"  filas hub: {len(h):,} | municipios: {h['cod_mpio'].nunique():,}")
    toph = h[h["a_o"] == 2021].nlargest(8, "consultas_1000hab")
    log(toph[["cod_mpio", "nom_mpio", "poblacion", "consultas_1000hab", "brecha_consultas"]].to_string(index=False))

    log("\n== brecha_consultas (pares) por anio ==")
    log(con.groupby("a_o")["brecha_consultas"].agg(["mean", "median", "std"]).round(3).to_string())

    log("\n== Correlaciones con brecha_consultas ==")
    num = con.select_dtypes(include=[np.number])
    corr = num.corrwith(con["brecha_consultas"]).sort_values()
    log(corr.round(3).to_string())

    salida = LOG_DIR / "eda_resumen.txt"
    log(f"\n(reporte mostrado en consola -> {salida})")


if __name__ == "__main__":
    main()
