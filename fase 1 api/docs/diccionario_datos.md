# Diccionario de datos — `municipio_anio.parquet`

Tabla modelo del **Sistema de Priorización de Brigadas de Salud Extramurales**.
Unidad: **municipio × año** (2017–2021). Llave: **DIVIPOLA** (`cod_mpio`, 5 dígitos).

- Salida: `data/modelo/municipio_anio.csv` (+ `.parquet` si `pyarrow` está disponible)
- Filas: 5.610 (1.122 municipios × 5 años) · Columnas: 74

## Bloque llave y georreferenciación (DIVIPOLA `gdxc-w37w`)
| Columna | Origen | Descripción |
|---|---|---|
| `cod_mpio` | DIVIPOLA | Código municipal DANE de 5 dígitos (llave principal) |
| `cod_dpto` | DIVIPOLA | Código departamental de 2 dígitos |
| `nom_mpio` | DIVIPOLA | Nombre oficial del municipio |
| `latitud` | DIVIPOLA | Latitud geográfica decimal (GPS centroide municipal) |
| `longitud` | DIVIPOLA | Longitud geográfica decimal (GPS centroide municipal) |
| `a_o` | RIPS | Año de observación (2017–2021) |
| `split` | Pipeline | Partición para modelado (`train`: 70%, `val`: 15%, `test`: 15%), agrupada por `cod_mpio` |
| `banda_pob` | DANE | Quintil de población (0 = más pequeño … 4 = más grande) |

## Demanda (RIPS `4k9h-8qiu`)
| Columna | Descripción |
|---|---|
| `consultas` | Atenciones de tipo CONSULTAS |
| `procedimientos` | Atenciones de tipo PROCEDIMIENTOS DE SALUD |
| `urgencias` | Atenciones de tipo URGENCIAS |
| `hospitalizaciones` | Atenciones de tipo HOSPITALIZACIONES |
| `atenciones_total` | Suma de los 4 tipos |
| `sin_rips` | true si el municipio-año no tiene registros RIPS |
| `pct_cap_A` … `pct_cap_Z` | Porcentaje de atenciones por capítulo CIE-10 (consulta+urgencias+hospitalización, 2017–2021) |

## Infraestructura (REPS `c36g-9fc2`)
| Columna | Descripción |
|---|---|
| `n_sedes` | Sedes habilitadas de servicios de salud en el municipio |
| `n_sedes_ese` | Sedes de Empresa Social del Estado (públicas) |

## Contexto étnico (Resguardos `epzt-64uw` / Comunidades `fmd2-kgwe`)
| Columna | Descripción |
|---|---|
| `n_resguardos` | Número de resguardos indígenas |
| `pob_resguardos` | Población proyectada en resguardos |
| `n_comunidades` | Comunidades indígenas fuera de resguardo |

## Pobreza y Vulnerabilidad Multidimensional (Censo DANE 2018 — NBI)
| Columna | Descripción |
|---|---|
| `nbi_total` | % de población con Necesidades Básicas Insatisfechas en todo el municipio |
| `nbi_miseria` | % de población en condición de miseria extrema en el municipio |
| `nbi_vivienda` | % de viviendas inadecuadas (materiales precarios) |
| `nbi_servicios` | % de viviendas con servicios inadecuados (sin agua potable/alcantarillado) |
| `nbi_hacinamiento` | % de hogares en hacinamiento crítico (>3 personas por habitación) |
| `nbi_inasistencia` | % de menores en inasistencia escolar |
| `nbi_dependencia` | % de hogares con alta dependencia económica |
| `nbi_rural` | **% de personas con NBI en Centros Poblados y Rural Disperso** (Foco del proyecto) |
| `nbi_rural_miseria` | **% de población rural dispersa en miseria extrema** |
| `nbi_rural_vivienda` | % de viviendas inadecuadas en área rural |
| `nbi_rural_servicios` | % sin agua/saneamiento en área rural dispersa |
| `nbi_rural_hacinamiento` | % hacinamiento en área rural |
| `nbi_rural_inasistencia` | % inasistencia escolar en área rural |
| `nbi_rural_dependencia` | % alta dependencia económica en área rural |

## Denominador y ruralidad (DANE — serie municipal por área)
| Columna | Descripción |
|---|---|
| `poblacion` | Población total proyectada del municipio (denominador de la brecha) |
| `pct_rural_disperso` | % de población en "Centros Poblados y Rural Disperso" (DANE, 2018) |

## Indicadores derivados
| Columna | Fórmula |
|---|---|
| `consultas_1000hab` | `consultas / poblacion × 1000` |
| `urgencias_1000hab` | `urgencias / poblacion × 1000` |
| `hosp_1000hab` | `hospitalizaciones / poblacion × 1000` |
| `proced_1000hab` | `procedimientos / poblacion × 1000` |
| `ratio_consultas_urgencias` | `consultas / urgencias` |
| `sedes_10k_hab` | `n_sedes / poblacion × 10000` |

## Target (ajustado por pares)
El benchmark es la **mediana de la tasa por banda de población** (quintiles), con la tasa *winsorizada* al p99.
Así cada municipio se compara con municipios de tamaño similar y los extremos (hubs) no distorsionan.

| Columna | Descripción |
|---|---|
| `bench_consultas` | Benchmark: mediana de consultas por 1.000 hab de su banda y año |
| `bench_global` | Idem para atenciones totales |
| `brecha_consultas` | **Target principal**: `max(0, 1 − tasa / bench_consultas)`. Mediana 0; >0 = por debajo de su par |
| `brecha_global` | Igual, usando atenciones totales |
| `brecha_nacional` | Versión legacy (benchmark nacional agregado); se conserva para comparar |
| `es_hub` | 1 si la tasa ≥ 3× la mediana de su banda (prestador que sirve área de influencia); 0 si no |
| `prioridad_alta` | 1 si `brecha_consultas` ≥ percentil 66 **y** no es hub; 0 si no; vacío en hubs o sin RIPS |

## Advertencias (leer antes de modelar)
1. **`municipio` en RIPS es la sede del prestador, no la residencia del paciente.** Se mitiga con el
   **benchmark por pares** y marcando los **hubs** (`es_hub = 1`, ≥3× la mediana de su banda). Los hubs
   **se conservan en la tabla pero se excluyen del ranking** (`prioridad_alta` queda vacío).
2. **Coordenadas GPS:** 100% de los municipios tienen `latitud` y `longitud` disponibles para Folium y ruteo MILP.
3. **No hay fuga de información** si se usan como predictores el contexto (REPS, étnico, NBI, capítulos CIE-10, ruralidad,
   `banda_pob`) y **no** las intensidades RIPS directas (`*_1000hab`, `brecha_*`, `consultas`).

## Fuentes
| Fuente | ID / Archivo | Acceso |
|---|---|---|
| RIPS | `4k9h-8qiu` | API SODA v3 |
| DIVIPOLA municipios | `gdxc-w37w` | API datos abiertos |
| REPS | `c36g-9fc2` | API SODA v3 |
| Resguardos 2020 | `epzt-64uw` | API SODA v3 |
| Comunidades fuera de resguardo | `fmd2-kgwe` | API SODA v3 |
| Necesidades Básicas Insatisfechas (NBI) | `CNPV-2018-NBI-DIVIPOLA-2021.xlsx` | Censo DANE 2018 (`data/raw/`) |
| Población municipal DANE | `PPED-AreaMun-2018-2042_VP.xlsx` | Descarga DANE (`data/raw/`) |
