# 08 — Pruebas y ejecución local

## Estado

Los siguientes son criterios y procedimientos previstos. No se han ejecutado pruebas del aplicativo porque todavía no existe implementación.

## Matriz de aceptación

| Caso | Verificación | Resultado esperado |
|---|---|---|
| A01 — RF-01 | Crear registro válido y reiniciar | Registro conservado y consultable |
| A02 — RF-02 | Cargar CSV de varios municipios | Prevalidación y confirmación explícitas |
| A03 — RF-03 | Mezclar filas válidas, duplicados y rangos inválidos | Rechazos identificados, sin incorporación silenciosa |
| A04 — RF-04 | Comparar estadísticas con muestra conocida | Conteos y medidas coinciden |
| A05 — RF-05 | Consultar evaluación de experimento | Métricas ligadas al modelo, umbral y partición correctos |
| A06 — RF-06 | Aplicar filtros de año/departamento | KPI reproducibles con denominadores visibles |
| A07 — RF-07 | Operativo llama endpoint de entrenamiento | 403 y ninguna ejecución creada |
| A08 — RF-08 | Recorrer ciclo de desarrollo y uso operativo | Modelo publicado explícitamente y predicción trazable |
| A09 — Nacional | Importar municipio fuera de Cesar | Se valida y analiza sin cambios estructurales |
| A10 — Inmutabilidad | Importar nuevos datos | Dataset y modelo publicados previos no cambian |
| A11 — Geografía | Cruzar códigos con ceros iniciales | Uniones por código correctas |
| A12 — MILP | Resguardos mínimos mayores que destinos elegibles | Inviabilidad explicada, sin relajación silenciosa |
| A13 — Distancias | Inyectar proveedor de prueba | MILP recibe km sin depender de Haversine internamente |
| A14 — Sin red | Interrumpir acceso al mapa base | Consulta tabular, inferencia y planes siguen disponibles |
| A15 — Recuperación | Reiniciar durante entrenamiento | Trabajo interrumpido visible, no completado falsamente |
| A16 — Propiedad | Usuario intenta consultar plan ajeno | Acceso denegado sin filtrar contenido |

## Pruebas unitarias

- Validación de tipos, rangos, códigos y duplicados.
- Estadística y fórmulas de KPI sobre muestras pequeñas.
- Partición sin municipios compartidos entre conjuntos.
- Imputación y escalado ajustados exclusivamente con entrenamiento.
- Consistencia de predicción manual, por municipio y del optimizador.
- Haversine: distancia cero, simetría y casos conocidos con tolerancia.
- MILP: capacidad, alcance, elegibilidad y cobertura mínima.
- Permisos, expiración de sesión y serialización sin secretos.

## Pruebas de integración

- Importación → confirmación → versión → entrenamiento → evaluación → publicación.
- Transacciones y confirmación idempotente de importaciones.
- Persistencia de planes y referencias al modelo exacto.
- Publicación simultánea con inferencia en curso.
- Exportaciones CSV seguras frente a contenido interpretable como fórmulas.

## Seguridad mínima

- Sin contraseñas o tokens en repositorio, respuestas ni logs.
- Sin carga de pickle/joblib no confiable.
- Límites de archivo, filas, peticiones costosas y concurrencia.
- Errores públicos sin trazas internas.
- Validación de rutas internas y nombres de archivo.
- Sesiones revocables, control CSRF y orígenes explícitos.
- Impedir dejar el sistema sin administrador activo accidentalmente.

## Preparación del entorno

Durante el bloque 1 se deben verificar:

1. Versiones reales de Python y Node soportadas.
2. Instalación de dependencias y compatibilidad de modelos heredados.
3. Archivos de configuración de ejemplo sin secretos.
4. Inicialización de SQLite, migraciones y creación del administrador.
5. Copia controlada de activos iniciales y descarga geográfica con procedencia.
6. Arranque de API y frontend.

No se incluyen comandos ficticios de arranque. Se añadirán al README cuando existan archivos ejecutables y se hayan probado.

## Persistencia y respaldo

`storage/` contiene datos locales y no se versiona. Respaldar coherentemente SQLite y archivos referenciados, con la aplicación detenida o mediante un mecanismo de snapshot consistente. Probar restauración antes de afirmar que existe recuperación.

No basta copiar únicamente el archivo SQLite: los artefactos de datasets, modelos y geometrías también son necesarios.

## Guion de demostración

1. Entrar como administrador.
2. Importar CSV con casos válidos y errores; confirmar solo válidos.
3. Mostrar versión, estadísticas y KPI.
4. Mostrar partición y experimento; ejecutar uno corto si el tiempo lo permite.
5. Consultar validación/prueba y publicar un modelo.
6. Entrar como operativo y comprobar restricciones de acceso.
7. Consultar municipio y predicción sobre el mapa.
8. Generar plan, mostrar restricciones y descargarlo.
9. Reiniciar y recuperar un plan persistido.

Los experimentos largos pueden prepararse antes de la exposición, manteniendo trazabilidad y sin presentar resultados simulados como reales.
