"""probar_ia.py - Script interactivo para consultar y probar el modelo de IA con cualquier municipio de Colombia."""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BASE_DIR, MODEL_DIR, MODELOS_DIR  # noqa: E402
from modelado import FEATURES


def consultar_municipio(nombre_o_codigo: str) -> None:
    parquet_path = MODEL_DIR / "municipio_anio.parquet"
    if not parquet_path.exists():
        parquet_path = MODEL_DIR / "municipio_anio.csv"
        df = pd.read_csv(parquet_path, dtype={"cod_mpio": str, "cod_dpto": str})
    else:
        df = pd.read_parquet(parquet_path)

    modelo_path = MODELOS_DIR / "modelo_gradient_boosting.joblib"
    if not modelo_path.exists():
        print("Error: No se encontró el modelo entrenado en", modelo_path)
        return

    modelo = joblib.load(modelo_path)

    # Buscar municipio por nombre o código (último año: 2021)
    busqueda = nombre_o_codigo.strip().upper()
    filtro = (df["a_o"] == 2021) & (
        (df["cod_mpio"] == busqueda) | (df["nom_mpio"].str.upper().str.contains(busqueda, na=False))
    )
    coincidencias = df[filtro]

    if coincidencias.empty:
        # Si no encuentra en 2021, buscar en cualquier año
        filtro = (df["cod_mpio"] == busqueda) | (df["nom_mpio"].str.upper().str.contains(busqueda, na=False))
        coincidencias = df[filtro].sort_values("a_o", ascending=False)

    if coincidencias.empty:
        print(f"\n❌ No se encontraron municipios con el término: '{nombre_o_codigo}'")
        print("Sugerencias: 'Valledupar', 'Pueblo Bello', 'Uribia', 'Becerril', 'Aguachica', 'Ciénaga'")
        return

    # Si hay varios, tomar el primero y listar alternativas
    if len(coincidencias) > 1:
        print(f"\nSe encontraron {len(coincidencias)} coincidencias. Mostrando la más relevante:")

    row = coincidencias.iloc[0]

    # Vector de características
    X = pd.DataFrame([row[FEATURES]]).fillna(0)
    prob_prioridad = float(modelo.predict_proba(X)[0, 1])
    pred_clase = int(prob_prioridad >= 0.5)

    print("\n" + "=" * 65)
    print(f"🏥 DIAGNÓSTICO DE IA — SISTEMA DE BRIGADAS EXTRAMURALES")
    print("=" * 65)
    print(f"📍 Municipio:       {row['nom_mpio']} ({row['cod_dpto']} - {row['cod_mpio']})")
    print(f"🌍 Coordenadas GPS: Lat {row['latitud']:.4f}, Lon {row['longitud']:.4f}")
    print(f"👥 Población Total: {int(row['poblacion']):,} habitantes")
    print(f"🌾 Rural Disperso:  {row['pct_rural_disperso']:.1f}% de la población")
    print(f"🏚️ NBI Rural:       {row['nbi_rural']:.1f}% de pobreza en el campo")
    print(f"🏕️ Resguardos Ind.: {int(row['n_resguardos'])} ({int(row['pob_resguardos']):,} personas)")
    print(f"🩺 Sedes de Salud:  {int(row['n_sedes'])} (Públicas ESE: {int(row['n_sedes_ese'])})")
    print("-" * 65)
    
    # Resultado de la IA
    porcentaje = prob_prioridad * 100
    barra = "█" * int(porcentaje // 5) + "░" * (20 - int(porcentaje // 5))
    
    print(f"📊 Probabilidad de Déficit Crítico: [{barra}] {porcentaje:.1f}%")
    
    if row.get("es_hub") == 1:
        print("🏢 Estado Especial: PRESTADOR DE REFERENCIA (HUB HOSPITALARIO REGIONAL)")
        print("   -> No requiere brigadas móviles (recibe remisiones de otros municipios).")
    elif pred_clase == 1 or prob_prioridad >= 0.5:
        print("🚨 RECOMENDACIÓN: 🔴 PRIORIDAD ALTA PARA ENVÍO DE BRIGADA EXTRAMURAL")
        print("   -> El territorio presenta alta vulnerabilidad rural y déficit grave de atención.")
    else:
        print("✅ RECOMENDACIÓN: 🟢 PRIORIDAD NORMAL / REGULAR")
        print("   -> La cobertura ambulatoria actual se encuentra dentro del rango de sus pares.")
    print("=" * 65)


def main() -> None:
    if len(sys.argv) > 1:
        termino = " ".join(sys.argv[1:])
        consultar_municipio(termino)
    else:
        # Modo interactivo
        print("=============================================================")
        print("DEMO INTERACTIVA DE IA — SISTEMA DE PRIORIZACIÓN DE SALUD")
        print("=============================================================")
        print("Puedes escribir el nombre de cualquier municipio de Colombia.")
        print("Ejemplos: Pueblo Bello, Uribia, Valledupar, Becerril, Quibdó")
        print("Escribe 'salir' para terminar.\n")
        
        # Prueba automática de ejemplo
        consultar_municipio("Pueblo Bello")
        consultar_municipio("Valledupar")


if __name__ == "__main__":
    main()
