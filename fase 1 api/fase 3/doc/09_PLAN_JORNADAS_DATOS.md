# 09 — Plan de jornadas, territorio y datos de IA

**Estado: implementación iniciada.** Existe catálogo local, bases, validación geográfica y asistente de jornadas con consulta histórica, Haversine o prueba OSRM, revisión y guardado explícito. Los datos operativos actuales, las plantillas y las demás funciones descritas como propuestas siguen pendientes. Este documento recoge los acuerdos posteriores al diseño inicial. Ante discrepancias de alcance con los documentos 01–08, prevalece este plan; los contratos técnicos de aquellos documentos deberán actualizarse al implementar cada etapa. No modifica el informe académico ni los activos de las fases anteriores.

## 1. Propósito y límites

La aplicación debe ayudar a un coordinador a proponer asignaciones de brigadas desde una o varias bases hacia municipios de un departamento, con recursos limitados. La IA estima una prioridad municipal; un proveedor geográfico calcula distancias; un optimizador MILP propone asignaciones. La revisión y decisión final son humanas.

La etiqueta histórica `prioridad_alta` se deriva de un criterio del proyecto; no equivale directamente a una necesidad clínica comprobada. Las probabilidades actuales no están calibradas y la construcción histórica de etiquetas puede contaminar la evaluación. No se considera validado el uso para decisiones sanitarias reales.

## 2. Estado actual y cambio previsto

| Tema | Prototipo actual | Plan |
|---|---|---|
| Territorio | Opciones procedentes de los datos operativos asociados al modelo; vista inicial en Cesar | Catálogo DIVIPOLA nacional independiente de la IA |
| Bases | Registro manual y selección de varias bases con capacidad por jornada | Completar verificación geográfica y gestión de bases |
| Planificación | Primera versión MILP multibase; guardado automático al generar | Completar asistente, revisión y trazabilidad |
| Distancia | Haversine de ida | Probar OSRM; alternativa Haversine explícita |
| Datos operativos | Vinculados al histórico o al dataset del modelo publicado | Datos municipales operativos independientes del entrenamiento |
| Incorporación | Formulario e importación CSV básicos; filas válidas se guardan inmediatamente | Formulario completo, Excel/CSV, validación y confirmación |
| Mapa | Puntos municipales, sin contornos departamentales incorporados | Bases, asignaciones, y contorno departamental si se incorpora una fuente adecuada |

La vista actual de nombres de departamentos mejora la presentación, pero no constituye un catálogo nacional independiente. La aplicación no contiene todavía los datos recientes ni las coordenadas de hospitales por el solo hecho de planear estas funciones.

## 3. Catálogo territorial nacional

- Mantener en SQLite un catálogo nacional de departamentos y municipios, con códigos DIVIPOLA como texto para preservar ceros iniciales.
- Reutilizarlo en registro de bases, gestión de datos, vista territorial y planificación. El selector muestra nombres y permite buscar municipios por departamento.
- Un municipio puede existir en el catálogo sin tener indicadores suficientes para inferencia. Mostrar «sin datos suficientes» en lugar de omitirlo o fabricar una predicción.
- Revisar primero las fuentes y archivos usados en fases 1 y 2; adoptar una fuente oficial tras verificar cobertura, edición, vigencia, licencia y reglas de actualización. Conservar origen, fecha de corte, fecha de importación y versión.
- No depender de una consulta externa cada vez que se abra un selector. Definir migración y tratamiento de cambios territoriales históricos antes de actualizar el catálogo.
- El contorno del departamento seleccionado requiere geometrías verificadas, con fuente, licencia y edición documentadas. MapLibre puede dibujarlo, pero el catálogo tabular no aporta por sí solo límites. No confundir contornos departamentales con polígonos municipales.

## 4. Bases operativas y REPS

Una base es un punto real desde el que se pueden enviar brigadas: hospital, sede de salud u otra instalación. Se podrá registrar manualmente en cualquier departamento, no solamente Cesar.

Campos propuestos: nombre, tipo, departamento y municipio, dirección opcional, latitud y longitud, fuente y estado de verificación de coordenadas, estado operativo y código REPS opcional. La ubicación podrá introducirse o seleccionarse en el mapa; validar rangos y advertir incoherencias territoriales. Las coordenadas deben confirmarse antes de usarlas.

Una base registrada no implica disponibilidad automática para una jornada. Las brigadas se declaran por base y por jornada. Mantener historial de cambios sin alterar planes anteriores.

### Catálogo REPS: complemento posterior

El [conjunto REPS c36g-9fc2](https://www.datos.gov.co/d/c36g-9fc2) puede servir para buscar prestadores y sedes candidatas. Los [metadatos consultados](https://www.datos.gov.co/api/views/c36g-9fc2.json) incluyen nombre, códigos, municipio y dirección, pero no exponen campos de latitud y longitud; no usar una dirección o el centro municipal como ubicación exacta sin confirmación. Incluye prestadores de diversas clases, no solo hospitales, y pertenecer al registro no demuestra disponibilidad de brigadas.

Los metadatos consultados indican licencia CC BY-SA 4.0 y un campo de corte de marzo de 2026. Verificar condiciones vigentes, atribución, fecha de corte, esquema y uso de la API antes de importar; distinguir fecha de corte de actualización del portal. No es necesario importar todas las sedes para iniciar. Identificar posibles duplicados por código de habilitación y conservar correcciones locales sin sobrescribirlas silenciosamente.

## 5. Jornada como flujo central

Asistente propuesto:

1. Crear jornada: departamento, fecha de la jornada y fecha de corte de los datos.
2. Seleccionar una o varias bases registradas y verificar sus ubicaciones.
3. Declarar la cantidad de brigadas disponibles en cada base.
4. Consultar las prioridades municipales elegibles, mostrando fuente, período, faltantes y modelo.
5. Seleccionar y calcular distancias con el proveedor disponible.
6. Definir restricciones y ejecutar el MILP.
7. Revisar mapa, asignaciones, municipios excluidos, brigadas sin asignar y advertencias; guardar el plan.

Separar claramente fecha de referencia de los indicadores, fecha de cálculo de la predicción, fecha de cálculo de distancias y fecha de la jornada. Se podrá mantener un modo histórico explícito para demostración; no presentar datos históricos como situación actual.

Los planes deben guardar una instantánea reproducible: usuario, fecha y parámetros de jornada; bases, coordenadas y capacidades; candidatos y razones de exclusión; datos municipales y sus versiones o referencias; modelo y umbral; proveedor, sentido, fecha y resultados de distancias; fórmula y parámetros del optimizador; asignaciones y recursos no utilizados. Cambios posteriores no deben alterar un plan ya guardado.

## 6. Optimización multibase

Reglas acordadas para la primera versión:

- Varias bases por jornada, cada una con su propia capacidad.
- Como máximo una brigada por municipio y jornada.
- Cada brigada atiende como máximo un municipio durante la jornada.
- Una base puede enviar varias brigadas hasta su capacidad y un municipio puede ser atendido desde una base ubicada en él.
- Se pueden dejar brigadas sin asignar. El máximo de una brigada por municipio es una simplificación operativa, no una afirmación sobre necesidad sanitaria.
- La decisión de excluir hubs existente debe revisarse; no se debe excluir automáticamente el municipio de una base.

La formulación prevista utiliza una variable binaria por par base–municipio, límites por capacidad de base y por municipio, restricciones de distancia y demás reglas aprobadas. Los pares sin conexión válida quedan excluidos. Las brigadas pueden identificarse en la salida sin imponer rutas de varias paradas.

La función objetivo combinará prioridad estimada, información poblacional o de vulnerabilidad y costo de desplazamiento, pero **pesos, normalización, unidades, desempates y política de asignación vacía quedan pendientes de diseño y validación**. No llamar población beneficiaria a población de referencia ni prometer cobertura real. Documentar sensibilidad de resultados y permitir comparar escenarios; no reutilizar coeficientes de distancia para duración sin recalibrar.

La implementación multibase reutiliza **provisionalmente** el objetivo anterior: probabilidad × log(1 + población rural dispersa + población de resguardos) − 0,005 × distancia de ida en km. Solo se consideran pares dentro del límite, se permite la solución vacía y los puntajes negativos pueden dejar recursos sin asignar. La misma fórmula se aplica tanto a Haversine como a OSRM y **no está calibrada ni validada para distancias viales**. Pesos, escala y política definitiva siguen pendientes. La API anterior se conserva por compatibilidad y todavía guarda automáticamente; el nuevo asistente genera un borrador y requiere guardar explícitamente después de revisar. La interfaz recupera planes multibase guardados y muestra puntos, no trazados de ruta.

El asistente usa automáticamente el último año disponible para el departamento en el conjunto asociado al modelo activo. Esto no equivale a contar con datos recientes ni independientes del entrenamiento. Muestra el año, el modelo y los municipios sin predicción; si cambian las predicciones entre consulta y cálculo, exige consultarlas de nuevo.

En la revisión del borrador se pueden retirar asignaciones sugeridas y añadir otras desde bases con capacidad disponible. El servidor comprueba unicidad del municipio, capacidad y conexión dentro de la matriz y el límite calculados. El borrador conserva la marca de revisión manual y se guarda explícitamente; los planes ya guardados no se modifican. Los números de brigada mostrados son identificadores visuales de la lista, no identidades de equipos reales.

Recorridos de varios municipios, horarios, duración de atención y jornadas de varios días quedan para una versión posterior; pueden exigir reformular el optimizador.

## 7. Distancias y rutas

- Probar OSRM mediante HTTP desde el backend con una matriz pequeña, por ejemplo dos bases y cinco municipios del Cesar, utilizando coordenadas verificadas.
- Comprobar condiciones vigentes del servidor elegido, límites, disponibilidad, soporte efectivo de `Table` para distancias y duraciones y comportamiento ante rutas inexistentes. El servidor público de demostración no ofrece disponibilidad garantizada y no debe suponerse adecuado para uso institucional.
- Si la prueba resulta viable, usar `Table` para alimentar el MILP y `Route` solo para geometrías de asignaciones seleccionadas. OSRM recibe longitud, latitud; tiempos estimados no son tráfico en tiempo real.
- Conexión sin ruta: marcarla y excluirla de la asignación vial automática. Un fallo del servicio es distinto de una ruta inexistente.
- Si OSRM no resulta práctico o falla, ofrecer Haversine como **modo alternativo explícito**, nunca sustituir silenciosamente una ruta vial. Señalar línea recta y no dibujarla como carretera real.
- Definir antes de implementar si el límite y el costo serán de ida o ida y vuelta; el retorno puede diferir. Las coordenadas municipales representan un punto de referencia y no necesariamente una comunidad rural.
- Guardar proveedor, perfil, sentido, fecha, distancia, duración, coordenadas, versión de datos si está disponible y advertencias. Si se añade caché, definir caducidad e invalidación.
- Las rutas estimadas no confirman transitabilidad, cierres, condiciones climáticas ni acceso fluvial o rural.

Prueba implementada: `Table` del servidor público de demostración `router.project-osrm.org`, perfil driving, con un máximo de 100 puntos y separación mínima entre consultas. El servicio [solo admite uso razonable no comercial y no más de una consulta por segundo](https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server); no tiene garantía de disponibilidad ni debe considerarse infraestructura institucional. Enviar coordenadas a OSRM es explícito. La matriz guarda distancias de ida; conexiones nulas y ajustes a más de 1 km de la red quedan excluidos. Fallos del servicio no activan Haversine automáticamente. No se solicita ni dibuja geometría vial, ni se guardan duraciones o versión de datos OSRM; quedan pendientes.

## 8. Datos operativos y datos para entrenamiento

Mantener separados:

1. **Catálogo territorial:** municipios y departamentos.
2. **Bases operativas:** ubicación de hospitales o puntos de salida y disponibilidad declarada en una jornada.
3. **Indicadores municipales operativos:** registros validados para consulta y planificación.
4. **Datos de entrenamiento:** registros elegibles, con etiqueta y procedencia válidas, agrupados en versiones inmutables.
5. **Predicciones y planes:** resultados vinculados a datos y modelo concretos.

Un registro municipal reciente puede ser elegible para inferencia sin etiqueta, siempre que sea compatible con el modelo y cumpla las reglas de calidad. Importarlo no entrena ni publica automáticamente. Los registros operativos no deben depender de publicar una nueva versión del modelo para poder consultarse.

Se propone seleccionar registros aprobados hasta una fecha de corte, mostrando período y fuente. Al inicio es más prudente trabajar con conjuntos municipales coherentes que mezclar automáticamente los valores más recientes de cada indicador. Si se mezclan períodos o fuentes, documentar fecha y procedencia por indicador y aprobar reglas de compatibilidad. No inferir fechas ni rellenar valores como si fueran observados.

## 9. Registro individual y carga masiva

Ofrecer las mismas reglas de validación para:

1. Formulario individual con variables agrupadas, unidades, ayuda y origen.
2. Plantilla Excel `.xlsx` como formato principal.
3. Plantilla CSV como alternativa para intercambio y automatización.

La plantilla Excel propuesta incluye hojas de registros municipales, instrucciones, diccionario de variables y catálogo territorial. Se pueden añadir listas desplegables y validaciones de hoja, sin sustituir la validación del servidor. La plantilla CSV tendrá instrucciones y diccionario accesibles por separado. Definir formato de fechas, codificación CSV y conservación de ceros iniciales.

Antes de cerrar el esquema, auditar los **27 predictores actuales** en `backend/app/main.py`: nombre, unidad, origen, rango, fecha de referencia, obligatoriedad, elegibilidad y reglas de faltantes. Identificar variables derivadas —por ejemplo banda poblacional y sedes por 10.000 habitantes— y documentar cómo se calculan y verifican; no asumir que puedan capturarse libremente sin coherencia.

Flujo de importación propuesto: descargar plantilla → cargar archivo → validar y previsualizar → mostrar errores, advertencias y duplicados por fila → confirmar explícitamente los registros válidos → guardar resultado trazable. Validar también tamaño, tipo y contenido del archivo, incluidas fórmulas y valores no interpretables; no ejecutar contenido. Definir límites y política de correcciones sin sobrescrituras silenciosas.

Las reglas deben distinguir elegibilidad para inferencia de elegibilidad para entrenamiento. Para aprendizaje supervisado se requiere `prioridad_alta` y procedencia válida; no reutilizar automáticamente predicciones de la propia IA como etiquetas reales. Documentar la metodología para generar o validar etiquetas nuevas antes de incorporarlas al entrenamiento.

## 10. Ciclo de IA y evaluación

El administrador gestiona datos → valida → crea versión inmutable → entrena candidatos → revisa validación → evalúa prueba → decide publicación. La publicación es explícita y no modifica los archivos históricos.

Revisar la construcción de etiquetas y referencias calculadas antes de la partición. La separación actual por municipio evalúa generalización entre municipios, no garantiza validez para años posteriores. Diseñar además una evaluación temporal cuando existan datos y etiquetas posteriores adecuados; mantener una prueba final protegida y documentar cualquier reutilización.

Comprobar consistencia de variables recientes respecto al entrenamiento, faltantes, cambios de distribución y calibración antes de emplear el modelo en un contexto real. Mostrar siempre las limitaciones de la etiqueta y de las probabilidades. Conservar el modelo heredado como tal, sin afirmar que su preprocesamiento reproduce un pipeline moderno.

## 11. Etapas y criterios de aceptación

1. **Auditoría territorial y contrato de datos:** verificar fuentes previas, catálogo DIVIPOLA y 27 variables. Aceptación: procedencia, cobertura, unidades, duplicados y limitaciones documentados.
2. **Catálogo y bases:** selectores nacionales independientes y bases manuales con ubicación confirmada. Aceptación: registrar una base en un municipio sin datos de IA y recuperarla sin conexión externa al catálogo.
3. **Jornada multibase:** capacidades por base, datos seleccionados, MILP y resultados guardados. Aceptación: varias bases, capacidades respetadas, destino único, municipio de base permitido y recursos sin asignar visibles.
4. **Distancias:** probar OSRM y alternativa explícita. Aceptación: diferenciar ruta inexistente de fallo del servicio; no simular vías con línea recta ni perder procedencia.
5. **Datos y plantillas:** formulario, XLSX/CSV, previsualización y confirmación. Aceptación: ambos formatos aplican reglas equivalentes, conservan DIVIPOLA y muestran errores y elegibilidad sin guardar antes de confirmar.
6. **Modelo y evaluación:** separar datos operativos, evaluar temporalmente cuando sea posible y revisar etiquetas. Aceptación: predicción sin reentrenar, etiquetas trazables, métricas y límites explícitos.
7. **Mapa y fuentes adicionales:** contorno departamental y catálogo REPS cuando sus fuentes y licencias se hayan verificado. Aceptación: procedencia visible y ningún establecimiento sin coordenadas confirmadas utilizado como base exacta.

Pruebas transversales: permisos de ambos perfiles, ausencia de datos, datos antiguos, duplicados, importaciones inválidas, municipios sin predicción, coordenadas fuera de rango, planes inviables, rutas no encontradas, servicio caído, límites de capacidad y reproducibilidad de planes guardados. Comprobar interfaz con teclado y tamaños de pantalla distintos.

## 12. Decisiones pendientes

- Fuente y edición definitivas del catálogo DIVIPOLA y de los límites; política de actualización.
- Disponibilidad de fuentes recientes y compatibles para los 27 predictores y construcción de la etiqueta.
- Reglas exactas de elegibilidad, antigüedad y combinación temporal de indicadores.
- Función objetivo, pesos, normalización, política de asignación vacía y restricciones finales.
- Distancia de ida o ida y vuelta, proveedor OSRM, límites y estrategia de despliegue.
- Capacidad disponible, calendario de implementación y criterios de validación con usuarios.
- Tratamiento de casos de acceso no terrestre; Haversine no demuestra accesibilidad.

Estos pendientes no autorizan a inventar datos, etiquetas ni resultados, ni a declarar cumplidos los ocho requisitos sin verificación integral.
