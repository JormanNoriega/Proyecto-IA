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

Se implementó una partición **70% Entrenamiento, 15% Validación y 15% Prueba** agrupada por municipio (`cod_mpio`), de modo que ningún municipio del conjunto de prueba fue observado durante el entrenamiento. El conjunto de validación quedó reservado y no se utilizó en esta iteración. Se entrenaron y compararon cuatro enfoques algorítmicos con ajuste sistemático de hiperparámetros. El modelo **HistGradientBoosting** alcanzó el mejor rendimiento global con un **F1-Score de 0.6234**, **ROC-AUC de 0.7848** y **Accuracy de 77.97%** en el conjunto de prueba ciego. Finalmente, se formuló y resolvió un modelo prescriptivo de **Programación Lineal Entera Mixta (MILP)** con distancias Haversine que genera el plan de asignación de unidades médicas móviles maximizando la cobertura de vulnerabilidad y penalizando la distancia recorrida.

---

## 2. Metodología de Datos y Preprocesamiento

### 2.1 Fuentes Oficiales Integradas
* **DIVIPOLA (`gdxc-w37w`):** Catálogo maestro de 1.122 municipios con centroides geográficos (`latitud`, `longitud`) decimales corregidos.
* **RIPS (`4k9h-8qiu`):** Agregación de más de 1.800 millones de atenciones (consultas, procedimientos, urgencias y hospitalizaciones) entre 2017 y 2021, desagregadas en 26 capítulos diagnósticos CIE-10 (`pct_cap_A` a `pct_cap_Z`).
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

> **Nota metodológica.** El test es ciego a nivel municipal, pero la validación cruzada interna de `GridSearchCV` utiliza una partición aleatoria de filas (no agrupada por municipio) y la imputación de medianas se calcula sobre el conjunto completo antes de separar. Ambas prácticas se reconocen como limitaciones y se corrigen en la Fase 3 con `StratifiedGroupKFold` e imputación ajustada solo con train.

---

## 3. Desarrollo y Comparación de Modelos de Machine Learning

Se evaluaron cuatro modelos representativos. El Random Forest y el HistGradientBoosting se calibraron con `GridSearchCV` (3 pliegues, criterio F1-Score) sobre 12 y 24 combinaciones respectivamente; la Regresión Logística se empleó como línea base lineal sin búsqueda de hiperparámetros:

1. **Dummy Baseline:** Clasificador trivial por clase mayoritaria (`strategy='most_frequent'`).
2. **Regresión Logística:** Modelo lineal estandarizado con regularización L2 y ponderación de clases balanceada (`class_weight='balanced'`, `max_iter=1000`).
3. **Random Forest:** Ensamble de bagging optimizado (`n_estimators=200`, `max_depth=6`, `min_samples_split=2`, `class_weight='balanced'`).
4. **HistGradientBoosting:** Boosting de gradiente con discretización en bins (`learning_rate=0.15`, `max_iter=100`, `max_leaf_nodes=15`, `min_samples_leaf=20`).

**Espacio de búsqueda evaluado:**

| Modelo | Malla | Mejor configuración |
| :--- | :--- | :--- |
| Random Forest | `n_estimators` ∈ {100, 200}; `max_depth` ∈ {6, 10, sin límite}; `min_samples_split` ∈ {2, 5}; `class_weight` = balanced | 200 árboles, profundidad 6, `min_samples_split=2` |
| HistGradientBoosting | `learning_rate` ∈ {0.03, 0.08, 0.15}; `max_iter` ∈ {100, 150}; `max_leaf_nodes` ∈ {15, 31}; `min_samples_leaf` ∈ {20, 40} | Tasa 0.15, 100 iteraciones, 15 hojas, 20 muestras mínimas por hoja |

### 3.1 Resultados Cuantitativos en el Conjunto de Prueba Ciego (Test Set)

| Modelo Evaluado | Accuracy | Precision | Recall | F1-Score | ROC-AUC | PR-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **HistGradientBoosting** | **0.7797** | **0.7413** | **0.5379** | **0.6234** | **0.7848** | **0.7414** |
| **Random Forest (Optimizado)** | 0.7283 | 0.6211 | 0.5090 | 0.5595 | 0.7653 | 0.6803 |
| **Regresión Logística** | 0.6573 | 0.4952 | 0.5596 | 0.5254 | 0.6920 | 0.5926 |
| **Dummy Baseline (Trivial)** | 0.6610 | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.3390 |

### 3.2 Hallazgos de Modelado
* **Superación del Baseline:** `HistGradientBoosting` incrementó el F1-Score desde 0.0 hasta 0.6234 y el área bajo la curva Precision-Recall (PR-AUC) de 0.3390 a 0.7414.
* **Precisión y Recall:** Con una precisión de **74.1%**, aproximadamente 3 de cada 4 registros municipio–año clasificados como prioritarios corresponden efectivamente a un déficit crítico. Sin embargo, el recall es de **53.8%**: cerca del 46% de los registros realmente prioritarios no se detectan con el umbral de 0.5, por lo que el modelo debe operar como apoyo a la decisión y no como filtro único.
* **Importancia de Variables (Gini):** El ranking real del Random Forest optimizado es:
  1. `pct_cap_O` — Capítulo CIE-10 O, embarazo, parto y puerperio (0.112).
  2. `pob_resguardos` — Población en resguardos indígenas (0.091).
  3. `nbi_servicios` — Carencias en servicios básicos (0.085).
  4. `nbi_rural_servicios` — Las mismas carencias en rural disperso (0.059).
  5. `pct_cap_A` — Capítulo CIE-10 A, infecciosas y parasitarias (0.049).
  
  Agregadas por bloque, las once variables de NBI concentran ≈42% de la importancia total, los capítulos CIE-10 ≈26%, las variables étnicas ≈12%, geografía y demografía ≈15% y la capacidad instalada REPS ≈5%. `pct_rural_disperso` ocupa el puesto 13 y `sedes_10k_hab` el 21. La importancia Gini no implica causalidad y el modelo empleado para el despacho es el HistGradientBoosting.

### 3.3 Análisis de Errores y Limitaciones
La matriz de confusión del modelo final sobre las 817 observaciones de prueba registra **488 verdaderos negativos, 52 falsos positivos, 128 falsos negativos y 149 verdaderos positivos**. El error dominante son los falsos negativos, coherente con el recall de 53.8%.

Limitaciones identificadas:
* **Validación no utilizada:** el conjunto de validación quedó reservado; no se calibró el umbral de decisión ni se aplicó *early stopping*.
* **CV interna no agrupada:** `GridSearchCV` usa `KFold` simple, por lo que un mismo municipio puede aparecer en entrenamiento y validación de la búsqueda.
* **Imputación global:** las medianas se calculan antes de separar los conjuntos, lo que introduce una fuga leve.
* **Distancia Haversine:** la distancia es ortodrómica, no por carretera.
* **Cobertura temporal:** el panel cubre 2017–2021 y no incorpora años posteriores.
* **Sin restricción presupuestal explícita:** el MILP modela la flota (`K`), la cuota de resguardos (`M`) y la autonomía (`D_max`), pero no un presupuesto monetario.

---

## 4. Componente Prescriptivo: Optimización MILP de Despacho

Para cumplir con el **Objetivo Específico #4** de la propuesta, se formuló un modelo de **Programación Lineal Entera Mixta (MILP)** que toma las probabilidades continuas generadas por el modelo de IA y calcula la asignación óptima para una flota de brigadas médicas.

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

Para el ejercicio piloto se adoptaron $K = 4$ brigadas, $M = 2$ municipios con resguardos como cuota mínima y $D_{\max} = 350$ km de autonomía.

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
1. **Script de Modelado:** [`src/modelado.py`](../src/modelado.py).
2. **Script de Optimización:** [`src/optimizacion_milp.py`](../src/optimizacion_milp.py).
3. **Demo de Consulta por Municipio:** [`src/probar_ia.py`](../src/probar_ia.py).
4. **Modelos Serializados:** Archivos `.joblib` en `fase 2/modelos/`.
5. **Reportes y Gráficas de Alta Calidad (300 DPI):**
   * Curvas ROC: [`reportes/curva_roc_comparacion.png`](../reportes/curva_roc_comparacion.png).
   * Matrices de Confusión: [`reportes/matriz_confusion_modelos.png`](../reportes/matriz_confusion_modelos.png).
   * Importancia de Variables: [`reportes/importancia_variables_rf.png`](../reportes/importancia_variables_rf.png).
   * Métricas Cuantitativas: [`reportes/metricas_comparacion.json`](../reportes/metricas_comparacion.json).
   * Plan de Asignación: [`reportes/asignacion_brigadas_optima.csv`](../reportes/asignacion_brigadas_optima.csv).
6. **Notebook Demostrativo:** [`notebooks/modelado_fase2.ipynb`](../notebooks/modelado_fase2.ipynb).
7. **Documento Técnico:** fuente [`documento.tex`](documento.tex) y versión compilada [`documento.pdf`](documento.pdf).

---

## 6. Conclusiones y Preparación para la Fase 3

La Fase 2 demostró que la combinación de variables de vulnerabilidad territorial (NBI rural y demografía DANE) con datos de prestación médica (RIPS y REPS) permite clasificar los municipios en situación de abandono asistencial con una precisión del 74.1%, un F1-Score de 0.6234 y un ROC-AUC de 0.7848 sobre municipios no observados durante el entrenamiento. El recall de 53.8% delimita el espacio de mejora: el modelo debe operar con revisión humana o con un umbral ajustado.

La integración prescriptiva resuelve la brecha entre el nivel macro-municipal y la toma de decisiones sobre el terreno, dejando el proyecto listo para la **Fase 3: Integración de la Interfaz Web (Streamlit/Folium), Despliegue y Video Pitch**. Las prioridades técnicas para esa etapa son: agrupar la validación cruzada por municipio, calcular la imputación solo con train, calibrar el umbral con el conjunto de validación y reemplazar la distancia Haversine por distancia por carretera si se dispone de un servicio de ruteo.
