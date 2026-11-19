# Preparación de la referencia geográfica MGN 2025

Estado: **incorporada para el prototipo local**, con las limitaciones descritas. Los bloqueos de registro usan los ZIP originales, no el contorno simplificado.

## Fuentes verificadas

- [Servicio DIVIPOLA MGN 2025](https://geoportal.dane.gov.co/mparcgis/rest/services/Divipola/Serv_DIVIPOLA_MGN_2025/FeatureServer): capa 319, Departamento, campo `DPTO_CCDGO`; capa 317, Municipio, campos `DPTO_CCDGO` y `MPIO_CDPMP` (código concatenado de cinco dígitos).
- La capa municipal declara sistema de origen EPSG:4686 y permite consultar GeoJSON con `outSR=4326`. Debe verificarse también el sistema y la transformación de cada archivo descargado antes de usarlo.
- El [Geoportal DANE](https://geoportal.dane.gov.co/servicios/descarga-y-metadatos/datos-geoestadisticos/?cod=111) anuncia descargas nacionales por nivel para departamento y municipio.
- Las [condiciones generales del Geoportal](https://geoportal.dane.gov.co/acerca-del-geoportal/licencia-y-condiciones-de-uso/) describen licencia Creative Commons y atribución al DANE. Comprobar las condiciones específicas de los archivos y conservar los metadatos antes de distribuirlos.

El MGN es una referencia geoestadística, no una certificación jurídica definitiva de límites.

## Adquisición y auditoría

Los ZIP fueron proporcionados por el usuario desde el Geoportal; contienen Shapefile con `.prj` WGS 84. La auditoría local encontró 33 departamentos y 1.122 entidades municipales, sin diferencias de códigos respecto al catálogo, duplicados, geometrías no poligonales ni geometrías topológicamente inválidas. El informe reproducible y los hashes están en `data/geography/mgn_2025/processed/audit.json`. Se probaron ejemplos en San Andrés y Providencia; esto no demuestra que todas las islas ni fronteras sean adecuadas para cualquier uso.

Los metadatos de ambas capas establecen: «No modificar, no distribuir y no comercializar sin previa autorización expresa y escrita» y permiten generar productos derivados con citación. También limitan los fines de acceso y uso. Estas condiciones específicas requieren aclaración antes de redistribuir originales o derivados, especialmente frente a la licencia general del Geoportal. Se mantienen locales y fuera de Git. Atribución: Departamento Administrativo Nacional de Estadística - DANE, www.dane.gov.co.

El umbral de cercanía es 100 m, provisional, con proyección local azimutal equidistante para medir el punto fronterizo más cercano; no es una garantía de precisión ni una regla jurídica. La frontera exacta se incluye con `covers()` y se bloquea para revisión. Si faltan datos, hay errores de geometría o no coinciden los hashes auditados, se bloquea el registro.

## Auditoría de códigos

Con archivos oficiales GeoJSON completos en EPSG:4326, desde `fase 3/backend`:

```powershell
python -m app.audit_geography "../../data/processed/dim_municipio.csv" "departamentos.geojson" "municipios.geojson" > auditoria_mgn.json
```

El informe identifica códigos faltantes, adicionales, duplicados, geometrías ausentes o no poligonales y hashes SHA-256. La herramienta no comprueba validez topológica, precisión, cobertura de islas ni condiciones de licencia; esas comprobaciones siguen pendientes. No modifica SQLite.

Para regenerar desde los ZIP oficiales, ejecutar `python -m app.mgn_import` desde `fase 3/backend`. Se conserva el original y se genera el contorno simplificado para visualización. Las bases anteriores se evalúan al consultarlas y permanecen pendientes de revisión sin modificar SQLite. No existe todavía un flujo para resolver manualmente una ubicación fronteriza.
