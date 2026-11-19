# 01 — Alcance y requisitos

## Objetivo

Entregar una aplicación local reproducible para gestionar datos municipales, desarrollar y evaluar modelos de clasificación y apoyar la asignación de brigadas de salud.

El resultado es una recomendación territorial para revisión humana. No constituye diagnóstico clínico, orden de despacho ni certificación de necesidad de atención.

## Perfiles

| Acción | Administrador IA | Usuario operativo |
|---|---|---|
| Consultar mapa y predicciones publicadas | Sí | Sí |
| Introducir datos para predicción sin incorporarlos al entrenamiento | Sí | Sí |
| Crear y consultar sus planes operativos | Sí | Sí |
| Registrar/importar datos de desarrollo | Sí | No |
| Consultar estadística del dataset de desarrollo | Sí | No |
| Crear versiones y particiones de datasets | Sí | No |
| Entrenar y evaluar candidatos | Sí | No |
| Publicar o recuperar modelos | Sí | No |
| Crear y desactivar cuentas | Sí | No |

No existe registro público. El usuario operativo solo accede a sus propios planes; el administrador puede consultarlos para soporte y auditoría. Los permisos se verifican en backend.

## Requisitos obligatorios y aceptación

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-01 | Registro individual | Un administrador guarda un municipio-año válido en un borrador de datos y lo recupera tras reiniciar la aplicación. |
| RF-02 | Carga masiva | Un administrador carga un CSV con múltiples filas, revisa su prevalidación y confirma explícitamente la incorporación. JSON no es obligatorio. |
| RF-03 | Validación | Ambos canales aplican las mismas reglas; una fila inválida no entra silenciosamente. El resultado identifica fila, campo y motivo. |
| RF-04 | Estadística descriptiva | El administrador ve conteos, faltantes, distribuciones y medidas descriptivas calculadas para una versión identificada del dataset. |
| RF-05 | Métricas del modelo | Se muestran precision, recall, F1 y métricas complementarias por experimento y conjunto evaluado, sin mezclar validación y prueba. |
| RF-06 | KPI | Se muestran indicadores calculados y definidos: municipios únicos, registros, proporción de faltantes, prioridades estimadas y brigadas asignadas. |
| RF-07 | Perfiles y permisos | Dos cuentas con roles distintos acceden a sus funciones; las peticiones operativas a endpoints administrativos reciben 403. |
| RF-08 | Ciclo de vida IA | Un administrador completa datos → versión → estadísticas → partición → entrenamiento → validación → prueba final → publicación; el operativo usa el modelo publicado. |

Estado inicial de aceptación: **0 de 8 verificados en la nueva aplicación**. Existen activos reutilizables de fases anteriores, pero todavía no integración web.

## Funciones complementarias aprobadas

- Mapa con vista inicial en Cesar y filtros para Colombia.
- Ficha municipal con año de referencia, modelo y salida estimada.
- Asignación MILP configurable y persistencia de planes.
- Proveedor de distancias intercambiable.
- Comparación básica de dos escenarios si el calendario lo permite.

## Fuera del alcance inicial

- OSRM, tráfico y navegación vial.
- Optimización de rutas de múltiples paradas, turnos o capacidades clínicas.
- Seguimiento GPS de brigadas.
- Predicciones a nivel de comunidad con el modelo municipal actual.
- Aplicación móvil nativa, chatbot y registro público.
- Actualización automática de fuentes externas.
- Modificación del informe académico.

## Definición de terminado

Un requisito se considera completado solo si tiene implementación, prueba de aceptación y persistencia cuando corresponda. Las pantallas estáticas y datos simulados no cuentan como cumplimiento funcional.
