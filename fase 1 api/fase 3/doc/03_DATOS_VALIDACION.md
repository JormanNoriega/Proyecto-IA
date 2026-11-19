# 03 — Datos, importación y validación

## Unidad de análisis

Cada registro representa un **municipio-año** de Colombia. La clave lógica es `(cod_mpio, a_o)`. La cobertura nacional existe desde el comienzo, aunque el mapa abra en Cesar.

Los códigos DIVIPOLA son texto: municipio de cinco caracteres y departamento de dos. Deben conservarse ceros iniciales y comprobarse contra el catálogo adoptado.

## Dos tipos de entrada

1. **Datos de desarrollo:** registrados por el administrador; pueden integrarse en una nueva versión de dataset tras validar y confirmar.
2. **Datos de predicción:** introducidos por el usuario operativo; se evalúan con el modelo publicado, sin modificar datasets.

Los registros sin etiqueta válida pueden conservarse como datos pendientes o servir para inferencia. No son elegibles automáticamente para entrenamiento supervisado.

## Dataset de referencia

Se parte del dataset de `../data/modelo/` respecto a `fase 3/`, sin modificar el original. Contiene variables de identificación, demografía, NBI, infraestructura, contexto étnico, actividad asistencial y columnas derivadas.

El contrato de variables debe extraerse y contrastarse con `FEATURES` de `fase 2/src/modelado.py` durante la implementación. La selección actual incluye 27 predictores. No se deben inventar variables como cobertura de vacunación si no existen en los datos utilizados.

## Reglas mínimas

| Grupo | Reglas |
|---|---|
| Identificación | Código municipal válido, departamento coherente y año entero soportado |
| Duplicados | Detectar municipio-año repetido en el archivo y frente al borrador destino |
| Población | Valor positivo para operaciones con tasas; conteos no negativos |
| Coordenadas | Latitud entre -90 y 90, longitud entre -180 y 180; revisar pertenencia territorial |
| Porcentajes | Entre 0 y 100, tras confirmar la unidad en el diccionario |
| Infraestructura | Conteos enteros no negativos; sedes ESE no superiores a sedes totales |
| Variables numéricas | Rechazar texto no convertible, infinitos y valores fuera de dominio |
| Faltantes | Diferenciar campo obligatorio, opcional e imputable por el pipeline |
| Etiqueta | `prioridad_alta` solo admite 0/1 o ausencia explícita pendiente |
| Derivadas | Calcular con reglas versionadas; no confiar en valores enviados sin comprobar |

Las reglas de consistencia poblacional y territorial pueden producir advertencias cuando las fuentes no sean directamente comparables. Una advertencia no debe ocultar un error de dominio.

## Proceso de importación

1. Descargar plantilla con campos, unidades y ejemplos.
2. Subir CSV; limitar tamaño y número de filas.
3. Leer como datos, sin ejecutar contenido ni aceptar rutas externas.
4. Normalizar encabezados y tipos de forma documentada.
5. Presentar previsualización con errores y advertencias.
6. Ofrecer descarga de filas rechazadas y sus motivos.
7. Confirmar explícitamente la incorporación de filas válidas.
8. Crear un snapshot versionado cuando el administrador cierre el borrador.

Política inicial: duplicados se rechazan; no se sobrescriben automáticamente. La corrección de un dato existente debe ser explícita y quedar en una nueva versión.

El informe de validación es una **salida funcional de la aplicación**, distinto del informe académico que no se modificará.

## Versionado

Cada versión cerrada es inmutable y registra:

- ID, autor, fecha y descripción.
- Versión de esquema y reglas de validación.
- Archivo interno, checksum y fuentes.
- Registros, municipios, años, faltantes y elegibilidad para entrenamiento.
- Procedencia de etiquetas y transformaciones derivadas.

Importar no entrena, entrenar no publica y publicar no modifica el dataset.

## Etiquetas y prevención de contaminación

La etiqueta histórica deriva de una brecha de consultas respecto a pares poblacionales, no de un diagnóstico clínico confirmado. Su construcción y limitaciones deben mostrarse en el módulo IA.

Antes de reentrenar hay que revisar benchmarks, bandas y umbrales derivados del conjunto completo. Los parámetros aprendidos o de referencia deben ajustarse solo con entrenamiento y congelarse para los demás conjuntos, o documentarse como referencias externas previamente fijadas.

Una predicción nunca debe reutilizarse como etiqueta observada sin una metodología adicional aprobada.

## Estadística y KPI

- Registros y municipios únicos se muestran por separado.
- Estadísticas: media, mediana, dispersión, cuantiles y distribución por año/departamento.
- Faltantes: celdas faltantes / celdas esperadas del conjunto de columnas declarado.
- Aceptación de importación: filas aceptadas / filas procesadas.
- Prioridad: municipios con resultado positivo / municipios elegibles del año filtrado.
- Brigadas asignadas: destinos seleccionados, no personas efectivamente atendidas.

Todos los indicadores muestran filtros, versión y denominador; no se presenta población municipal sumada como cobertura clínica efectiva.
