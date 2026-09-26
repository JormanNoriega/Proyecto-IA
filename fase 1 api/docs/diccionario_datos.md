# Diccionario de datos — `municipio_anio.parquet`

Tabla modelo del **Sistema de Priorización de Brigadas de Salud Extramurales**.
Unidad: **municipio × año** (2017–2021). Llave: **DIVIPOLA** (`cod_mpio`, 5 dígitos).

- Salida: `data/modelo/municipio_anio.csv` (+ `.parquet` si `pyarrow` está disponible)
- Filas: 5.610 (1.122 municipios × 5 años) · Columnas: 57

## Bloque llave
| Columna | Origen | Descripción |
|---|---|---|
| `cod_mpio` | DIVIPOLA | Código municipal (llave) |
| `cod_dpto` | DIVIPOLA | Código departamental |
| `nom_mpio` | DIVIPOLA | Nombre del municipio |
| `a_o` | RIPS | Año (2017–2021) |

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

## Denominador y ruralidad (DANE — serie municipal por área)
| Columna | Descripción |
|---|---|
| `poblacion` | Población total proyectada del municipio (denominador de la brecha) |
| `pct_rural_disperso` | % de población en "Centros Poblados y Rural Disperso" (DANE, 2018) |

> **Fuente = DANE**, archivo `data/raw/PPED-AreaMun-2018-2042_VP.xlsx` (serie municipal por área,
> 2018–2042). El script `etl_05_poblacion.py` lo detecta automáticamente. Como la serie empieza en 2018,
> **los valores de 2017 se completan con los de 2018**. Si el archivo no está, cae a BDUA (afiliados, snapshot).

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
| `banda_pob` | Quintil de población (0 = más pequeño … 4 = más grande) |
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
   **se conservan en la tabla pero se excluyen del ranking** (`prioridad_alta` queda vacío). La brecha
   sigue midiendo **provisión local de servicios**, no cobertura de la población residente.
2. `poblacion` viene de proyecciones DANE; **2017 se aproxima con 2018** (la serie municipal inicia en 2018).
3. **No hay fuga de información** si se usan como predictores el contexto (REPS, étnico, capítulos, ruralidad,
   `banda_pob`) y **no** las intensidades RIPS (`*_1000hab`, `brecha_*`, `consultas`).
4. RIPS descarta los `PROCEDIMIENTOS` del perfil diagnóstico (usan CUPS, no CIE-10) y el sentinel
   `1 - NO DEFINIDO`.
5. `longitud`/`latitud` se omiten: la fuente DIVIPOLA no las trae pobladas.

## Fuentes
| Fuente | ID | Acceso |
|---|---|---|
| RIPS | `4k9h-8qiu` | API SODA v3 |
| DIVIPOLA municipios | `gdxc-w37w` | API SODA v3 |
| REPS | `c36g-9fc2` | API SODA v3 |
| Resguardos 2020 | `epzt-64uw` | API SODA v3 |
| Comunidades fuera de resguardo | `fmd2-kgwe` | API SODA v3 |
| BDUA subsidiado | `d7a5-cnra` | API SODA v3 |
| BDUA contributivo | `tq4m-hmg2` | API SODA v3 |
| Población municipal DANE | `PPED-AreaMun-2018-2042_VP.xlsx` | descarga (`data/raw/`) |
