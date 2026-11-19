# 06 — Interfaz y mapa

## Principio

La interfaz es una herramienta de operación: facilita explorar, comparar y decidir, sin confundir una visualización atractiva con evidencia de precisión.

No se fija todavía una identidad visual definitiva. Este documento especifica comportamiento, jerarquía y estados, no un diseño implementado.

## Navegación

### Compartida

- Inicio de sesión.
- Mapa y ranking territorial.
- Consulta y predicción.
- Planificación y planes guardados.

### Administrador IA

- Datos e importaciones.
- Estadísticas del dataset.
- Particiones y experimentos.
- Evaluaciones y modelos publicados.
- Usuarios.

## Pantalla operativa principal

1. **Cabecera:** año, modelo publicado, procedencia y estado del sistema.
2. **Panel de filtros:** departamento, municipio y filtros operativos.
3. **Mapa central:** polígonos municipales, base y destinos seleccionados.
4. **Ficha lateral:** datos del municipio, resultado y elegibilidad.
5. **Tabla vinculada:** ranking, selección y acceso al detalle.

El mapa abre en Cesar, pero el selector y los datos admiten Colombia desde la primera versión.

## Cartografía

- Adoptar geometrías municipales oficiales cuya edición, licencia y procedencia se registren.
- Unir geometrías y datos por DIVIPOLA normalizado, nunca por nombre.
- Comprobar códigos no emparejados y cambios territoriales entre ediciones.
- Conservar geometría de referencia y generar copia simplificada para la web.
- Cargar por departamento inicialmente para reducir peso.
- No depender de un mapa de demostración como fuente de geometrías de producción.
- Mantener la atribución visible del proveedor y de las fuentes.

## Codificación visual

- Escala secuencial para probabilidad estimada.
- Gris para datos insuficientes, con estado textual.
- Contorno o símbolo independiente para selección MILP.
- Leyenda con umbral y significado.
- Hubs con estado diferenciado y explicación de la regla.
- No depender solo de rojo/verde ni del color para comunicar estados.

No llamar “confianza” al porcentaje ni mostrarlo como indicador médico oficial.

## Interacciones

- Clic sobre municipio: ficha; no envío automático de brigada.
- Selección en tabla: enfocar y destacar polígono.
- Cambio de año o modelo: invalidar resultados incompatibles y avisar.
- Base: elegir municipio o introducir coordenadas; mostrar que no identifica necesariamente un hospital.
- Generar plan: validar restricciones, ejecutar y mostrar factibilidad.
- Líneas base-destino: si se dibujan, rotularlas como conexiones geográficas, no rutas viales.

## Comparación de escenarios

Primera mejora propuesta: un mapa con selector A/B y tabla de cambios entre dos planes.

Solo comparar directamente planes con datos, año y modelo compatibles, o mostrar claramente sus diferencias. Indicadores: destinos que entran/salen, brigadas asignadas y distancias geográficas de ida acumuladas. No interpretar esa suma como kilometraje real de una ruta.

## Estados obligatorios

- Carga inicial y progreso de trabajos.
- Sin datos para el filtro.
- Municipio sin geometría o sin predicción elegible.
- Modelo no publicado o incompatible.
- Mapa base no disponible: conservar polígonos cuando sea posible y tabla funcional.
- Error de importación con corrección accionable.
- Solver inviable o interrumpido.
- Sesión vencida y acceso prohibido.

## Accesibilidad y alcance de pantalla

- Tabla equivalente al mapa para consulta y selección mediante teclado.
- Etiquetas explícitas, foco visible y contraste suficiente.
- Formularios con errores junto al campo y resumen de validación.
- Escritorio como escenario principal; paneles apilables o plegables en pantallas pequeñas.
- Ningún botón debe afirmar “despachar” si solo genera una recomendación.

## Disponibilidad

La aplicación se ejecuta localmente, pero el mapa base requiere red. No se promete funcionamiento cartográfico totalmente sin conexión. Tablas, modelos y planes locales deben seguir operativos sin el proveedor externo.
