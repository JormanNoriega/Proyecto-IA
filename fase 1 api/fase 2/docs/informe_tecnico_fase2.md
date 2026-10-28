# Informe Técnico de Avance — Segunda Fase (Fase 2)

**SISTEMA DE PRIORIZACIÓN DE BRIGADAS DE SALUD EXTRAMURALES PARA COMUNIDADES INDÍGENAS Y RURALES DISPERSAS**

* **Institución:** Universidad Popular del Cesar (UPC)
* **Facultad:** Facultad de Ingenierías y Tecnologías
* **Programa:** Ingeniería de Sistemas e Informática
* **Asignatura:** Inteligencia Artificial (Grupo 02)
* **Docente:** Tonny Jiménez
* **Autores:** 
  * Jorman David Noriega Dávila
  * Julio César Ríos Maldonado
  * Gabriel Omar Venegas González
* **Ubicación y Año:** Valledupar, Cesar — 2026

---

## 1. Resumen Ejecutivo

Este documento presenta los avances técnicos y metodológicos correspondientes a la **Fase 2 (Desarrollo y Modelado)** del Proyecto de Aula. Se diseñó, implementó y evaluó un sistema híbrido de Inteligencia Artificial que aborda el problema de la asignación empírica e ineficiente de brigadas médicas extramurales en Colombia. 

A partir de un pipeline automatizado de extracción de datos abiertos del Ministerio de Salud (RIPS y REPS), DANE (Censo 2018 NBI y proyecciones poblacionales) y Ministerio del Interior (Resguardos Indígenas), se consolidó un dataset en formato panel de **5.610 observaciones** (1.122 municipios $\times$ 5 años: 2017–2021) con **74 variables**, incluyendo coordenadas GPS oficiales al 100%.

Se implementó una partición estratificada **70% Entrenamiento, 15% Validación y 15% Prueba** agrupada por municipio (`cod_mpio`) para erradicar cualquier fuga de datos temporal. Se entrenaron y compararon cuatro enfoques algorítmicos con ajuste sistemático de hiperparámetros. El modelo **HistGradientBoosting** alcanzó el mejor rendimiento global con un **F1-Score de 0.6234**, **ROC-AUC de 0.7848** y **Accuracy de 77.97%** en el conjunto de prueba ciego. Finalmente, se formuló y resolvió un modelo prescriptivo de **Programación Lineal Entera Mixta (MILP)** con distancias Haversine que genera el plan de despacho óptimo de unidades médicas móviles minimizando costos logísticos y maximizando el impacto sanitario.

---

## 2. Metodología de Datos y Preprocesamiento

### 2.1 Fuentes Oficiales Integradas
* **DIVIPOLA (`gdxc-w37w`):** Catálogo maestro de 1.122 municipios con centroides geográficos (`latitud`, `longitud`) decimales corregidos.
* **RIPS (`4k9h-8qiu`):** Agregación de más de 18 millones de atenciones en consultas, urgencias, hospitalizaciones y procedimientos entre 2017 y 2021, desagregadas en 26 capítulos diagnósticos CIE-10 (`pct_cap_A` a `pct_cap_Z`).
* **REPS (`c36g-9fc2`):** Capacidad fija instalada (sedes habilitadas totales y sedes de la red pública ESE).
* **Contexto Étnico (`epzt-64uw`, `fmd2-kgwe`):** Presencia y población de resguardos indígenas y comunidades fuera de resguardo.
* **Pobreza Multidimensional DANE (Censo 2018):** 14 variables de Necesidades Básicas Insatisfechas, haciendo énfasis en el indicador específico de **Centros Poblados y Rural Disperso** (`nbi_rural`, `nbi_rural_miseria`, `nbi_rural_servicios`).
* **Proyecciones Demográficas DANE (`PPED`):** Población total y porcentaje rural disperso.

### 2.2 Formulación Matemática del Target
Para eliminar el sesgo de escala urbana, se definió un **benchmark relativo por quintiles de población (`banda_pob`)**:
$$\text{tasa} = \frac{\text{consultas}}{\text{población}} \times 1.000$$
$$\text{brecha\_consultas} = \max\left(0, 1 - \frac{\text{tasa}}{\text{mediana}(\text{tasa}_{\text{banda}, \text{año}})}\right)$$

Se aislaron los prestadores de referencia regional (**Hubs**, con tasas $\ge 3\times$ la mediana) excluyéndolos del ranking de brigadas. La clase objetivo binaria se determinó en el percentil 66 de la brecha:
$$\text{prioridad\_alta} = \begin{cases} 1 & \text{si } \text{brecha\_consultas} \ge 0.337 \text{ y } \text{es\_hub} \neq 1 \\ 0 & \text{en otro caso} \end{cases}$$

### 2.3 Partición de Datos (Split 70 / 15 / 15 Agrupado)
Para evitar la autocorrelación intra-municipal entre años consecutivos, la división se ejecutó sobre los identificadores únicos municipales:
* **Train (70%):** 785 municipios (3.925 filas, 3.770 válidas tras excluir hubs).
* **Validation (15%):** 168 municipios (840 filas, 807 válidas).
* **Test (15%):** 169 municipios (845 filas, 817 válidas).

---

## 3. Desarrollo y Comparación de Modelos de Machine Learning

Se evaluaron 4 modelos representativos con calibración de hiperparámetros mediante `GridSearchCV` sobre 3 folds en el conjunto de entrenamiento:

1. **Dummy Baseline:** Clasificador trivial por clase mayoritaria.
2. **Regresión Logística:** Modelo lineal estandarizado con regularización L2 y ponderación de clases balanceada (`class_weight='balanced'`).
3. **Random Forest:** Ensamble de 200 árboles de decisión (`n_estimators=200`, `max_depth=6`, `min_samples_split=2`).
4. **HistGradientBoosting:** Algoritmo basado en árboles de regresión de gradiente con discretización en bins (`learning_rate=0.15`, `max_iter=100`, `max_leaf_nodes=15`, `min_samples_leaf=20`).

### 3.1 Resultados Cuantitativos en el Conjunto de Prueba Ciego (Test Set)

| Modelo Evaluado | Accuracy | Precision | Recall | F1-Score | ROC-AUC | PR-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **HistGradientBoosting** | **0.7797** | **0.7413** | **0.5379** | **0.6234** | **0.7848** | **0.7414** |
| **Random Forest (Optimizado)** | 0.7283 | 0.6211 | 0.5090 | 0.5595 | 0.7653 | 0.6803 |
| **Regresión Logística** | 0.6573 | 0.4952 | 0.5596 | 0.5254 | 0.6920 | 0.5926 |
| **Dummy Baseline (Trivial)** | 0.6610 | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.3390 |

### 3.2 Hallazgos de Modelado
* **Superación del Baseline:** `HistGradientBoosting` incrementó el F1-Score desde 0.0 hasta 0.6234 y el área bajo la curva Precision-Recall (PR-AUC) de 0.3390 a 0.7414.
* **Precisión en Positivos:** Con una precisión de **74.1%**, 3 de cada 4 municipios clasificados en prioridad alta realmente padecen un déficit crítico de salud, minimizando el despilfarro de brigadas en zonas no prioritarias.
* **Importancia de Variables (Gini):** Las variables más determinantes del modelo fueron:
  1. `% Población en Centros Poblados y Rural Disperso` (DANE).
  2. `NBI Rural Disperso` y `Miseria Rural`.
  3. `Sedes de salud por 10.000 habitantes` (Capacidad instalada REPS).
  4. `Población total` y `Población en resguardos indígenas`.
  5. `Capítulo CIE-10 O (Embarazo, parto y puerperio)`: indicador de alta demanda gineco-obstétrica insatisfecha.

---

## 4. Componente Prescriptivo: Optimización MILP de Despacho

Para cumplir con el **Objetivo Específico #4** de la propuesta, se formuló un modelo de **Programación Lineal Entera Mixta (MILP)** que toma las probabilidades continuas generadas por el modelo de IA y calcula el ruteo óptimo para una flota de brigadas médicas.

### 4.1 Formulación Matemática
Sea $x_i \in \{0, 1\}$ la variable binaria que indica si se asigna una brigada móvil al municipio $i$.
$$\max \sum_{i=1}^{N} \left[ P_i \cdot \ln(V_i + 1) - \lambda \cdot d_i \right] \cdot x_i$$
Sujeto a:
$$\sum_{i=1}^{N} x_i \le K \quad (\text{Capacidad de flota disponible})$$
$$\sum_{i \in \mathcal{R}} x_i \ge M \quad (\text{Cobertura obligatoria de municipios con resguardos indígenas})$$
$$d_i \cdot x_i \le D_{\max} \quad (\text{Autonomía máxima de traslado en km})$$

Donde:
* $P_i$: Probabilidad de prioridad alta predicha por el modelo de IA.
* $V_i$: Población vulnerable (rural dispersa + resguardos).
* $d_i$: Distancia ortodrómica (Haversine) en km desde el hospital base.
* $\lambda$: Factor de penalización por costo de combustible y tiempo de traslado ($\lambda = 0.005$).

### 4.2 Demostración Operativa en el Departamento del Cesar
Tomando como base de operaciones la ciudad de **Valledupar** (Hospital Rosario Pumarejo de López: $10.4605^\circ\text{N}, -73.2594^\circ\text{W}$) y una flota de $K = 4$ brigadas móviles, el solver HiGHS generó el siguiente plan de despacho óptimo:

| Municipio Asignado | Probabilidad IA ($P_i$) | Población Vulnerable | Distancia Base | Resguardos | NBI Rural | Asignación Operativa |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Pueblo Bello** | 0.369 | 29.861 hab | 36.1 km | 2 | 86.6% | **Brigada Móvil #1** |
| **Becerril** | 0.458 | 8.160 hab | 84.1 km | 2 | 67.2% | **Brigada Móvil #2** |
| **Astrea** | 0.909 | 10.298 hab | 132.7 km | 0 | 37.5% | **Brigada Móvil #3** |
| **Chimichagua** | 0.750 | 22.329 hab | 146.8 km | 0 | 30.0% | **Brigada Móvil #4** |

*Resultado:* El modelo priorizó de manera balanceada dos zonas de resguardo crítico en la Sierra Nevada y Serranía del Perijá (Pueblo Bello y Becerril) junto a los dos municipios con mayor probabilidad predictiva de desatención ambulatoria del departamento (Astrea y Chimichagua).

---

## 5. Artefactos y Entregables Generados

Todos los productos de la Fase 2 quedaron estructurados en el repositorio:
1. **Script de Modelado:** [fase 1 api/fase 2/src/modelado.py](file:///C:/Users/jorma/Desktop/IA/Proyecto%20IA/fase%201%20api/fase%202/src/modelado.py).
2. **Script de Optimización:** [fase 1 api/fase 2/src/optimizacion_milp.py](file:///C:/Users/jorma/Desktop/IA/Proyecto%20IA/fase%201%20api/fase%202/src/optimizacion_milp.py).
3. **Modelos Serializados:** Archivos `.joblib` en `fase 1 api/fase 2/modelos/`.
4. **Reportes y Gráficas de Alta Calidad (300 DPI):**
   * Curvas ROC: [curva_roc_comparacion.png](file:///C:/Users/jorma/Desktop/IA/Proyecto%20IA/fase%201%20api/fase%202/reportes/curva_roc_comparacion.png).
   * Matrices de Confusión: [matriz_confusion_modelos.png](file:///C:/Users/jorma/Desktop/IA/Proyecto%20IA/fase%201%20api/fase%202/reportes/matriz_confusion_modelos.png).
   * Importancia de Variables: [importancia_variables_rf.png](file:///C:/Users/jorma/Desktop/IA/Proyecto%20IA/fase%201%20api/fase%202/reportes/importancia_variables_rf.png).
   * Métricas Cuantitativas: [metricas_comparacion.json](file:///C:/Users/jorma/Desktop/IA/Proyecto%20IA/fase%201%20api/fase%202/reportes/metricas_comparacion.json).
   * Plan de Asignación: [asignacion_brigadas_optima.csv](file:///C:/Users/jorma/Desktop/IA/Proyecto%20IA/fase%201%20api/fase%202/reportes/asignacion_brigadas_optima.csv).
5. **Notebook Demostrativo Interactivo:** [modelado_fase2.ipynb](file:///C:/Users/jorma/Desktop/IA/Proyecto%20IA/fase%201%20api/fase%202/notebooks/modelado_fase2.ipynb).
6. **Código Fuente del Documento Técnico:** [documento.tex](file:///C:/Users/jorma/Desktop/IA/Proyecto%20IA/fase%201%20api/fase%202/docs/documento.tex).

---

## 6. Conclusiones y Preparación para la Fase 3

La Fase 2 demostró que la combinación de variables de vulnerabilidad territorial (NBI rural y demografía DANE) con datos de prestación médica (RIPS y REPS) permite predecir con una precisión del 74.1% los municipios en situación de abandono asistencial. 

La integración prescriptiva resuelve la brecha entre el nivel macro-municipal y la toma de decisiones sobre el terreno, dejando el proyecto completamente listo para la **Fase 3: Integración de la Interfaz Web (Streamlit/Folium), Despliegue y Video Pitch**.
