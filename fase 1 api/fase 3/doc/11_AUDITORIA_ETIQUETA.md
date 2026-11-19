# Auditoría de `prioridad_alta` y carga única

Esta auditoría describe el código histórico; no modifica datos ni afirma que la metodología esté validada para años nuevos. Fuente principal: `fase 1/src/build_tabla_modelo.py`, líneas 62–82 y 105–159.

## Entradas y alcance

La etiqueta se calcula a partir de `cod_mpio`, `a_o`, `poblacion` y `consultas`, entendidas estas últimas como el número de atenciones de tipo `CONSULTAS` de RIPS agregadas para el municipio y año. También requiere observaciones de otros municipios: no puede reconstruirse con un registro aislado. La población ya es un predictor de la plantilla actual; `consultas` no está en ella.

`atenciones_total`, urgencias, hospitalizaciones y procedimientos se usan para otras variables, incluida `brecha_global`, pero no intervienen directamente en `prioridad_alta`. No deben exigirse para esta etiqueta sin otra justificación.

## Cálculo histórico exacto

1. La base cruza el catálogo municipal con todos los años configurados. Agrega por municipio, año y tipo de atención, y suma consultas. El código histórico rellena con cero los RIPS ausentes; por tanto, distingue un marcador `sin_rips`, pero aun así usa ceros en el cálculo posterior.
2. La tasa de consultas es `consultas / poblacion`; población cero se convierte en faltante.
3. `banda_pob` se calcula a escala nacional con la población del **último año configurado**: ordena con `rank(method="first")`, aplica `pd.qcut(..., 5, labels=False)` y asigna las categorías 0–4 a todos los años. Si no hay filas del último año, usa el promedio por municipio. Los empates dependen del orden. Este cálculo utiliza el último año incluso para registros anteriores.
4. Para cada año limita la tasa de consultas por arriba al percentil 99 de todas las tasas de ese año. La referencia de pares es la mediana de las tasas limitadas por cada combinación **año y banda poblacional**.
5. La brecha es `max(0, 1 - tasa_limitada / mediana_grupo)`, redondeada a cuatro decimales. `bench_consultas` guarda la mediana por mil habitantes redondeada a dos decimales.
6. La clasificación de hub usa **la tasa original sin limitar**, dividida por `bench_consultas / 1000` —es decir, utiliza la referencia redondeada—. Si el cociente es al menos 3, `es_hub` es 1; si el cociente no existe, queda faltante.
7. Para calcular el umbral se usan las filas con brecha no nula y `es_hub != 1`. Es un único percentil 2/3 de esas brechas **para todos los municipios y años juntos**, no un umbral separado por año. La etiqueta vale 1 si la brecha redondeada es mayor o igual al umbral, y 0 en caso contrario. Las filas no válidas quedan sin etiqueta.
8. Solo después de crear las etiquetas se divide por municipio en entrenamiento, validación y prueba.

Una mediana de cero, población faltante o cero, tasas faltantes y cocientes indefinidos requieren atención explícita. La implementación histórica usa semántica de pandas/NumPy para valores no finitos y faltantes; no es seguro sustituirla por reglas supuestas.

## Implicaciones para una sola carga

- El formulario y las plantillas actuales contienen los 27 predictores, pero **no contienen `consultas`**. No es posible obtener la etiqueta original solo con los campos actuales.
- `consultas` debería ser un conteo no negativo de atenciones del municipio y año, con significado y cobertura compatibles. Cero observado y dato ausente deben mantenerse distintos; cambiar la imputación histórica a cero sería una decisión metodológica nueva.
- `sedes_10k_hab` puede calcularse como `n_sedes / poblacion × 10.000`, redondeado a dos decimales, cuando ambas entradas estén disponibles y la población sea positiva.
- `banda_pob` no se deduce reproduciblemente de un solo municipio: requiere una población nacional de referencia y decidir año, cobertura, empates y congelación. Recalcularla con años posteriores puede alterar bandas de años anteriores.
- La referencia de consultas requiere un conjunto de comparación por año y banda; el percentil 99 requiere datos del año completo. El código histórico no establece un mínimo de cobertura ni tamaño de grupo: definirlos sería una regla nueva, no una reproducción literal.
- Calcular la etiqueta para un año nuevo usando un solo archivo parcial, o recalcular el umbral global cada vez que entra una fila, puede cambiar etiquetas previas. Debe definirse un conjunto de referencia y congelar su instantánea, regla, parámetros y resultados.

## Evaluación y decisiones antes de automatizar

La construcción histórica usa información colectiva y el último año antes de partir los datos; además, el umbral global incluye todas las filas válidas. Las métricas existentes pueden estar contaminadas y no prueban generalización temporal.

Para una evaluación temporal, definir previamente el corte y ajustar con datos de entrenamiento las referencias que deban aprenderse, incluido el umbral; no usar el año de prueba para elegirlas. Como la etiqueta original usa comparaciones contemporáneas, debe decidirse y documentarse si en despliegue se permitirá calcular referencias del año evaluado como información contextual disponible, y cómo se evaluará esa política. No presentar una adaptación como reproducción exacta de la fórmula histórica.

Decisiones necesarias: población de referencia y cobertura; regla para faltantes y ceros; tamaño mínimo de grupos; tratamiento de referencia cero; ventana y congelación del umbral; disponibilidad temporal de las consultas; y si se permiten etiquetas manuales alternativas. Deben existir estados separados: predictores completos para consulta, etiqueta pendiente por datos/referencia insuficientes, y apto para entrenamiento cuando la etiqueta y sus insumos estén disponibles.

Actualmente Laboratorio IA acepta etiquetas declaradas manualmente. No calcula esta metodología; además, para registros operativos usa la clasificación histórica de hub del municipio. La evaluación actual es por municipio, no temporal, y no compara automáticamente el candidato con el modelo publicado sobre una prueba temporal común.
