# Fase 3 — Aplicativo de priorización de brigadas de salud

Aplicación web de apoyo a la planificación territorial que integra gestión de datos, desarrollo de modelos de IA y asignación de brigadas.

## Estado actual

**Prototipo local en desarrollo.** Incluye acceso por roles, mapa de puntos, registro e importación básicos, versiones de datos, entrenamiento, evaluación y publicación de modelos, predicción manual y planificación con MILP. Consulta las limitaciones abajo antes de interpretar los resultados.

Este directorio no modifica los datos, los modelos ni los informes de las fases anteriores. Las decisiones aquí documentadas definen el trabajo de implementación; no representan funcionalidades ya terminadas.

## Alcance aprobado

- Ejecución inicial local con SQLite y persistencia.
- Frontend React + TypeScript.
- Backend FastAPI.
- Mapa MapLibre con mapa base OpenFreeMap, sujeto a revisión de sus condiciones.
- Datos e importación para municipios de toda Colombia; vista inicial centrada en Cesar.
- Dos perfiles con inicio de sesión y sin registro público.
- Datasets y modelos versionados; importar datos no cambia el modelo publicado.
- Reutilización y adaptación de los modelos y el optimizador MILP existentes.
- Distancias Haversine inicialmente; interfaz sustituible por OSRM en una etapa posterior.
- Mapa básico desde las primeras etapas.
- Los ocho requisitos funcionales son obligatorios. Escenarios y mapa no los sustituyen.
- El informe académico existente queda fuera de esta tarea.

## Estructura

```text
fase 3/
├── README.md
├── .gitignore
├── doc/                      # Especificaciones y guía de implementación
├── backend/
│   ├── app/
│   │   ├── api/              # Endpoints y dependencias de acceso
│   │   ├── core/             # Configuración, autenticación y permisos
│   │   ├── db/               # Persistencia y migraciones
│   │   ├── schemas/          # Contratos y validación
│   │   ├── services/         # Casos de uso
│   │   ├── ml/               # Preprocesamiento, entrenamiento e inferencia
│   │   └── geo/              # Geometrías, distancias y optimización
│   └── tests/
├── frontend/
│   ├── public/
│   └── src/
│       ├── app/              # Rutas, sesión y composición
│       ├── components/       # Componentes compartidos
│       ├── features/         # Módulos funcionales
│       ├── services/         # Cliente de API
│       └── styles/
├── storage/
│   ├── database/
│   ├── datasets/
│   ├── models/
│   ├── geography/
│   ├── exports/
│   └── logs/
└── scripts/                  # Inicialización y ejecución local
```

Los archivos `.gitkeep` únicamente conservan directorios vacíos en Git.

## Documentación

Empezar por [el índice de documentación](doc/README.md).

## Activos de referencia

Rutas relativas a este directorio:

- Dataset inicial: `../data/modelo/municipio_anio.csv` y `.parquet`.
- Modelos existentes: `../fase 2/modelos/`.
- Entrenamiento: `../fase 2/src/modelado.py`.
- Consulta: `../fase 2/src/probar_ia.py`.
- Optimización: `../fase 2/src/optimizacion_milp.py`.
- Construcción del dataset: `../fase 1/src/build_tabla_modelo.py`.

Los activos se deben incorporar mediante un proceso explícito de inicialización, sin sobrescribir sus originales.

## Iniciar en Windows

Desde PowerShell, dentro de `fase 3/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python scripts\crear_admin.py
```

Introduce un usuario y contraseña propios. El script solo crea el primer administrador y no establece credenciales predeterminadas. Después inicia el backend:

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

En otra terminal, desde `fase 3/`:

```powershell
cd frontend
npm install
npm run dev
```

Abre la dirección local que muestre Vite, normalmente `http://localhost:5173`. La documentación interactiva de la API está en `http://127.0.0.1:8000/docs`. Desde el panel de administración puedes crear una cuenta operativa.

Para pruebas:

```powershell
cd backend
python -m pytest tests -q
```

Los datos locales se guardan en `storage/`, que está excluido de Git. El mapa base necesita conexión a internet; los datos y el modelo se leen de las fases anteriores.

## Limitaciones conocidas de esta versión

- El mapa presenta **puntos de coordenadas**, no polígonos municipales oficiales.
- La importación guarda inmediatamente filas válidas con validación básica; todavía no ofrece vista previa, versiones ni validación completa de DIVIPOLA.
- Los registros adicionales se conservan separados hasta crear una versión del dataset; solo se usan para entrenar si cuentan con etiqueta válida y al menos 20 variables predictoras. Las estadísticas de la pantalla de datos siguen siendo del histórico.
- La etiqueta histórica fue construida antes de particionar: las métricas nuevas **pueden contener contaminación** y no constituyen una prueba ciega rigurosa. Se requiere rediseñar la construcción de etiquetas para evaluación confiable.
- Inicialmente se utiliza el modelo heredado de fase 2, cuya demo reemplaza faltantes por cero. Un administrador puede publicar un modelo nuevo con imputación ajustada solo en entrenamiento. Las probabilidades no están calibradas y no son diagnóstico clínico.
- La importación todavía no ofrece previsualización/confirmación ni validación completa de DIVIPOLA; los ocho requisitos aún necesitan verificación integral.
- La planificación usa Valledupar como base fija y distancias Haversine, no rutas viales. La interfaz de proveedor sustituible y comparación de escenarios quedan pendientes.
- El prototipo está diseñado para uso local, no para exposición pública en internet.

La documentación en `doc/` es el plan objetivo; puede describir funciones aún pendientes.
