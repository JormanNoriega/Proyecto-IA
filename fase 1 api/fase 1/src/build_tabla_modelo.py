"""build_tabla_modelo - Une todas las fuentes por DIVIPOLA, integra Coordenadas, NBI, Split 70/15/15 y Target."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MODEL_DIR, PROCESSED_DIR, anios, get_logger  # noqa: E402

RENOMBRE_TIPO = {
    "CONSULTAS": "consultas",
    "PROCEDIMIENTOS DE SALUD": "procedimientos",
    "URGENCIAS": "urgencias",
    "HOSPITALIZACIONES": "hospitalizaciones",
}


def _cargar_poblacion() -> pd.DataFrame:
    con_anio = PROCESSED_DIR / "poblacion_municipio_anio.csv"
    if con_anio.exists():
        df = pd.read_csv(con_anio, dtype={"cod_mpio": str, "cod_dpto": str})
        cols = ["cod_mpio", "a_o", "poblacion"]
        if "pct_rural_disperso" in df.columns:
            cols.append("pct_rural_disperso")
        return df[cols]
    df = pd.read_csv(PROCESSED_DIR / "poblacion_municipio.csv", dtype={"cod_mpio": str})
    base = pd.DataFrame({"a_o": [int(a) for a in anios()]})
    out = df[["cod_mpio", "poblacion"]].merge(base, how="cross")
    if "pct_rural_disperso" in df.columns:
        out["pct_rural_disperso"] = out["cod_mpio"].map(df.set_index("cod_mpio")["pct_rural_disperso"])
    return out


def _asignar_split_estratificado(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Asigna partición 70% Train, 15% Val, 15% Test agrupada por cod_mpio para evitar fuga de datos."""
    mpio_target = df.groupby("cod_mpio")["prioridad_alta"].max().fillna(0)
    mpios = mpio_target.index.values
    labels = mpio_target.values

    m_train, m_temp, _, y_temp = train_test_split(
        mpios, labels, test_size=0.30, stratify=labels, random_state=seed
    )
    m_val, m_test = train_test_split(
        m_temp, test_size=0.50, stratify=y_temp, random_state=seed
    )

    split_map = {m: "train" for m in m_train}
    split_map.update({m: "val" for m in m_val})
    split_map.update({m: "test" for m in m_test})

    df["split"] = df["cod_mpio"].map(split_map)
    return df


def main() -> None:
    log = get_logger("build_tabla_modelo")
    
    # 1. Maestro DIVIPOLA con Coordenadas GPS
    dim = pd.read_csv(PROCESSED_DIR / "dim_municipio.csv", dtype={"cod_mpio": str, "cod_dpto": str})
    dim = dim[["cod_mpio", "cod_dpto", "nom_mpio", "latitud", "longitud"]]
    anios_int = [int(a) for a in anios()]

    base = dim.merge(pd.DataFrame({"a_o": anios_int}), how="cross")

    # 2. Atenciones RIPS por tipo
    rp = pd.read_csv(PROCESSED_DIR / "rips_municipio_anio_tipo.csv", dtype={"cod_mpio": str, "cod_dpto": str})
    piv = rp.pivot_table(index=["cod_mpio", "a_o"], columns="tipoatencion",
                         values="atenciones", aggfunc="sum").reset_index()
    piv = piv.rename(columns=RENOMBRE_TIPO)
    for col in RENOMBRE_TIPO.values():
        if col not in piv.columns:
            piv[col] = 0
    tipos = list(RENOMBRE_TIPO.values())
    piv[tipos] = piv[tipos].fillna(0).astype("int64")
    piv["atenciones_total"] = piv[tipos].sum(axis=1)
    base = base.merge(piv, on=["cod_mpio", "a_o"], how="left")
    base["sin_rips"] = base["consultas"].isna()
    base[tipos + ["atenciones_total"]] = base[tipos + ["atenciones_total"]].fillna(0).astype("int64")

    # 3. Diagnósticos CIE-10 por municipio
    cap = pd.read_csv(PROCESSED_DIR / "rips_municipio_capitulo.csv", dtype={"cod_mpio": str})
    cap_piv = cap.pivot_table(index="cod_mpio", columns="capitulo", values="pct", aggfunc="sum")
    cap_piv.columns = [f"pct_cap_{c}" for c in cap_piv.columns]
    base = base.merge(cap_piv.reset_index(), on="cod_mpio", how="left")

    # 4. Capacidad instalada (REPS) y Contexto étnico
    for archivo, cols in (
        ("reps_sedes_municipio.csv", ["n_sedes", "n_sedes_ese"]),
        ("etnico_municipio.csv", ["n_resguardos", "pob_resguardos", "n_comunidades"]),
    ):
        df = pd.read_csv(PROCESSED_DIR / archivo, dtype={"cod_mpio": str})
        base = base.merge(df[["cod_mpio"] + cols], on="cod_mpio", how="left")
        base[cols] = base[cols].fillna(0)

    # 5. Pobreza y Vulnerabilidad Multidimensional (NBI DANE 2018)
    nbi_path = PROCESSED_DIR / "nbi_municipio.csv"
    if nbi_path.exists():
        nbi_df = pd.read_csv(nbi_path, dtype={"cod_mpio": str})
        base = base.merge(nbi_df, on="cod_mpio", how="left")

    # 6. Demografía y Ruralidad DANE
    pob = _cargar_poblacion()
    base = base.merge(pob, on=["cod_mpio", "a_o"], how="left")

    # Indicadores derivados
    pob_segura = base["poblacion"].replace(0, np.nan)
    base["consultas_1000hab"] = (base["consultas"] / pob_segura * 1000).round(2)
    base["urgencias_1000hab"] = (base["urgencias"] / pob_segura * 1000).round(2)
    base["hosp_1000hab"] = (base["hospitalizaciones"] / pob_segura * 1000).round(2)
    base["proced_1000hab"] = (base["procedimientos"] / pob_segura * 1000).round(2)
    base["ratio_consultas_urgencias"] = (
        base["consultas"] / base["urgencias"].replace(0, np.nan)
    ).round(2)
    base["sedes_10k_hab"] = (base["n_sedes"] / pob_segura * 10000).round(2)

    base["_tasa_cons"] = base["consultas"] / pob_segura
    base["_tasa_total"] = base["atenciones_total"] / pob_segura

    # Quintil de población (banda de pares comparables)
    anio_ref = max(anios_int)
    pop_ref = base.loc[base["a_o"] == anio_ref, ["cod_mpio", "poblacion"]].set_index("cod_mpio")["poblacion"]
    if pop_ref.empty:
        pop_ref = base.groupby("cod_mpio")["poblacion"].mean()
    base["banda_pob"] = base["cod_mpio"].map(pd.qcut(pop_ref.rank(method="first"), 5, labels=False)).astype("Int64")

    # Target: Brecha relativa ajustada por pares y año
    def _brecha_par(col_tasa: str, nombre: str, bench_nombre: str) -> None:
        tasa = base[col_tasa]
        cap = tasa.groupby(base["a_o"]).transform(lambda s: s.quantile(0.99))
        tasa_w = tasa.clip(upper=cap)
        bench = tasa_w.groupby([base["a_o"], base["banda_pob"]]).transform("median")
        base[bench_nombre] = (bench * 1000).round(2)
        base[nombre] = (1 - tasa_w / bench).clip(lower=0).round(4)

    _brecha_par("_tasa_cons", "brecha_consultas", "bench_consultas")
    _brecha_par("_tasa_total", "brecha_global", "bench_global")

    # Brecha nacional legacy (referencia)
    sum_cons = base.groupby("a_o")["consultas"].transform("sum")
    sum_pob = base.groupby("a_o")["poblacion"].transform("sum")
    base["brecha_nacional"] = (1 - base["_tasa_cons"] / (sum_cons / sum_pob.replace(0, np.nan))).clip(lower=0).round(4)

    # Identificación de prestadores de referencia regional (Hubs)
    ratio = base["_tasa_cons"] / (base["bench_consultas"] / 1000)
    base["es_hub"] = np.where(ratio.notna(), (ratio >= 3).astype(float), np.nan)

    # Prioridad alta: tercio superior de brecha sin considerar prestadores hub
    validos = base["brecha_consultas"].notna() & (base["es_hub"] != 1)
    umbral = base.loc[validos, "brecha_consultas"].quantile(2 / 3)
    base["prioridad_alta"] = np.where(validos, (base["brecha_consultas"] >= umbral).astype(float), np.nan)

    base = base.drop(columns=["_tasa_cons", "_tasa_total"])

    # Asignación de partición estratificada 70% Train, 15% Val, 15% Test
    base = _asignar_split_estratificado(base, seed=42)

    # Organización de columnas
    orden = ["cod_mpio", "cod_dpto", "nom_mpio", "latitud", "longitud", "a_o", "split", "banda_pob"]
    resto = [c for c in base.columns if c not in orden]
    base = base[orden + resto].sort_values(["cod_mpio", "a_o"])

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    csv = MODEL_DIR / "municipio_anio.csv"
    base.to_csv(csv, index=False, encoding="utf-8")
    try:
        base.to_parquet(MODEL_DIR / "municipio_anio.parquet", index=False)
    except Exception as exc:  # noqa: BLE001
        log(f"  (parquet no disponible: {exc})")

    hubs = int((base["es_hub"] == 1).sum())
    log(f"OK -> {csv.name}: {len(base):,} filas x {base.shape[1]} columnas")
    log(f"   municipios: {base['cod_mpio'].nunique():,} | anios: {min(anios_int)}-{max(anios_int)}")
    log(f"   coordenadas no nulas: {int(base['latitud'].notna().sum()):,} / {len(base):,}")
    log(f"   split por filas: train={int((base['split']=='train').sum()):,} (70%) | "
        f"val={int((base['split']=='val').sum()):,} (15%) | "
        f"test={int((base['split']=='test').sum()):,} (15%)")
    log(f"   brecha_consultas (pares): media={base['brecha_consultas'].mean():.3f} | "
        f"umbral_prioridad={umbral:.3f} | prioridad_alta={int(base['prioridad_alta'].sum()):,}")
    log(f"   hubs (tasa >= 3x mediana de su banda): {hubs:,} filas | "
        f"{base.loc[base['es_hub'] == 1, 'cod_mpio'].nunique():,} municipios")


if __name__ == "__main__":
    main()
