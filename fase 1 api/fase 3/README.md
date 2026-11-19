# Fase 3 — Aplicativo de priorización de brigadas de salud

Aplicación web de apoyo a la planificación territorial que integra gestión de datos, desarrollo de modelos de IA y asignación de brigadas.

## Estado actual

**Prototipo local en desarrollo.** Incluye acceso por roles, exploración territorial, registro e importación operativa con vista previa, versiones de datos, entrenamiento, evaluación y publicación de modelos, predicción manual y planificación con MILP. Consulta las limitaciones abajo antes de interpretar los resultados.

La pantalla de Gestión de datos permite descargar plantillas Excel y CSV y un diccionario, validar y confirmar filas, consultar registros operativos separados y corregirlos con historial. El formulario individual ofrece los mismos 31 campos que la plantilla. En Vista territorial y Jornadas se puede elegir explícitamente entre datos históricos y registros operativos completos, sin mezclarlos. Las estimaciones operativas son exploratorias y no están validadas temporalmente. Los planes guardan una instantánea de los candidatos, fuente, valores y huella del modelo; los planes anteriores no se modifican. Los registros completos también permiten ejecutar explícitamente una **prueba exploratoria** individual con el modelo activo. Se requiere instalar las dependencias actualizadas del backend (`pip install -r requirements.txt`).

En Laboratorio IA, el administrador selecciona registros operativos completos con consultas para crear una versión del dataset. La etiqueta se calcula automáticamente por año con la cohorte operativa disponible: se necesitan al menos 30 registros con consultas y población por cada una de las cinco bandas; se limita la tasa al percentil 99 anual, se calcula la brecha respecto a la mediana de su banda, se excluyen hubs (tasa al menos tres veces la mediana) y se aplica el percentil 2/3 de brecha de ese año. Esta regla anual es una adaptación, no idéntica al umbral global histórico. La versión congela las referencias usadas, etiquetas y huellas. También se rechazan municipios con clasificación histórica de hub no inequívoca. Sin cohorte suficiente no se crea la versión con esa selección. Después se debe entrenar, evaluar y publicar expresamente. Los archivos `../../data/municipios_prueba.csv` y `.xlsx` contienen 150 registros sintéticos, no aptos para decisiones reales.

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
- Se probará OSRM como proveedor vial; Haversine seguirá como alternativa explícita si OSRM no resulta viable. El prototipo actual usa Haversine.
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

Los acuerdos más recientes y el plan de implementación están en [Jornadas, territorio y datos de IA](doc/09_PLAN_JORNADAS_DATOS.md). Hay una primera planificación multibase con Haversine y guardado automático; el asistente completo y las demás funciones propuestas siguen pendientes.

El catálogo se inicializa en SQLite desde `../data/processed/dim_municipio.csv`, copia procesada en fase 1 de [DIVIPOLA gdxc-w37w, DANE](https://www.datos.gov.co/d/gdxc-w37w), licencia CC BY-SA 4.0. Contiene 1.122 entidades, incluidas áreas no municipalizadas e islas; la fecha de corte exacta de la copia local no está verificada. Se conservan el hash y la fecha de importación. No se actualiza automáticamente.

Para registrar una base, puedes introducir coordenadas o seleccionar un punto y confirmarlo. El servidor comprueba departamento y municipio con el MGN 2025 original; las ubicaciones a 100 metros o menos de un límite quedan bloqueadas para revisión. El umbral es provisional y no sustituye una evaluación de precisión. Las bases anteriores aparecen pendientes de revisión sin cambiar sus datos. NIT, dirección, teléfono y contacto son opcionales y visibles para usuarios de la aplicación. El mapa base requiere internet; la geometría y la validación son locales.

El asistente de jornadas selecciona automáticamente el último año disponible en el conjunto asociado al modelo activo y lo identifica como histórico. Permite revisar candidatos, elegir Haversine o el servidor de demostración OSRM, calcular una propuesta y guardarla tras revisión. OSRM requiere internet, envía coordenadas al servicio público y no garantiza disponibilidad ni transitabilidad. La función objetivo es provisional y no está validada para distancias viales. Los puntos del mapa no son rutas ni lugares de atención confirmados.

Los archivos originales del DANE deben permanecer en `data/geography/mgn_2025/originals/`. Para regenerar la auditoría y contornos simplificados, ejecutar desde `backend`: `python -m app.mgn_import`. La aplicación verifica los hashes de los ZIP frente al informe antes de validar. Los metadatos de ambos archivos restringen modificación y distribución sin autorización; permiten productos derivados con citación. No redistribuir los archivos ni derivados sin aclarar las condiciones aplicables con el DANE. Fuente: Departamento Administrativo Nacional de Estadística - DANE, www.dane.gov.co.

En **Planificar brigadas**, seleccionar una fecha, departamento, año de datos y bases registradas con su capacidad. La propuesta se guarda al generarse y presenta asignaciones y recursos sin usar. El límite es de ida en línea recta; no demuestra acceso vial. El objetivo reutiliza provisionalmente la fórmula histórica y no está validado. Los indicadores siguen vinculados a los datos históricos o al dataset del modelo publicado; no representan necesariamente la situación actual. La API anterior `/plans` sigue disponible para compatibilidad y utiliza una sola base.

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

- La vista territorial y el registro de bases muestran contornos simplificados del departamento y del municipio seleccionado; son referencias geoestadísticas, no un deslinde jurídico. La vista territorial incluye todas las bases registradas, aunque las de otros departamentos pueden quedar fuera del encuadre.
- La importación guarda inmediatamente filas válidas con validación básica; todavía no ofrece vista previa, versiones ni validación completa de DIVIPOLA.
- Los registros adicionales se conservan separados hasta crear una versión del dataset; solo se usan para entrenar si cuentan con etiqueta válida y al menos 20 variables predictoras. Las estadísticas de la pantalla de datos siguen siendo del histórico.
- La etiqueta histórica fue construida antes de particionar: las métricas nuevas **pueden contener contaminación** y no constituyen una prueba ciega rigurosa. Se requiere rediseñar la construcción de etiquetas para evaluación confiable.
- Inicialmente se utiliza el modelo heredado de fase 2, cuya demo reemplaza faltantes por cero. Un administrador puede publicar un modelo nuevo con imputación ajustada solo en entrenamiento. Las probabilidades no están calibradas y no son diagnóstico clínico.
- La importación todavía no ofrece previsualización/confirmación ni validación completa de DIVIPOLA; los ocho requisitos aún necesitan verificación integral.
- La planificación usa Valledupar como base fija y distancias Haversine, no rutas viales. La interfaz de proveedor sustituible y comparación de escenarios quedan pendientes.
- El prototipo está diseñado para uso local, no para exposición pública en internet.

La documentación en `doc/` es el plan objetivo; puede describir funciones aún pendientes.
