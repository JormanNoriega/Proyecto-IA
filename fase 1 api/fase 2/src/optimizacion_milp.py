"""optimizacion_milp.py - Modelo Prescriptivo de Asignación y Ruteo de Brigadas de Salud (Fase 2).

Implementa Programación Lineal Entera Mixta (MILP) con solver HiGHS (scipy.optimize.milp)
para optimizar el despliegue de brigadas de salud extramurales maximizando cobertura de
vulnerabilidad y minimizando costos de transporte calculados con coordenadas GPS (Haversine).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import LinearConstraint, milp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BASE_DIR, MODEL_DIR, MODELOS_DIR, REPORTES_DIR, get_logger  # noqa: E402
from modelado import FEATURES


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula la distancia ortodrómica en kilómetros entre dos coordenadas GPS."""
    R = 6371.0  # Radio medio de la Tierra en km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def resolver_asignacion_brigadas(
    cod_dpto_objetivo: str = "20",  # Cesar por defecto (sede UPC)
    lat_base: float = 10.460472,     # Valledupar (Hospital Rosario Pumarejo de López)
    lon_base: float = -73.259398,
    n_brigadas_disponibles: int = 4, # Número de brigadas médicas móviles
    max_km_por_brigada: float = 350.0,
    min_resguardos_cobertura: int = 2,
) -> pd.DataFrame:
    log = get_logger("optimizacion_milp")
    log("=" * 60)
    log("COMPONENTE PRESCRIPTIVO: OPTIMIZACIÓN LINEAL ENTERA MIXTA (MILP)")
    log("=" * 60)

    # 1. Cargar datos del modelo y modelo de IA entrenado
    df = pd.read_parquet(MODEL_DIR / "municipio_anio.parquet")
    modelo_ia = joblib.load(MODELOS_DIR / "modelo_gradient_boosting.joblib")

    # Filtrar último año disponible (2021) para el departamento seleccionado
    dpto_df = df[(df["cod_dpto"] == cod_dpto_objetivo) & (df["a_o"] == 2021)].copy()
    if dpto_df.empty:
        log(f"No hay registros para departamento {cod_dpto_objetivo}. Usando toda la región.")
        dpto_df = df[df["a_o"] == 2021].copy()

    # Predecir probabilidades con IA
    X_dpto = dpto_df[FEATURES].fillna(0)
    dpto_df["prob_prioridad_ia"] = modelo_ia.predict_proba(X_dpto)[:, 1]

    # Calcular distancia desde la base operativa central (Hospital base)
    dpto_df["distancia_base_km"] = [
        haversine_km(lat_base, lon_base, lat, lon)
        for lat, lon in zip(dpto_df["latitud"], dpto_df["longitud"])
    ]

    # Población vulnerable estimada (Rural + Resguardos)
    dpto_df["pob_vulnerable"] = (
        dpto_df["poblacion"] * (dpto_df["pct_rural_disperso"] / 100.0) + dpto_df["pob_resguardos"]
    ).fillna(0)

    n_mpios = len(dpto_df)
    mpios = dpto_df.reset_index(drop=True)

    log(f"Candidatos para asignación: {n_mpios} municipios en Dpto {cod_dpto_objetivo}")
    log(f"Brigadas disponibles: {n_brigadas_disponibles} | Base GPS: ({lat_base:.4f}, {lon_base:.4f})")

    # ============================================================
    # FORMULACIÓN MATEMÁTICA MILP (Programación Lineal Entera)
    # Variable de decisión: x_i in {0, 1} (1 si se asigna brigada al municipio i)
    # ============================================================
    # Función Objetivo: Maximizar Cobertura de Prioridad y Vulnerabilidad - Penalización de Distancia
    # max sum_i [ (prob_prioridad_i * log(pob_vulnerable_i + 1)) - 0.005 * dist_i ] * x_i
    # Como milp() de scipy minimiza c^T x, multiplicamos por -1.
    
    beneficio = mpios["prob_prioridad_ia"] * np.log1p(mpios["pob_vulnerable"])
    penalizacion_distancia = 0.005 * mpios["distancia_base_km"]
    c = -(beneficio - penalizacion_distancia).values

    # Restricciones Lineales:
    # 1. Total de brigadas asignadas <= n_brigadas_disponibles
    # 2. Cobertura mínima de municipios con resguardos indígenas >= min_resguardos_cobertura
    # 3. Distancia máxima permitida por municipio <= max_km_por_brigada (filtro o cota)
    
    # Matriz A_ub:
    # Fila 0: sum_i x_i <= n_brigadas_disponibles
    # Fila 1: sum_{i in resguardos} x_i >= min_resguardos_cobertura  -->  -sum x_i <= -min_resguardos_cobertura
    
    ind_resguardos = (mpios["n_resguardos"] > 0).astype(float).values
    
    A_rows = [
        np.ones(n_mpios),           # Límite de brigadas
        -ind_resguardos,            # Mínimo de resguardos
    ]
    b_u = [n_brigadas_disponibles, -min_resguardos_cobertura]
    b_l = [0, -n_mpios]

    constraints = LinearConstraint(A_rows, b_l, b_u)

    # Variables binarias: integrality = 1 para todas las x_i
    integrality = np.ones(n_mpios)
    # Cotas de variables: 0 <= x_i <= 1 (y 0 si excede max_km_por_brigada)
    upper_bounds = np.where(mpios["distancia_base_km"] <= max_km_por_brigada, 1.0, 0.0)
    bounds = (np.zeros(n_mpios), upper_bounds)

    # Resolver con solver HiGHS
    res = milp(c=c, constraints=constraints, integrality=integrality, bounds=bounds)

    if not res.success:
        log(f"Aviso del Solver: {res.status} - {res.message}. Relajando restricción de resguardos.")
        constraints = LinearConstraint([np.ones(n_mpios)], [0], [n_brigadas_disponibles])
        res = milp(c=c, constraints=constraints, integrality=integrality, bounds=bounds)

    mpios["asignar_brigada"] = np.round(res.x).astype(int)

    # Asignar número de brigada (1..K)
    asignados = mpios[mpios["asignar_brigada"] == 1].sort_values("distancia_base_km").copy()
    asignados["numero_brigada"] = [f"Brigada Móvil #{i+1}" for i in range(len(asignados))]
    
    log(f"Optimización completada exitosamente. Brigadas asignadas: {len(asignados)}")
    log("\nPLAN OPERATIVO ÓPTIMO DE DESPACHO:")
    cols_rep = [
        "nom_mpio", "prob_prioridad_ia", "pob_vulnerable", "distancia_base_km",
        "n_resguardos", "nbi_rural", "numero_brigada"
    ]
    log(asignados[cols_rep].to_string(index=False))

    # Guardar reporte
    csv_salida = REPORTES_DIR / "asignacion_brigadas_optima.csv"
    asignados.to_csv(csv_salida, index=False, encoding="utf-8")
    log(f"\nOK -> Plan de despacho guardado en {csv_salida.name}")

    return asignados


def main() -> None:
    resolver_asignacion_brigadas()


if __name__ == "__main__":
    main()
