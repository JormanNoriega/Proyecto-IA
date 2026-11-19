# 07 — Plan de implementación

## Situación inicial

Documentación y directorios creados. No hay servidor, frontend ejecutable ni base de datos inicializada en fase 3.

El plazo de entrega aún no se conoce. Por ello se usan bloques con criterios de salida, no fechas inventadas.

## Bloque 1 — Esqueleto ejecutable, acceso y mapa temprano

- Verificar Python, Node y compatibilidad de artefactos existentes.
- Crear manifiestos y versiones reproducibles de frontend/backend.
- Configuración local, persistencia y migraciones iniciales.
- Inicialización del administrador y sesiones con dos roles.
- Incorporación controlada del dataset y catálogo nacionales.
- Adaptador de inferencia para el modelo heredado, con sus limitaciones visibles.
- Obtener geometrías verificadas y mostrar mapa inicial de Cesar.
- Mostrar probabilidades reales por municipio y tabla equivalente.

**Salida:** iniciar sesión, consultar un municipio y ver una salida trazable al modelo existente. El mapa aparece desde este bloque, no al final.

## Bloque 2 — Datos y estadísticas

- Registro individual y borradores.
- Plantilla CSV, prevalidación y confirmación.
- Errores por fila/campo y descarga de rechazados.
- Snapshot de datasets y checksums.
- Estadísticas y KPI con filtros y denominadores.
- Importar y consultar municipios de departamentos distintos de Cesar.

**Salida:** demostrar RF-01 a RF-04 y KPI de calidad, sin alterar el modelo publicado.

## Bloque 3 — Ciclo de IA reproducible

- Pipeline único de preprocesamiento e inferencia.
- Revisión de etiquetas y variables derivadas.
- Partición y validación cruzada agrupadas por municipio.
- Entrenamiento fuera del ciclo de peticiones, con estados persistidos.
- Comparación con baseline y modelos candidatos.
- Selección/umbral por validación y evaluación final en prueba.
- Publicación explícita, recuperación de versión y auditoría.

**Salida:** completar el recorrido de RF-05 y RF-08; la consulta operativa usa el modelo publicado.

## Bloque 4 — Asignación operativa

- Separar el cálculo de distancias del MILP.
- Implementar proveedor Haversine y validar sus unidades.
- Parámetros de base, brigadas, alcance y cobertura de resguardos.
- Excluir candidatos según reglas operativas explícitas.
- Manejar inviabilidad sin relajar restricciones automáticamente.
- Guardar y exportar planes con metadatos y resultados.
- Mostrar asignación en mapa y tabla.

**Salida:** plan factible o explicación verificable de inviabilidad, con trazabilidad completa.

## Bloque 5 — Aceptación y entrega local

- Ejecutar la matriz de pruebas obligatorias.
- Verificar roles, propiedad, persistencia y errores.
- Preparar instrucciones reales de instalación y ejecución.
- Verificar restauración y reinicio.
- Ensayar demostración con cuentas de ambos roles.

**Salida:** ocho requisitos demostrables y ejecución reproducible.

## Mejora condicionada al tiempo

Comparación A/B de planes guardados. No se introduce antes de asegurar los requisitos obligatorios.

OSRM permanece fuera de esta entrega inicial. La interfaz de distancias es preparación arquitectónica, no compromiso de integrarlo ahora.

## Riesgos y respuesta

| Riesgo | Respuesta |
|---|---|
| Dependencias o artefactos incompatibles | Verificación inicial; reentrenar con entorno controlado si hace falta |
| Geometrías grandes o códigos sin correspondencia | Carga departamental, simplificación y reporte de uniones fallidas |
| Mapa externo no disponible | Tabla y funciones locales siguen utilizables |
| Datos insuficientes para entrenar | Bloqueo explicativo; no generar métricas inventadas |
| Entrenamiento lento | Trabajo separado y progreso; limitar concurrencia local |
| Modelo con bajo recall | Evaluar y comunicar límites; no prometer mejora por cambios de interfaz |
| Plazo corto | Reducir comparación de escenarios y acabado, no permisos ni separación de prueba |

## Control del alcance

Cada bloque debe terminar con pruebas y un commit coherente cuando el usuario solicite versionar. Crear archivos o pantallas no equivale a cerrar requisitos. No modificar fases anteriores para acomodar rutas nuevas.
