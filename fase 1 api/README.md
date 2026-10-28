# Proyecto de Aula IA — Sistema de Priorización de Brigadas de Salud

**Universidad Popular del Cesar (UPC)** — Facultad de Ingenierías y Tecnologías  
Ingeniería de Sistemas e Informática — Grupo 02  
Valledupar, Cesar — 2026

---

## Estructura Modular de Fases

El proyecto está organizado en fases modulares que ejecutan el ciclo completo de la solución:

```text
fase 1 api/
│
├── config/
│   └── fuentes.json                <- Configuración de endpoints de datos abiertos
│
├── data/
│   ├── raw/                        <- Excels oficiales DANE (NBI Censo 2018 y proyecciones)
│   ├── processed/                  <- Tablas normalizadas (DIM, REPS, Resguardos, NBI)
│   └── modelo/                     <- Datasets finales (municipio_anio.csv y .parquet, 74 cols)
│
├── fase 1/                         <- FASE 1: Formulación, Extracción ETL y Exploración (EDA)
│   ├── src/                        <- Pipeline ETL de extracción y limpieza
│   │   ├── etl_00_divipola.py      <- DIVIPOLA con coordenadas GPS al 100%
│   │   ├── etl_01_rips_principal.py<- Extracción de consultas y atenciones
│   │   ├── etl_02_rips_diagnostico.py <- Perfil CIE-10 por departamento
│   │   ├── etl_03_reps.py          <- Infraestructura y sedes ESE
│   │   ├── etl_04_resguardos.py    <- Contexto indígena y resguardos
│   │   ├── etl_05_poblacion.py     <- Demografía y ruralidad DANE
│   │   ├── etl_06_nbi.py           <- Necesidades Básicas Insatisfechas
│   │   └── build_tabla_modelo.py   <- Unión maestra con Split 70/15/15
│   ├── notebooks/
│   │   └── eda_dataset.ipynb       <- Análisis exploratorio visual (36 celdas)
│   └── docs/                       <- Propuesta, diapositivas y diccionario de datos
│
├── fase 2/                         <- FASE 2: Desarrollo, Modelado y Optimización
│   ├── src/
│   │   ├── modelado.py             <- Entrenamiento, GridSearch y evaluación (4 modelos)
│   │   └── optimizacion_milp.py    <- Programación Lineal Entera Mixta (Ruteo MILP)
│   ├── notebooks/
│   │   └── modelado_fase2.ipynb    <- Demostración interactiva de modelado y optimización
│   ├── modelos/                    <- Modelos serializados (.joblib)
│   ├── reportes/                   <- Curvas ROC, matrices de confusión y plan de brigadas
│   └── docs/                       <- Documento técnico de avance (documento.tex y .md)
│
└── logs/                           <- Trazabilidad y registros de ejecución
```

---

## Resultados Clave de la Fase 2

### Comparación de Modelos en Test Set Ciego (15%)

| Modelo | Accuracy | Precision | Recall | F1-Score | ROC-AUC | PR-AUC |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **HistGradientBoosting** | **77.97%** | **74.13%** | 53.79% | **0.6234** | **0.7848** | **0.7414** |
| Random Forest (Optimizado)| 72.83% | 62.11% | 50.90% | 0.5595 | 0.7653 | 0.6803 |
| Regresión Logística | 65.73% | 49.52% | **55.96%** | 0.5254 | 0.6920 | 0.5926 |
| Dummy Baseline | 66.10% | 0.00% | 0.00% | 0.0000 | 0.5000 | 0.3390 |

### Componente Prescriptivo (Optimización MILP)
* Solver: **HiGHS** vía `scipy.optimize.milp`.
* Función objetivo: Maximiza el impacto sobre la vulnerabilidad geográfica minimizando distancias de viaje por carretera.
* Prueba piloto en el **Cesar**: Despacha 4 brigadas desde Valledupar asignando prioritariamente a **Pueblo Bello**, **Becerril**, **Astrea** y **Chimichagua**.
