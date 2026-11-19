# 02 — Arquitectura

## Decisiones aprobadas

| Área | Elección | Límite |
|---|---|---|
| Frontend | React + TypeScript | Interfaz; no decide permisos ni ejecuta modelos |
| Backend | FastAPI | Único punto de acceso a datos y casos de uso |
| Persistencia | SQLite | Ejecución local inicial; no se presupone despliegue multiinstancia |
| Mapa | MapLibre GL JS | Renderizado, no cálculo de rutas |
| Fondo cartográfico | OpenFreeMap | Verificar condiciones y atribución antes de integrar |
| IA | scikit-learn + joblib | Reutilización condicionada a compatibilidad y procedencia |
| Optimización | SciPy MILP / HiGHS | Asignación de destinos; no ruteo |
| Distancias | Haversine | Distancia geográfica, no vial |

No se fijan todavía versiones nuevas sin comprobar su compatibilidad. Las versiones declaradas en fases previas también deben verificarse al preparar el entorno.

## Flujo de componentes

```text
Navegador React
  ├── MapLibre → servicio externo de mapa base
  └── API FastAPI
        ├── Autenticación y autorización
        ├── Datos y estadísticas
        ├── Entrenamiento e inferencia
        ├── Geografías y planificación
        ├── SQLite: metadatos y registros operativos
        └── storage/: datasets, modelos, geometrías y exportaciones
```

La caída del mapa base no debe impedir consultar tablas, predicciones ni planes.

## Responsabilidades del backend

- `api/`: transporte HTTP, comprobación de rol y propiedad del recurso.
- `core/`: configuración, sesiones, contraseñas y políticas de seguridad.
- `db/`: tablas, transacciones y migraciones.
- `schemas/`: contratos tipados y validaciones de entrada/salida.
- `services/`: operaciones de negocio y trazabilidad.
- `ml/`: pipeline compartido, experimentos e inferencia.
- `geo/`: geometrías, distancias y adaptación del MILP.

Los scripts anteriores sirven como referencia. No se ejecutarán directamente como endpoints porque escriben resultados en rutas compartidas y mezclan cálculo, carga y presentación.

## Entidades mínimas propuestas

| Entidad | Responsabilidad |
|---|---|
| Usuario | Nombre de acceso, hash de contraseña, rol y estado |
| Sesión | Token opaco almacenado como hash, usuario y expiración |
| Importación | Origen, usuario, estado y resumen de validación |
| Error de importación | Fila, campo, código y mensaje |
| Dataset / versión | Identidad, snapshot inmutable, esquema y checksum |
| Partición | Versión, semilla, estrategia y asignación municipal |
| Experimento | Dataset, partición, algoritmo, parámetros y estado |
| Evaluación | Experimento, conjunto, umbral y métricas |
| Modelo / publicación | Artefacto, metadatos y versión operativa |
| Predicción | Versión usada, entradas, salida y fecha |
| Plan | Autor, entradas, restricciones, distancias, resultado y modelo |
| Evento de auditoría | Actor, acción, recurso, fecha y resultado |

Los datos grandes se conservan en archivos; SQLite mantiene referencias y metadatos. Las referencias deben ser rutas internas controladas, nunca rutas arbitrarias recibidas del cliente.

## Autenticación local

Sesión mediante cookie HttpOnly, expiración y cierre de sesión. Guardar contraseñas con un algoritmo de hash adecuado; nunca texto plano. Proteger operaciones mutables frente a CSRF y restringir orígenes.

El primer administrador se crea mediante script con contraseña suministrada por el operador, sin credenciales predeterminadas versionadas. Al desplegar con HTTPS se debe activar la cookie Secure.

## Interfaz de distancias

Contrato conceptual, aún no implementado:

```text
DistanceProvider.distances_from(base, destinations)
  → proveedor, unidad, distancias, errores_por_destino, metadatos
```

- Unidad interna: kilómetros.
- La primera implementación calcula Haversine.
- El MILP recibe distancias calculadas; no realiza llamadas HTTP.
- Cada plan registra proveedor, coordenadas utilizadas y restricciones.
- Un futuro proveedor OSRM puede sustituir el cálculo sin cambiar la selección MILP.
- Una distancia vial no disponible nunca se reemplaza silenciosamente por Haversine.
- Los errores y destinos inaccesibles deben aparecer antes de confirmar el plan.

## Ejecuciones largas

Entrenamientos y optimizaciones se gestionan como trabajos con ID y estados persistidos: pendiente, ejecutando, completado o fallido. El procesamiento pesado corre fuera del ciclo de peticiones.

Para la primera versión basta un ejecutor local controlado, sin incorporar un broker. Al reiniciar se detectan trabajos interrumpidos y se marcan de forma explícita; no se muestran como completados.
