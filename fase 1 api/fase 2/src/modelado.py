"""modelado.py - Entrenamiento, ajuste de hiperparámetros y evaluación comparativa de modelos (Fase 2)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BASE_DIR, LOG_DIR, MODEL_DIR, get_logger  # noqa: E402

FASE2_DIR = BASE_DIR / "fase 2"
MODELOS_DIR = FASE2_DIR / "modelos"
REPORTES_DIR = FASE2_DIR / "reportes"

for _d in (MODELOS_DIR, REPORTES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Lista rigurosa de características predictoras (sin fuga de datos)
FEATURES = [
    # Demográficas y Geográficas
    "latitud",
    "longitud",
    "poblacion",
    "pct_rural_disperso",
    "banda_pob",
    # Pobreza y Vulnerabilidad Multidimensional (NBI)
    "nbi_total",
    "nbi_miseria",
    "nbi_vivienda",
    "nbi_servicios",
    "nbi_hacinamiento",
    "nbi_inasistencia",
    "nbi_dependencia",
    "nbi_rural",
    "nbi_rural_miseria",
    "nbi_rural_servicios",
    "nbi_rural_hacinamiento",
    # Capacidad Instalada (REPS)
    "n_sedes",
    "n_sedes_ese",
    "sedes_10k_hab",
    # Contexto Étnico
    "n_resguardos",
    "pob_resguardos",
    "n_comunidades",
    # Capítulos CIE-10 más sensibles
    "pct_cap_O",  # Embarazo, parto y puerperio
    "pct_cap_A",  # Infecciosas y parasitarias
    "pct_cap_J",  # Respiratorias
    "pct_cap_K",  # Digestivas
    "pct_cap_Z",  # Contacto con servicios de salud
]


def cargar_datos(log) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ruta_parquet = MODEL_DIR / "municipio_anio.parquet"
    if ruta_parquet.exists():
        df = pd.read_parquet(ruta_parquet)
    else:
        df = pd.read_csv(MODEL_DIR / "municipio_anio.csv")

    # Excluir prestadores hub (centros de referencia regional)
    df_valid = df[df["es_hub"] != 1].copy()
    # Filtrar solo filas con target válido (con RIPS)
    df_valid = df_valid.dropna(subset=["prioridad_alta"]).copy()
    df_valid["prioridad_alta"] = df_valid["prioridad_alta"].astype(int)

    # Imputar medianas para features CIE-10 que tengan nulos por falta de casos
    for col in FEATURES:
        if col in df_valid.columns:
            df_valid[col] = df_valid[col].fillna(df_valid[col].median())

    train_df = df_valid[df_valid["split"] == "train"].copy()
    val_df = df_valid[df_valid["split"] == "val"].copy()
    test_df = df_valid[df_valid["split"] == "test"].copy()

    log(f"Datos cargados (Excluidos Hubs): {len(df_valid):,} filas")
    log(f"  Train: {len(train_df):,} | Val: {len(val_df):,} | Test: {len(test_df):,}")
    log(f"  Positivos (% Prioridad Alta) -> Train: {train_df['prioridad_alta'].mean()*100:.1f}% | "
        f"Val: {val_df['prioridad_alta'].mean()*100:.1f}% | Test: {test_df['prioridad_alta'].mean()*100:.1f}%")

    return train_df, val_df, test_df


def evaluar_modelo(nombre: str, modelo, X_test, y_test, scaler=None) -> dict:
    X_in = scaler.transform(X_test) if scaler else X_test
    y_pred = modelo.predict(X_in)
    if hasattr(modelo, "predict_proba"):
        y_prob = modelo.predict_proba(X_in)[:, 1]
    else:
        y_prob = np.zeros(len(y_test))

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    roc = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 and hasattr(modelo, "predict_proba") else 0.5
    pr_auc = average_precision_score(y_test, y_prob) if hasattr(modelo, "predict_proba") else 0.0

    return {
        "modelo": nombre,
        "accuracy": round(float(acc), 4),
        "precision": round(float(prec), 4),
        "recall": round(float(rec), 4),
        "f1_score": round(float(f1), 4),
        "roc_auc": round(float(roc), 4),
        "pr_auc": round(float(pr_auc), 4),
        "y_prob": y_prob,
        "y_pred": y_pred,
    }


def main() -> None:
    log = get_logger("modelado_fase2")
    log("=" * 60)
    log("FASE 2: ENTRENAMIENTO, AJUSTE Y EVALUACIÓN COMPARATIVA")
    log("=" * 60)

    train_df, val_df, test_df = cargar_datos(log)

    X_train = train_df[FEATURES]
    y_train = train_df["prioridad_alta"]

    X_val = val_df[FEATURES]
    y_val = val_df["prioridad_alta"]

    X_test = test_df[FEATURES]
    y_test = test_df["prioridad_alta"]

    # Escalador para modelos lineales
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)
    joblib.dump(scaler, MODELOS_DIR / "scaler.joblib")

    resultados = []
    modelos_dict = {}

    # 1. Modelo Baseline Trivial (Dummy)
    log("\n[1/4] Entrenando Baseline Trivial (Dummy)...")
    dummy = DummyClassifier(strategy="most_frequent")
    dummy.fit(X_train, y_train)
    res_dummy = evaluar_modelo("Dummy Baseline", dummy, X_test, y_test)
    resultados.append(res_dummy)
    modelos_dict["Dummy Baseline"] = dummy
    joblib.dump(dummy, MODELOS_DIR / "modelo_dummy.joblib")

    # 2. Modelo Lineal: Regresión Logística
    log("\n[2/4] Entrenando Regresión Logística...")
    lr = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    lr.fit(X_train_scaled, y_train)
    res_lr = evaluar_modelo("Regresión Logística", lr, X_test_scaled, y_test)
    resultados.append(res_lr)
    modelos_dict["Regresión Logística"] = lr
    joblib.dump(lr, MODELOS_DIR / "modelo_logistica.joblib")

    # 3. Random Forest con Búsqueda de Hiperparámetros
    log("\n[3/4] Ajustando hiperparámetros de Random Forest...")
    rf_params = {
        "n_estimators": [100, 200],
        "max_depth": [6, 10, None],
        "min_samples_split": [2, 5],
        "class_weight": ["balanced"],
    }
    rf_grid = GridSearchCV(
        RandomForestClassifier(random_state=42),
        rf_params,
        cv=3,
        scoring="f1",
        n_jobs=-1,
    )
    rf_grid.fit(X_train, y_train)
    best_rf = rf_grid.best_estimator_
    log(f"  Mejores hiperparámetros RF: {rf_grid.best_params_}")
    res_rf = evaluar_modelo("Random Forest (Optimizado)", best_rf, X_test, y_test)
    resultados.append(res_rf)
    modelos_dict["Random Forest (Optimizado)"] = best_rf
    joblib.dump(best_rf, MODELOS_DIR / "modelo_random_forest.joblib")

    # 4. HistGradientBoosting (Boosting de Alto Rendimiento)
    log("\n[4/4] Ajustando HistGradientBoosting...")
    hgb_params = {
        "learning_rate": [0.03, 0.08, 0.15],
        "max_iter": [100, 150],
        "max_leaf_nodes": [15, 31],
        "min_samples_leaf": [20, 40],
    }
    hgb_grid = GridSearchCV(
        HistGradientBoostingClassifier(random_state=42),
        hgb_params,
        cv=3,
        scoring="f1",
        n_jobs=-1,
    )
    hgb_grid.fit(X_train, y_train)
    best_hgb = hgb_grid.best_estimator_
    log(f"  Mejores hiperparámetros HGB: {hgb_grid.best_params_}")
    res_hgb = evaluar_modelo("HistGradientBoosting", best_hgb, X_test, y_test)
    resultados.append(res_hgb)
    modelos_dict["HistGradientBoosting"] = best_hgb
    joblib.dump(best_hgb, MODELOS_DIR / "modelo_gradient_boosting.joblib")

    # Tabla resumen de métricas
    res_tabla = []
    for r in resultados:
        res_tabla.append({
            "Modelo": r["modelo"],
            "Accuracy": r["accuracy"],
            "Precision": r["precision"],
            "Recall": r["recall"],
            "F1-Score": r["f1_score"],
            "ROC-AUC": r["roc_auc"],
            "PR-AUC": r["pr_auc"],
        })
    df_metricas = pd.DataFrame(res_tabla).sort_values("F1-Score", ascending=False)
    csv_metricas = REPORTES_DIR / "metricas_comparacion.csv"
    json_metricas = REPORTES_DIR / "metricas_comparacion.json"
    df_metricas.to_csv(csv_metricas, index=False, encoding="utf-8")
    
    with open(json_metricas, "w", encoding="utf-8") as f:
        json.dump(res_tabla, f, indent=2)

    log("\n" + "=" * 60)
    log("TABLA COMPARATIVA FINAL EN TEST SET (CIEGO):")
    log("=" * 60)
    log(df_metricas.to_string(index=False))

    # Generación de Gráficos de Evaluación
    # A. Curvas ROC Comparativas
    plt.figure(figsize=(9, 7))
    for r in resultados:
        if r["modelo"] == "Dummy Baseline":
            continue
        fpr, tpr, _ = roc_curve(y_test, r["y_prob"])
        plt.plot(fpr, tpr, label=f"{r['modelo']} (AUC = {r['roc_auc']:.3f})", lw=2)
    plt.plot([0, 1], [0, 1], "k--", label="Azar (AUC = 0.500)", lw=1.5)
    plt.xlabel("Tasa de Falsos Positivos (1 - Especificidad)", fontsize=11)
    plt.ylabel("Tasa de Verdaderos Positivos (Sensibilidad / Recall)", fontsize=11)
    plt.title("Comparación de Curvas ROC en Test Set — Priorización de Brigadas", fontsize=13, fontweight="bold")
    plt.legend(loc="lower right", fontsize=10)
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(REPORTES_DIR / "curva_roc_comparacion.png", dpi=300)
    plt.close()

    # B. Matrices de Confusión
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    modelos_visual = [
        ("Regresión Logística", res_lr["y_pred"]),
        ("Random Forest", res_rf["y_pred"]),
        ("HistGradientBoosting", res_hgb["y_pred"]),
    ]
    for idx, (m_nombre, y_p) in enumerate(modelos_visual):
        cm = confusion_matrix(y_test, y_p)
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=axes[idx], cbar=False,
                    xticklabels=["No Prioritario", "Prioridad Alta"],
                    yticklabels=["No Prioritario", "Prioridad Alta"])
        axes[idx].set_title(m_nombre, fontsize=12, fontweight="bold")
        axes[idx].set_xlabel("Predicción", fontsize=10)
        axes[idx].set_ylabel("Valor Real", fontsize=10)
    plt.suptitle("Matrices de Confusión en Conjunto de Prueba (Test Set)", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(REPORTES_DIR / "matriz_confusion_modelos.png", dpi=300)
    plt.close()

    # C. Importancia de Características (Feature Importance con Random Forest)
    importancias = pd.Series(best_rf.feature_importances_, index=FEATURES).sort_values(ascending=True)
    plt.figure(figsize=(10, 8))
    importancias.plot(kind="barh", color="#2b5c8f")
    plt.title("Importancia Relativa de Variables — Random Forest", fontsize=13, fontweight="bold")
    plt.xlabel("Gini Importance (Reducción de Impureza)", fontsize=11)
    plt.ylabel("Variable Predictora", fontsize=11)
    plt.grid(axis="x", linestyle="--", alpha=0.7)
    plt.tight_layout()
    plt.savefig(REPORTES_DIR / "importancia_variables_rf.png", dpi=300)
    plt.close()

    log(f"\nOK -> Gráficos y modelos guardados en:")
    log(f"   Modelos serializados: {MODELOS_DIR}")
    log(f"   Reportes y gráficas:  {REPORTES_DIR}")


if __name__ == "__main__":
    main()
