# 05 — Contrato inicial de API

**Diseño propuesto; endpoints todavía no implementados.** Prefijo: `/api/v1`. FastAPI generará la especificación OpenAPI cuando exista el backend.

## Convenciones

- JSON para operaciones ordinarias; multipart para subir CSV.
- IDs opacos, fechas ISO 8601 y códigos DIVIPOLA como cadenas.
- Paginación y filtros de tablas; límite máximo de resultados.
- Coordenadas GeoJSON en orden `[longitud, latitud]`.
- Distancias en kilómetros; probabilidades entre 0 y 1.
- No devolver rutas internas, hashes de contraseñas ni secretos.
- Las acciones sobre recursos verifican rol y propiedad.

## Endpoints previstos

| Método y ruta | Perfil | Función |
|---|---|---|
| `GET /health` | Público | Estado básico, sin información sensible |
| `POST /auth/login` | Público | Iniciar sesión |
| `POST /auth/logout` | Autenticado | Invalidar sesión |
| `GET /auth/me` | Autenticado | Usuario y rol |
| `POST /users` | Administrador | Crear cuenta sin registro público |
| `PATCH /users/{id}` | Administrador | Cambiar rol o estado con controles |
| `GET /municipalities` | Autenticado | Catálogo y filtros nacionales |
| `GET /geography/municipalities` | Autenticado | Geometrías filtradas/simplificadas |
| `GET /datasets` | Administrador | Listar versiones y borradores |
| `POST /datasets` | Administrador | Crear borrador de dataset |
| `POST /datasets/{id}/records` | Administrador | Validar y registrar una fila en borrador |
| `GET /datasets/{id}/records` | Administrador | Consultar registros paginados |
| `GET /imports/template` | Administrador | Descargar plantilla CSV |
| `POST /imports` | Administrador | Subir y prevalidar CSV para un borrador |
| `GET /imports/{id}` | Administrador | Consultar resumen y estado |
| `GET /imports/{id}/errors` | Administrador | Errores paginados o exportables |
| `POST /imports/{id}/confirm` | Administrador | Incorporar filas válidas una sola vez |
| `POST /datasets/{id}/versions` | Administrador | Cerrar snapshot inmutable |
| `GET /datasets/{id}/statistics` | Administrador | Estadística de versión o borrador identificado |
| `POST /datasets/{id}/splits` | Administrador | Partición de versión cerrada |
| `POST /experiments` | Administrador | Crear trabajo de entrenamiento |
| `GET /experiments/{id}` | Administrador | Estado, configuración y métricas de validación |
| `POST /experiments/{id}/test-evaluation` | Administrador | Evaluación final con configuración congelada |
| `GET /models` | Administrador | Versiones candidatas/publicadas |
| `POST /models/{id}/publish` | Administrador | Publicar o recuperar una versión |
| `GET /models/active` | Autenticado | Metadatos operativos seguros |
| `POST /predictions` | Autenticado | Predecir sin incorporar datos a entrenamiento |
| `GET /priorities` | Autenticado | Salidas para mapa/ranking por año y departamento |
| `GET /kpis` | Autenticado | Indicadores permitidos para el rol |
| `POST /plans` | Autenticado | Crear trabajo de asignación |
| `GET /plans` | Autenticado | Planes visibles según propiedad/rol |
| `GET /plans/{id}` | Autenticado | Estado y resultado persistido |
| `GET /plans/{id}/export` | Autenticado | Descargar resultado CSV |

La comparación básica puede realizarse consultando dos planes; no requiere un servicio separado inicialmente.

## Contrato mínimo de predicción

Entrada: municipio-año existente o valores compatibles con el esquema del modelo. Los dos modos son excluyentes y se validan explícitamente.

Salida:

- ID y versión del modelo.
- Año y procedencia del dato.
- Probabilidad estimada, clase y umbral.
- Estado de elegibilidad y advertencias.

Un municipio sin datos suficientes no recibe automáticamente probabilidad cero.

## Contrato mínimo de planificación

Entrada:

- Departamento y año; candidatos municipales opcionales dentro del ámbito.
- Base operativa con coordenadas validadas.
- Número máximo de brigadas.
- Distancia máxima geográfica de ida desde la base, en kilómetros.
- Mínimo de destinos con resguardos, si aplica.

Salida:

- ID, autor, estado, modelo y snapshot de datos.
- Proveedor de distancias y configuración.
- Estado del solver, factibilidad y restricciones aplicadas.
- Destinos seleccionados, distancias y puntuaciones utilizadas.
- Advertencias y motivos de exclusión.

Inicialmente cada destino seleccionado representa una brigada, con un máximo configurable; el solver no está obligado a gastar todas las brigadas si la función objetivo no lo favorece.

No se amplía silenciosamente el departamento cuando no hay datos ni se relajan restricciones sin confirmación. Una segunda ejecución con restricciones modificadas crea otro plan.

## Errores y trabajos

Formato de error propuesto:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Hay datos que deben corregirse.",
  "details": [
    {"field": "poblacion", "row": 2, "message": "Debe ser positiva."}
  ]
}
```

- `401`: sesión ausente o inválida.
- `403`: permiso insuficiente.
- `404`: recurso inexistente o no visible.
- `409`: conflicto de estado, duplicado o confirmación ya procesada.
- `413`: archivo demasiado grande.
- `422`: entrada inválida.
- `503`: recurso necesario temporalmente no disponible.

Crear un entrenamiento o plan asíncrono devuelve `202` y un ID consultable. La inviabilidad matemática se registra como resultado del trabajo, distinta de un fallo técnico.
