"""ETL 05 - Poblacion (denominador de la brecha).

Fuente preferida: DANE - serie municipal de poblacion por area (xlsx en data/raw),
formato 'PPED-AreaMun-2018-2042'. Aporta poblacion total y % rural disperso.
Si no esta disponible, usa la poblacion afiliada (BDUA) por municipio via API.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DATA_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    anios,
    config,
    get_logger,
    llave_norm,
    normaliza,
    soda_query,
)

ALIAS_DPTO = {
    "VALLE": "VALLE DEL CAUCA",
    "SAN ANDRES": "ARCHIPIELAGO DE SAN ANDRES PROVIDENCIA Y SANTA CATALINA",
}
AREA_RURAL = "CENTROS POBLADOS Y RURAL DISPERSO"


def _llave_dpto(dpto, mpio) -> str:
    d = normaliza(dpto)
    d = ALIAS_DPTO.get(d, d)
    return f"{d}|{normaliza(mpio)}"


def _archivos_xlsx() -> list[Path]:
    vistos: list[Path] = []
    for carpeta in (RAW_DIR, DATA_DIR):
        for ruta in sorted(carpeta.glob("*.xlsx")):
            if "MUN" in ruta.name.upper() and ruta not in vistos:
                vistos.append(ruta)
    return vistos


def _leer_dane_municipal(log) -> pd.DataFrame | None:
    for ruta in _archivos_xlsx():
        try:
            hojas = pd.read_excel(ruta, sheet_name=None, header=None, nrows=15)
        except Exception:  # noqa: BLE001
            continue
        for nombre in hojas:
            prueba = pd.read_excel(ruta, sheet_name=nombre, header=None)
            cabecera = None
            for i in range(min(15, len(prueba))):
                fila = [normaliza(v) for v in prueba.iloc[i].tolist()]
                if any("MPIO" in v for v in fila) and any(v == "TOTAL" for v in fila):
                    cabecera = i
                    break
            if cabecera is None:
                continue
            tabla = pd.read_excel(ruta, sheet_name=nombre, header=cabecera)
            tabla.columns = [normaliza(c) for c in tabla.columns]
            col = {
                "mpio": next((c for c in tabla.columns if c == "MPIO"), None),
                "anio": next((c for c in tabla.columns if c in ("ANO", "AO")), None),
                "area": next((c for c in tabla.columns if "AREA" in c), None),
                "total": next((c for c in tabla.columns if c == "TOTAL"), None),
            }
            if None in col.values():
                continue
            log(f"  DANE municipal: {ruta.name} / hoja '{nombre}' ({len(tabla):,} filas)")
            tabla = tabla.rename(columns={v: k for k, v in col.items()})
            cod = (
                tabla["mpio"].astype(str).str.replace(r"\.0$", "", regex=True)
                .str.extract(r"(\d+)")[0].str.zfill(5)
            )
            tabla["cod_mpio"] = cod
            tabla["a_o"] = pd.to_numeric(tabla["anio"], errors="coerce")
            tabla["total"] = pd.to_numeric(tabla["total"], errors="coerce")
            tabla["area_norm"] = tabla["area"].map(normaliza)
            tabla = tabla.dropna(subset=["cod_mpio", "a_o", "total"])

            g = tabla.pivot_table(index=["cod_mpio", "a_o"], columns="area_norm",
                                  values="total", aggfunc="sum")
            total_col = next((c for c in g.columns if c == "TOTAL"), g.columns[0])
            rural_col = next((c for c in g.columns if c == AREA_RURAL), None)
            out = pd.DataFrame({"poblacion": g[total_col]})
            if rural_col is not None:
                out["pct_rural_disperso"] = (g[rural_col] / g[total_col] * 100).round(3)
            out = out.reset_index()
            out["a_o"] = out["a_o"].astype(int)
            out["fuente"] = "dane"
            return out
    return None


def _completar_anios(df: pd.DataFrame, log) -> pd.DataFrame:
    anios_int = [int(a) for a in anios()]
    idx = pd.MultiIndex.from_product([sorted(df["cod_mpio"].unique()), anios_int],
                                     names=["cod_mpio", "a_o"])
    df = df.set_index(["cod_mpio", "a_o"]).reindex(idx).sort_index()
    faltantes = df["poblacion"].isna().sum()
    df = df.groupby(level=0).ffill().bfill().reset_index()
    if faltantes:
        log(f"  {faltantes:,} filas sin dato directo (p.ej. 2017): completadas con el anio mas cercano")
    return df


def _agregar_bdua(log) -> pd.DataFrame:
    ds = config()["datasets"]
    totales, zonas = [], []
    for clave, regimen in (("bdua_subsidiado", "SUBSIDIADO"), ("bdua_contributivo", "CONTRIBUTIVO")):
        vid = ds[clave]
        log(f"  BDUA {regimen} ({vid}): afiliados por municipio ...")
        filas = soda_query(
            vid,
            "SELECT dpr_nombre, mnc_nombre, sum(cantidad::number) as n "
            "GROUP BY dpr_nombre, mnc_nombre",
        )
        df = pd.DataFrame(filas)
        df["afiliados"] = pd.to_numeric(df["n"], errors="coerce").fillna(0)
        df["llave_norm"] = [_llave_dpto(d, m) for d, m in zip(df["dpr_nombre"], df["mnc_nombre"])]
        totales.append(df.groupby("llave_norm")["afiliados"].sum().rename(f"af_{regimen.lower()}"))

        filas2 = soda_query(
            vid,
            "SELECT dpr_nombre, mnc_nombre, zns_nombre, sum(cantidad::number) as n "
            "WHERE zns_nombre IS NOT NULL "
            "GROUP BY dpr_nombre, mnc_nombre, zns_nombre",
        )
        dz = pd.DataFrame(filas2)
        dz["n"] = pd.to_numeric(dz["n"], errors="coerce").fillna(0)
        dz["llave_norm"] = [_llave_dpto(d, m) for d, m in zip(dz["dpr_nombre"], dz["mnc_nombre"])]
        zonas.append(dz)

    pob = pd.concat(totales, axis=1).fillna(0)
    pob["afiliados_total"] = pob.sum(axis=1)
    pob = pob.reset_index()

    z = pd.concat(zonas, ignore_index=True)
    z["zona_norm"] = z["zns_nombre"].str.upper()
    es_rural = z["zona_norm"].str.contains("RURAL|DISPERS", na=False)
    zr = z.assign(rural=z["n"].where(es_rural, 0)).groupby("llave_norm")[["n", "rural"]].sum()
    zr["pct_rural_afiliados"] = (zr["rural"] / zr["n"] * 100).round(3)
    pob = pob.merge(zr[["pct_rural_afiliados"]].reset_index(), on="llave_norm", how="left")
    pob["fuente"] = "bdua"
    return pob


def main() -> None:
    log = get_logger("etl_05_poblacion")
    dim = pd.read_csv(PROCESSED_DIR / "dim_municipio.csv", dtype={"cod_mpio": str, "cod_dpto": str})

    dane = _leer_dane_municipal(log)
    if dane is not None and len(dane):
        dane = _completar_anios(dane, log)
        dane = dane.merge(dim[["cod_mpio", "cod_dpto", "nom_mpio"]], on="cod_mpio", how="left")
        dane["pct_rural_disperso"] = dane.get("pct_rural_disperso", pd.Series(dtype=float)).fillna(0)
        salida = PROCESSED_DIR / "poblacion_municipio_anio.csv"
        dane[["cod_mpio", "cod_dpto", "nom_mpio", "a_o", "poblacion", "pct_rural_disperso", "fuente"]].to_csv(
            salida, index=False, encoding="utf-8"
        )
        log(f"OK (DANE) -> {salida.name}: {len(dane):,} filas | "
            f"{dane['cod_mpio'].nunique():,} municipios | "
            f"poblacion 2021: {int(dane.loc[dane['a_o'] == 2021, 'poblacion'].sum()):,}")
        return

    log("ADVERTENCIA: no hay serie municipal del DANE. Se usara BDUA (snapshot).")
    pob = _agregar_bdua(log)
    salida_df = dim[["cod_mpio", "cod_dpto", "nom_mpio", "llave_norm"]].drop_duplicates("llave_norm")
    salida_df = salida_df.merge(pob, on="llave_norm", how="left")
    salida_df["afiliados_total"] = salida_df["afiliados_total"].fillna(0).astype("int64")
    salida_df["poblacion"] = salida_df["afiliados_total"]
    salida_df["pct_rural_disperso"] = salida_df["pct_rural_afiliados"]
    salida_df["fuente"] = "bdua"
    salida_df = salida_df[
        ["cod_mpio", "cod_dpto", "nom_mpio", "poblacion", "afiliados_total",
         "af_subsidiado", "af_contributivo", "pct_rural_disperso", "fuente"]
    ]
    sin_datos = int((salida_df["poblacion"] == 0).sum())
    salida = PROCESSED_DIR / "poblacion_municipio.csv"
    salida_df.to_csv(salida, index=False, encoding="utf-8")
    log(f"OK (BDUA) -> {salida.name}: {len(salida_df):,} municipios | sin datos: {sin_datos} | "
        f"poblacion total: {int(salida_df['poblacion'].sum()):,}")


if __name__ == "__main__":
    main()
