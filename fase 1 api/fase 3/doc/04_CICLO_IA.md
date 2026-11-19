# 04 — Ciclo de vida de IA

## Problema actual

El proyecto existente implementa **clasificación binaria** de `prioridad_alta`. La salida probabilística permite ordenar municipios; no convierte el problema en regresión ni en diagnóstico.

Métricas principales: precision, recall, F1, ROC-AUC y PR-AUC. Accuracy y matriz de confusión son complementarias. MAE, RMSE y R² no son los criterios del clasificador actual.

## Flujo obligatorio

```text
Datos validados
  → versión inmutable de dataset
  → exploración y elegibilidad
  → partición reproducible
  → entrenamiento de candidatos
  → selección y umbral con validación
  → evaluación final en prueba
  → publicación explícita
  → predicciones operativas
```

## Particiones

- Distribución objetivo 70/15/15, aproximadamente; puede variar por agrupación.
- Agrupar por `cod_mpio`: todos sus años pertenecen a la misma partición.
- Estratificar cuando sea viable, registrando la estrategia y semilla.
- La validación cruzada interna para hiperparámetros también respeta grupos municipales.
- Comprobar suficientes ejemplos y clases; bloquear entrenamientos inviables con explicación.
- Guardar IDs y checksum de la partición para reproducir experimentos.

Esta separación evalúa generalización a municipios no vistos; no demuestra por sí sola capacidad de pronóstico hacia años futuros.

## Pipeline único

Un solo artefacto o paquete consistente debe incluir:

- Nombres, orden, tipos y unidades de variables.
- Imputador ajustado solo con entrenamiento.
- Transformaciones y escalador cuando corresponda.
- Clasificador.
- Umbral de decisión seleccionado con validación.
- Reglas de elegibilidad y tratamiento de hubs.
- Versiones del entorno y metadatos de entrenamiento.

El mismo procesamiento se usa en entrenamiento, consulta municipal, predicción manual y optimización.

## Adaptaciones necesarias del código anterior

1. Eliminar la diferencia entre imputación por medianas en entrenamiento y cero en inferencia.
2. No calcular medianas sobre entrenamiento + validación + prueba.
3. Usar validación para comparar candidatos y seleccionar el umbral.
4. No elegir modelos por la mejor puntuación del conjunto de prueba.
5. Sustituir la validación cruzada por filas por pliegues agrupados por municipio.
6. Revisar la construcción de etiquetas, benchmarks y bandas para evitar contaminación.
7. Sustituir rutas de salida fijas por artefactos identificados por experimento.

No se alteran los resultados históricos: los experimentos corregidos se registran como nuevos y no se prometen las mismas métricas.

## Reutilización inicial de modelos

Los `.joblib` existentes pueden habilitar una primera demo si su compatibilidad se verifica. Deben identificarse como artefactos heredados, con procedencia y limitaciones del preprocesamiento disponibles.

La aprobación del ciclo de vida requiere después un entrenamiento trazable con el pipeline unificado. No se inventan imputadores ni metadatos ausentes para presentar el modelo heredado como plenamente reproducible.

Solo se cargan artefactos locales confiables. No se habilita importación arbitraria de `.joblib` o pickle por usuarios.

## Evaluación

- Mostrar resultados separados por validación y prueba.
- El umbral se fija antes de la evaluación final.
- Las métricas no definidas se muestran como no disponibles, no como un resultado favorable.
- Revisar desempeño por departamento, ruralidad y contexto indígena si el tamaño muestral permite interpretarlo.
- Evaluar calibración antes de presentar probabilidades como estimaciones confiables.
- Conservar el conjunto de prueba fuera del ajuste; una evaluación histórica consultable no habilita su uso para optimizar.

## Publicación y trazabilidad

- Solo el administrador publica un modelo evaluado y compatible.
- Un único modelo operativo activo inicialmente.
- Cambiar la publicación es una operación atómica y auditada.
- Mantener la versión anterior para recuperación.
- Predicciones y planes registran el modelo concreto utilizado.
- Una ejecución en curso conserva su referencia aunque cambie el modelo activo.
- No mostrar explicaciones de Random Forest como si explicaran automáticamente HistGradientBoosting.

## Límites de interpretación

La variable objetivo representa un criterio derivado de datos históricos. No prueba causalidad ni sustituye evaluación de terreno. Un hub no se clasifica automáticamente como libre de necesidades: su exclusión operativa responde a la regla del proyecto y debe ser visible.
