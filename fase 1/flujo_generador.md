# Diagrama del flujo de `generar_dataset.py`

Documento de apoyo para entender como interactuan `data/colombia.json` y
`data/parametros.json` para producir `output/dataset_completo.csv` y
`output/dataset_ml.csv`.

---

## 1. Flujo general (`main()`)

```mermaid
flowchart TD
    A["data/colombia.json<br/>departamentos + municipios"] --> C["limpiar_municipios()<br/>quita duplicados"]
    B["data/parametros.json<br/>reglas + priors"] --> D["extraer configuracion<br/>semilla, n, pesos, umbrales, split"]
    D --> E{"¿Deptos de colombia.json ==<br/>claves de parametros.json?"}
    E -- "No" --> X["ValueError<br/>(no encajan los JSON)"]
    E -- "Si" --> F["Probabilidad por departamento<br/>proporcional a su nº de municipios"]
    F --> G["Bucle: n_registros (10000)"]
    G --> H["generar_registro()<br/>una comunidad"]
    H --> I["puntaje_prioridad =<br/>0.35·necesidad + 0.25·acceso<br/>+ 0.20·vulnerabilidad + 0.20·brecha<br/>+ ruido N(0, 6)"]
    I --> J["clasificar() con umbrales<br/>42 / 54 / 66"]
    J --> G
    G --> K["DataFrame + asignar_split()<br/>70 / 15 / 15"]
    K --> L["validar_catalogos()"]
    L --> M["output/dataset_completo.csv<br/>37 columnas"]
    L --> N["output/dataset_ml.csv<br/>29 features + 3 targets"]
```

---

## 2. Construccion de una comunidad (`generar_registro()`)

El registro se genera en orden causal: cada variable depende de las anteriores,
por lo que las combinaciones son coherentes.

```mermaid
flowchart TD
    P["Priors del departamento<br/>(zona, altitud_media, riesgos,<br/>transporte_dominante, prob_indigena,<br/>prob_afro, acceso_vial_base)"] --> G1
    G1["1. Geografia<br/>municipio aleatorio, altitud ~ N(media, sigma),<br/>riesgo_inundacion / deslizamiento"] --> G2
    G2["2. Tipo de comunidad<br/>pesos derivados de prob_indigena / prob_afro"] --> G3
    G3["3. Demografia<br/>poblacion ~ lognormal, menores,<br/>adultos mayores, gestantes, discapacidad"] --> G4
    G4["4. Cadena logistica<br/>distancia ~ gamma × factor transporte<br/>→ acceso_vial → transporte → tiempo_acceso_min"] --> G5
    G5["5. Servicios<br/>agua_potable, alcantarillado,<br/>puesto_salud_cercano"] --> G6
    G6["6. Salud<br/>cobertura_salud, cobertura_vacunacion,<br/>casos_prioritarios, cronicos, alerta"] --> G7
    G7["7. Brigadas y demanda<br/>ultima_brigada_dias, brigadas_ultimos_12m,<br/>conectividad, demanda_insatisfecha, temporada"] --> G8
    G8["8. Indices intermedios (0-100)<br/>necesidad, acceso, vulnerabilidad, brecha"]
```

---

## 3. De los indices al target

```mermaid
flowchart LR
    N["indice_necesidad"] -- "0.35" --> P(("puntaje_prioridad"))
    A["indice_acceso"] -- "0.25" --> P
    V["indice_vulnerabilidad"] -- "0.20" --> P
    R["indice_brecha"] -- "0.20" --> P
    Z["ruido N(0, 6)"] --> P
    P --> C{"clasificar()"}
    C -- "< 42" --> B["BAJA"]
    C -- "42 a <54" --> ME["MEDIA"]
    C -- "54 a <66" --> AL["ALTA"]
    C -- ">= 66" --> CR["CRITICA"]
```

---

## 4. Que aporta cada JSON

| Fuente | Contenido | Se usa en |
|---|---|---|
| `colombia.json` | 32 departamentos con su lista de municipios | Sorteo del departamento y del `municipio` |
| `parametros.json` → `semilla`, `n_registros` | Reproducibilidad y tamaño | `main()` |
| `parametros.json` → `ruido_puntaje` | Desvio del ruido del puntaje | Calculo de `puntaje_prioridad` |
| `parametros.json` → `split` | Proporciones train/val/test | `asignar_split()` |
| `parametros.json` → `prioridad` | Pesos de los 4 indices | Calculo del puntaje |
| `parametros.json` → `clasificacion` | Umbrales 42/54/66 | `clasificar()` |
| `parametros.json` → `catalogos` | Valores validos de las categoricas | `elegir()` y `validar_catalogos()` |
| `parametros.json` → `departamentos` | Priors por departamento | `generar_registro()` |

**Punto clave de acoplamiento:** el conjunto de `departamento` de `colombia.json`
debe ser identico a las claves de `departamentos` en `parametros.json`; si no,
el script aborta con `ValueError`.
