"""Generador de dataset sintetico para priorizacion de brigadas de salud.

Simula comunidades rurales de Colombia y produce dos archivos CSV:

- output/dataset_completo.csv : todas las columnas (auditoria / trazabilidad).
- output/dataset_ml.csv       : 29 features + puntaje_prioridad + prioridad + split,
                                listo para la fase de modelado.

Fuentes de datos (carpeta data/):
- colombia.json  : universo geografico (departamentos -> municipios).
- parametros.json: reglas del simulador (semilla, tamanos, pesos, umbrales,
                   catalogos y priors por departamento).

Uso:
    python generar_dataset.py
"""

import json          # leer los archivos de configuracion (colombia.json, parametros.json)
import sys           # ajustar la codificacion de la salida por consola
from pathlib import Path  # manejo de rutas independiente del sistema operativo

import numpy as np   # generacion aleatoria y operaciones numericas
import pandas as pd  # construccion del DataFrame y escritura de CSV

# En Windows la consola puede no ser UTF-8; esto evita errores al imprimir tildes.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Rutas base del proyecto (relativas a la ubicacion de este script).
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# Columnas que NO deben entrar al dataset de modelado.
# - comunidad_id: es un identificador, no aporta informacion predictiva.
# - indice_*: son los componentes intermedios del puntaje; incluirlos seria
#   "fuga de informacion" (leakage), porque el target se calcula a partir de ellos.
COL_BORRAR_ML = [
    "comunidad_id",
    "indice_necesidad",
    "indice_acceso",
    "indice_vulnerabilidad",
    "indice_brecha",
]

# Columnas objetivo; se colocan al final del dataset de ML por convencion.
ORDEN_TARGETS = ["puntaje_prioridad", "prioridad", "split"]

# Mapeo: columna categorica -> clave del catalogo en parametros.json.
# Se usa para validar que ningun valor generado quede fuera del catalogo.
CATEGORICAS_ESPERADAS = {
    "tipo_comunidad": "tipos_comunidad",
    "acceso_vial": "acceso_vial",
    "transporte_disponible": "transporte",
    "conectividad": "conectividad",
    "temporada": "temporadas",
}


def cargar_json(ruta):
    """Lee un archivo JSON en UTF-8 y devuelve su contenido como objetos Python."""
    with open(ruta, "r", encoding="utf-8") as archivo:
        return json.load(archivo)


def normalizar(probabilidades):
    """Convierte una lista de pesos en probabilidades que suman 1."""
    probabilidades = np.asarray(probabilidades, dtype=float)
    return probabilidades / probabilidades.sum()


def elegir(rng, opciones, probabilidades):
    """Muestrea una opcion del catalogo segun las probabilidades dadas."""
    return rng.choice(opciones, p=normalizar(probabilidades))


def limitar(valor, minimo, maximo):
    """Recorta un valor al rango [minimo, maximo] (equivale a np.clip)."""
    return np.clip(valor, minimo, maximo)


def limpiar_municipios(departamentos):
    """Quita municipios duplicados dentro de cada departamento, preservando el orden."""
    for departamento in departamentos:
        vistos = []
        for ciudad in departamento["ciudades"]:
            if ciudad not in vistos:
                vistos.append(ciudad)
        departamento["ciudades"] = vistos
    return departamentos


def pesos_tipo_comunidad(prob_indigena, prob_afro):
    """Traduce las probabilidades etnicas del departamento en pesos por tipo de comunidad.

    Reglas:
    - Cada probabilidad etnica se limita a [0, 0.70].
    - Si indigena + afro supera 0.85, se reescalan para no dejar sin peso al resto.
    - El "resto" se reparte entre rural dispersa, rural y campesina.
    """
    indigena = min(max(prob_indigena, 0.0), 0.70)
    afro = min(max(prob_afro, 0.0), 0.70)
    if indigena + afro > 0.85:
        factor = 0.85 / (indigena + afro)
        indigena *= factor
        afro *= factor
    resto = 1.0 - indigena - afro
    return {
        "Rural dispersa": resto * 0.45,
        "Rural": resto * 0.30,
        "Indígena": indigena,
        "Afrodescendiente": afro,
        "Campesina": resto * 0.25,
    }


def pesos_acceso_vial(distancia_km, acceso_base):
    """Combina la distancia (realidad del registro) con el prior del departamento.

    Devuelve las opciones y una mezcla 40% distancia + 60% acceso base.
    """
    opciones = ["Bueno", "Regular", "Difícil", "Muy difícil"]

    # Distribucion segun la distancia: a mayor distancia, peor acceso.
    if distancia_km < 15:
        por_distancia = [0.55, 0.30, 0.12, 0.03]
    elif distancia_km < 40:
        por_distancia = [0.20, 0.45, 0.28, 0.07]
    else:
        por_distancia = [0.05, 0.20, 0.45, 0.30]

    # Distribucion segun el prior de acceso del departamento.
    por_base = {
        "Bueno": [0.70, 0.22, 0.06, 0.02],
        "Regular": [0.15, 0.55, 0.25, 0.05],
        "Difícil": [0.05, 0.20, 0.55, 0.20],
        "Muy difícil": [0.02, 0.08, 0.30, 0.60],
    }[acceso_base]

    mezcla = 0.4 * np.asarray(por_distancia) + 0.6 * np.asarray(por_base)
    return opciones, mezcla


def pesos_transporte(acceso_vial, transporte_dominante):
    """Calcula pesos para el medio de transporte disponible.

    Parte de una base uniforme, refuerza el modo dominante del departamento,
    frena los modos poco probables y aumenta "Limitado"/"No disponible" cuando
    el acceso vial es malo.
    """
    opciones = [
        "Terrestre",
        "Terrestre + 4x4",
        "Motocicleta",
        "Fluvial",
        "Fluvial + Terrestre",
        "Marítimo",
        "Limitado",
        "No disponible",
    ]
    pesos = np.full(len(opciones), 0.15)  # base uniforme para todos
    pesos[5] = 0.0  # "Marítimo" parte en 0 (solo aplica donde el prior lo indica)

    # Refuerzo/depresion segun el transporte dominante del departamento.
    if "Fluvial" in transporte_dominante:
        pesos[3] += 3.0
        pesos[4] += 3.0
    else:
        pesos[3] = 0.05
        pesos[4] = 0.05
    if "Marítimo" in transporte_dominante:
        pesos[5] += 4.0
    if "Motocicleta" in transporte_dominante:
        pesos[2] += 2.0
    if "4x4" in transporte_dominante:
        pesos[1] += 1.5
    if transporte_dominante.startswith("Terrestre") and "Fluvial" not in transporte_dominante:
        pesos[0] += 2.0

    # Penalizacion del acceso: a peor via, mas peso a "Limitado"/"No disponible".
    penalizacion = {
        "Bueno": 0.4,
        "Regular": 1.0,
        "Difícil": 2.6,
        "Muy difícil": 4.5,
    }[acceso_vial]
    pesos[6] = penalizacion
    pesos[7] = penalizacion * 0.7
    return opciones, pesos


def pesos_conectividad(zona):
    """Pesos de conectividad (internet/senal) segun la zona geografica."""
    opciones = ["Buena", "Regular", "Baja", "Sin conexión"]
    if zona in ("Amazonía", "Orinoquía"):
        pesos = [0.08, 0.22, 0.40, 0.30]   # zonas mas aisladas
    elif zona == "Pacífica":
        pesos = [0.10, 0.28, 0.37, 0.25]
    elif zona == "Caribe":
        pesos = [0.16, 0.34, 0.32, 0.18]
    else:
        pesos = [0.24, 0.38, 0.28, 0.10]   # Andina: mejor conectividad
    return opciones, pesos


def factor_distancia(transporte_dominante):
    """Multiplicador de la distancia base segun el medio dominante (fluvial aleja mas)."""
    return {
        "Terrestre": 1.0,
        "Terrestre + 4x4": 1.15,
        "Terrestre + Motocicleta": 1.10,
        "Fluvial": 1.55,
        "Fluvial + Terrestre": 1.35,
        "Marítimo": 1.20,
    }.get(transporte_dominante, 1.0)


def factor_familia(tipo_comunidad):
    """Multiplicador demografico (mas menores y gestantes en comunidades etnicas)."""
    return {
        "Indígena": 1.25,
        "Afrodescendiente": 1.15,
        "Rural dispersa": 1.05,
        "Rural": 1.0,
        "Campesina": 1.0,
    }[tipo_comunidad]


def velocidad_por_transporte(rng, transporte):
    """Velocidad promedio (km/h) del viaje segun el medio de transporte."""
    if "Fluvial" in transporte:
        return rng.uniform(10, 30)
    if transporte == "Marítimo":
        return rng.uniform(15, 30)
    if transporte in ("Limitado", "No disponible"):
        return rng.uniform(8, 20)
    return rng.uniform(15, 55)


def generar_registro(rng, i, dep, info, catalogos):
    """Genera una comunidad (un registro completo) para un departamento dado.

    Parametros:
    - rng        : generador aleatorio con semilla fija.
    - i          : indice del registro (para construir comunidad_id).
    - dep        : objeto de colombia.json (departamento + municipios).
    - info       : priors del departamento desde parametros.json.
    - catalogos  : valores permitidos de las variables categoricas.

    El registro sigue un orden causal: geografia -> demografia -> logistica ->
    servicios -> salud -> indices, para que las variables sean coherentes entre si.
    """
    # --- Geografia basica -------------------------------------------------
    municipio = rng.choice(dep["ciudades"])  # municipio aleatorio del departamento
    zona = info["zona"]
    transporte_dominante = info["transporte_dominante"]

    # Riesgos ambientales: prior del departamento + ruido, recortados a [0, 1].
    riesgo_inundacion = round(
        float(limitar(
            info["riesgo_inundacion"] + rng.normal(0, 0.08),
            0,
            1,
        )),
        2,
    )
    riesgo_deslizamiento = round(
        float(limitar(
            info["riesgo_deslizamiento"] + rng.normal(0, 0.08),
            0,
            1,
        )),
        2,
    )

    # Altitud: normal alrededor de la media departamental. El sigma se adapta:
    # en tierras bajas es pequeno, en zonas de montana crece con la altitud.
    altitud_media = info["altitud_media"]
    if altitud_media < 200:
        sigma_altitud = max(8.0, altitud_media * 0.12)
    else:
        sigma_altitud = max(altitud_media * 0.15, 80)
    altitud_msnm = int(
        limitar(
            rng.normal(altitud_media, sigma_altitud),
            0,
            4500,
        )
    )

    # --- Tipo de comunidad (depende de la composicion etnica del depto) ----
    opciones_tc = catalogos["tipos_comunidad"]
    pesos_tc = pesos_tipo_comunidad(
        info["prob_indigena"],
        info["prob_afro"],
    )
    tipo_comunidad = elegir(
        rng,
        opciones_tc,
        [pesos_tc[opcion] for opcion in opciones_tc],
    )

    # --- Demografia -------------------------------------------------------
    # Poblacion con distribucion lognormal (mayoria de comunidades pequenas).
    poblacion_total = int(
        limitar(
            rng.lognormal(mean=5.8, sigma=0.75),
            50,
            5000,
        )
    )

    # Subgrupos como fraccion de la poblacion; algunos escalan por tipo de comunidad.
    factor = factor_familia(tipo_comunidad)
    menores_5 = int(poblacion_total * rng.uniform(0.08, 0.22) * factor)
    adultos_mayores = int(poblacion_total * rng.uniform(0.05, 0.18))
    gestantes = int(poblacion_total * rng.uniform(0.01, 0.05) * factor)
    personas_discapacidad = int(
        poblacion_total * rng.uniform(0.01, 0.08)
    )

    # --- Cadena logistica: distancia -> acceso -> transporte -> tiempo ----
    # La distancia base (gamma) se multiplica por el factor del transporte dominante.
    distancia_km = round(
        float(limitar(
            rng.gamma(shape=2.2, scale=15)
            * factor_distancia(transporte_dominante),
            1,
            180,
        )),
        2,
    )

    # El acceso vial se decide combinando la distancia y el prior del departamento.
    opciones_av, pesos_av = pesos_acceso_vial(
        distancia_km,
        info["acceso_vial_base"],
    )
    acceso_vial = elegir(rng, opciones_av, pesos_av)

    # El transporte disponible depende ya del acceso vial y del modo dominante.
    opciones_tp, pesos_tp = pesos_transporte(
        acceso_vial,
        transporte_dominante,
    )
    transporte = elegir(rng, opciones_tp, pesos_tp)

    # Tiempo = distancia / velocidad, mas una penalizacion por mal acceso vial.
    velocidad_promedio = velocidad_por_transporte(rng, transporte)
    penalizacion_tiempo = {
        "Bueno": 1.0,
        "Regular": 1.15,
        "Difícil": 1.4,
        "Muy difícil": 1.8,
    }[acceso_vial]
    tiempo_acceso_min = round(
        float((distancia_km / velocidad_promedio) * 60 * penalizacion_tiempo),
        2,
    )

    # --- Servicios basicos (probabilidad segun tipo de comunidad) ---------
    prob_agua = {
        "Rural dispersa": 0.45,
        "Rural": 0.65,
        "Indígena": 0.40,
        "Afrodescendiente": 0.55,
        "Campesina": 0.60,
    }
    prob_alcantarillado = {
        "Rural dispersa": 0.20,
        "Rural": 0.40,
        "Indígena": 0.15,
        "Afrodescendiente": 0.30,
        "Campesina": 0.35,
    }
    agua_potable = int(
        rng.random() < prob_agua[tipo_comunidad]
    )
    alcantarillado = int(
        rng.random() < prob_alcantarillado[tipo_comunidad]
    )

    # Puesto de salud: mas probable en zonas Andina/Caribe y a poca distancia.
    if zona in ("Andina", "Caribe"):
        umbral_puesto = 20
        prob_puesto = 0.70
        ajuste_cobertura = 0.0
    else:
        umbral_puesto = 15
        prob_puesto = 0.55
        ajuste_cobertura = -8.0
    puesto_salud_cercano = int(
        distancia_km < umbral_puesto
        and rng.random() < prob_puesto
    )

    # --- Indicadores de salud ---------------------------------------------
    # Las coberturas bajan con la distancia y con la dificultad de acceso.
    penal_distancia = min(distancia_km / 180, 1) * 10
    penal_acceso = {
        "Bueno": 0.0,
        "Regular": 3.0,
        "Difícil": 6.0,
        "Muy difícil": 10.0,
    }[acceso_vial]
    cobertura_salud_pct = round(
        float(limitar(
            rng.normal(
                78 - penal_distancia - penal_acceso + ajuste_cobertura,
                10,
            ),
            35,
            98,
        )),
        2,
    )
    cobertura_vacunacion_pct = round(
        float(limitar(
            rng.normal(
                73 - penal_distancia * 0.8 - penal_acceso * 0.7
                + ajuste_cobertura,
                13,
            ),
            25,
            98,
        )),
        2,
    )

    # Casos prioritarios: Poisson con lambda proporcional a la poblacion,
    # aumentada por riesgo de inundacion y por baja vacunacion.
    factor_cobertura = 1 + max(0.0, 85 - cobertura_vacunacion_pct) / 100
    lam_casos = (
        max(0.5, poblacion_total / 300)
        * (1 + 0.4 * info["riesgo_inundacion"])
        * factor_cobertura
    )
    casos_prioritarios_30d = int(rng.poisson(lam=lam_casos))

    # Cronicos: alta prevalencia en adultos mayores, baja en el resto.
    enfermedades_cronicas = int(
        adultos_mayores * rng.uniform(0.35, 0.65)
        + (poblacion_total - adultos_mayores) * rng.uniform(0.02, 0.06)
    )

    # Alerta epidemiologica: probabilidad base que sube con riesgo de inundacion.
    prob_alerta = 0.08 + 0.05 * info["riesgo_inundacion"]
    alerta_epidemiologica = int(rng.random() < prob_alerta)

    # --- Historial de brigadas --------------------------------------------
    # Menos brigadas y mas tiempo desde la ultima cuando el acceso es dificil.
    penalizacion_brigada = {
        "Bueno": 0.0,
        "Regular": 0.2,
        "Difícil": 0.5,
        "Muy difícil": 0.9,
    }[acceso_vial]
    ultima_brigada_dias = int(
        limitar(
            rng.exponential(scale=130 * (1 + penalizacion_brigada)),
            0,
            730,
        )
    )

    lam_brigadas = 1.5 * {
        "Bueno": 1.2,
        "Regular": 1.0,
        "Difícil": 0.7,
        "Muy difícil": 0.45,
    }[acceso_vial]
    brigadas_ultimos_12m = int(
        limitar(rng.poisson(lam=lam_brigadas), 0, 8)
    )

    # Conectividad segun zona.
    opciones_con, pesos_con = pesos_conectividad(zona)
    conectividad = elegir(rng, opciones_con, pesos_con)

    # Demanda insatisfecha: sube con mal acceso vial y mala conectividad.
    demanda_extra = 0.0
    if acceso_vial in ("Difícil", "Muy difícil"):
        demanda_extra += 8.0
    if conectividad in ("Baja", "Sin conexión"):
        demanda_extra += 5.0
    demanda_insatisfecha_pct = round(
        float(limitar(
            rng.normal(30 + demanda_extra, 15),
            2,
            90,
        )),
        2,
    )

    # Temporada: mas probabilidad de lluvias si el riesgo de inundacion es alto.
    prob_lluvias = 0.30 + 0.25 * info["riesgo_inundacion"]
    temporada = elegir(
        rng,
        catalogos["temporadas"],
        [
            (1 - prob_lluvias) * 0.57,
            prob_lluvias,
            (1 - prob_lluvias) * 0.43,
        ],
    )

    # --- Indices intermedios (0-100) --------------------------------------
    # NECESIDAD: falta de vacunacion + casos por 1000 hab + cronicos + alerta.
    indice_necesidad = (
        (100 - cobertura_vacunacion_pct) / 100 * 30
        + min(casos_prioritarios_30d / max(poblacion_total, 1) * 1000 * 4, 30)
        + min(
            enfermedades_cronicas / max(poblacion_total, 1) * 100,
            20,
        )
        + (20 if alerta_epidemiologica else 0)
    )
    indice_necesidad = float(limitar(indice_necesidad, 0, 100))

    # ACCESO: distancia + tiempo + dificultad vial + escasez de transporte.
    indice_acceso = (
        min(distancia_km / 2, 45)
        + min(tiempo_acceso_min / 5, 30)
        + {
            "Bueno": 0,
            "Regular": 8,
            "Difícil": 15,
            "Muy difícil": 25,
        }[acceso_vial]
        + (8 if transporte == "Limitado" else 0)
        + (15 if transporte == "No disponible" else 0)
    )
    indice_acceso = float(limitar(indice_acceso, 0, 100))

    # VULNERABILIDAD: proporcion de poblacion vulnerable + falta de agua/alcantarillado.
    poblacion_vulnerable = (
        menores_5 + adultos_mayores + gestantes + personas_discapacidad
    )
    porcentaje_vulnerable = (
        poblacion_vulnerable / poblacion_total
    ) * 100
    indice_vulnerabilidad = limitar(
        porcentaje_vulnerable / 55 * 70,
        0,
        70,
    )
    if agua_potable == 0:
        indice_vulnerabilidad += 15
    if alcantarillado == 0:
        indice_vulnerabilidad += 15
    indice_vulnerabilidad = float(
        limitar(indice_vulnerabilidad, 0, 100)
    )

    # BRECHA: tiempo sin brigada + demanda insatisfecha + falta de puesto de salud.
    indice_brecha = (
        min(ultima_brigada_dias / 8, 40)
        + demanda_insatisfecha_pct * 0.4
        + (20 if puesto_salud_cercano == 0 else 0)
    )
    indice_brecha = float(limitar(indice_brecha, 0, 100))

    # Se devuelve el registro como diccionario. "_indices" es temporal: main() lo
    # extrae para calcular el puntaje y luego lo elimina antes de exportar.
    return {
        "comunidad_id": f"COM-{i + 1:05d}",
        "departamento": dep["departamento"],
        "municipio": municipio,
        "zona_geografica": zona,
        "tipo_comunidad": tipo_comunidad,
        "altitud_msnm": altitud_msnm,
        "poblacion_total": poblacion_total,
        "menores_5": menores_5,
        "adultos_mayores": adultos_mayores,
        "gestantes": gestantes,
        "personas_discapacidad": personas_discapacidad,
        "distancia_km": distancia_km,
        "tiempo_acceso_min": tiempo_acceso_min,
        "acceso_vial": acceso_vial,
        "transporte_disponible": transporte,
        "agua_potable": agua_potable,
        "alcantarillado": alcantarillado,
        "puesto_salud_cercano": puesto_salud_cercano,
        "cobertura_salud_pct": cobertura_salud_pct,
        "cobertura_vacunacion_pct": cobertura_vacunacion_pct,
        "casos_prioritarios_30d": casos_prioritarios_30d,
        "enfermedades_cronicas": enfermedades_cronicas,
        "alerta_epidemiologica": alerta_epidemiologica,
        "ultima_brigada_dias": ultima_brigada_dias,
        "brigadas_ultimos_12m": brigadas_ultimos_12m,
        "demanda_insatisfecha_pct": demanda_insatisfecha_pct,
        "conectividad": conectividad,
        "temporada": temporada,
        "riesgo_inundacion": riesgo_inundacion,
        "riesgo_deslizamiento": riesgo_deslizamiento,
        "indice_necesidad": round(indice_necesidad, 2),
        "indice_acceso": round(indice_acceso, 2),
        "indice_vulnerabilidad": round(indice_vulnerabilidad, 2),
        "indice_brecha": round(indice_brecha, 2),
        "_indices": (
            indice_necesidad,
            indice_acceso,
            indice_vulnerabilidad,
            indice_brecha,
        ),
    }


def clasificar(puntaje, umbrales):
    """Convierte el puntaje (0-100) en la etiqueta ordinal de prioridad.

    Umbrales definidos en parametros.json -> clasificacion (baja/media/alta).
    """
    if puntaje < umbrales["baja"]:
        return "BAJA"
    if puntaje < umbrales["media"]:
        return "MEDIA"
    if puntaje < umbrales["alta"]:
        return "ALTA"
    return "CRÍTICA"


def asignar_split(rng, n, proporciones):
    """Asigna aleatoriamente cada fila a train/val/test segun las proporciones."""
    etiquetas = np.array(["train", "val", "test"])
    probabilidades = np.array([
        proporciones["train"],
        proporciones["val"],
        proporciones["test"],
    ])
    # Se normaliza por si las proporciones no suman exactamente 1.
    return rng.choice(etiquetas, size=n, p=probabilidades / probabilidades.sum())


def validar_catalogos(df, catalogos):
    """Verifica que ninguna variable categorica tenga valores fuera de catalogo.

    Si aparece un valor inesperado, lanza un error para detectar el problema
    antes de exportar.
    """
    problemas = []
    for columna, clave in CATEGORICAS_ESPERADAS.items():
        permitidos = set(catalogos[clave])
        inesperados = set(df[columna]) - permitidos
        if inesperados:
            problemas.append(f"{columna}: {sorted(inesperados)}")
    if problemas:
        raise ValueError(
            "Valores fuera de catalogo: " + "; ".join(problemas)
        )


def resumen_indice(serie):
    """Devuelve una linea de texto con estadisticos de un indice (para el log)."""
    saturados = (serie >= 99.5).mean() * 100  # % de valores pegados al maximo
    return (
        f"min={serie.min():6.2f} max={serie.max():6.2f} "
        f"avg={serie.mean():6.2f} p50={serie.median():6.2f} "
        f"saturados(>=99.5)={saturados:5.1f}%"
    )


def main():
    """Orquesta todo el proceso: cargar config -> generar registros -> exportar."""
    # 1) Cargar las dos fuentes de datos.
    territorios = limpiar_municipios(
        cargar_json(DATA_DIR / "colombia.json")
    )
    parametros = cargar_json(DATA_DIR / "parametros.json")

    # 2) Extraer la configuracion del simulador.
    semilla = parametros["semilla"]
    n_registros = parametros["n_registros"]
    pesos_prioridad = parametros["prioridad"]
    umbrales = parametros["clasificacion"]
    catalogos = parametros["catalogos"]
    info_deps = parametros["departamentos"]
    ruido_puntaje = parametros["ruido_puntaje"]
    proporciones_split = parametros["split"]

    # Generador aleatorio con semilla fija -> resultados reproducibles.
    rng = np.random.default_rng(semilla)

    # 3) Validar que los dos JSON "encajen": los departamentos de colombia.json
    #    deben coincidir exactamente con las claves de parametros.json.
    nombres_json = {dep["departamento"] for dep in territorios}
    nombres_param = set(info_deps)
    if nombres_json != nombres_param:
        faltan = nombres_json - nombres_param
        sobran = nombres_param - nombres_json
        raise ValueError(
            f"parametros.json no coincide con colombia.json. "
            f"Faltan: {sorted(faltan)} Sobran: {sorted(sobran)}"
        )

    # 4) Probabilidad de elegir cada departamento, proporcional a su n de municipios.
    conteo_municipios = np.array(
        [len(dep["ciudades"]) for dep in territorios],
        dtype=float,
    )
    probabilidad_dep = conteo_municipios / conteo_municipios.sum()

    # 5) Generar los registros uno por uno.
    registros = []
    for i in range(n_registros):
        idx = rng.choice(len(territorios), p=probabilidad_dep)
        dep = territorios[idx]
        info = info_deps[dep["departamento"]]
        registro = generar_registro(rng, i, dep, info, catalogos)

        # Extraer los indices intermedios (se usan aqui y no se exportan).
        (
            indice_necesidad,
            indice_acceso,
            indice_vulnerabilidad,
            indice_brecha,
        ) = registro.pop("_indices")

        # Puntaje = suma ponderada de los indices + ruido gaussiano controlado.
        puntaje_prioridad = (
            indice_necesidad * pesos_prioridad["peso_necesidad"]
            + indice_acceso * pesos_prioridad["peso_acceso"]
            + indice_vulnerabilidad * pesos_prioridad["peso_vulnerabilidad"]
            + indice_brecha * pesos_prioridad["peso_brecha"]
            + rng.normal(0, ruido_puntaje)
        )
        puntaje_prioridad = round(
            float(limitar(puntaje_prioridad, 0, 100)),
            2,
        )

        registro["puntaje_prioridad"] = puntaje_prioridad
        registro["prioridad"] = clasificar(
            puntaje_prioridad,
            umbrales,
        )
        registros.append(registro)

    # 6) Construir el DataFrame y asignar el split aleatorio.
    df = pd.DataFrame(registros)
    df["split"] = asignar_split(rng, len(df), proporciones_split)

    # 7) Validar que las categoricas respeten los catalogos.
    validar_catalogos(df, catalogos)

    # 8) Definir rutas de salida.
    OUTPUT_DIR.mkdir(exist_ok=True)
    ruta_completo = OUTPUT_DIR / "dataset_completo.csv"
    ruta_ml = OUTPUT_DIR / "dataset_ml.csv"

    # Columnas de features = todas menos las vetadas (id/indices) y los targets.
    columnas_features = [
        col
        for col in df.columns
        if col not in COL_BORRAR_ML and col not in ORDEN_TARGETS
    ]
    columnas_ml = columnas_features + ORDEN_TARGETS

    # 9) Exportar ambos CSV (utf-8-sig para que Excel muestre bien las tildes).
    df.to_csv(ruta_completo, index=False, encoding="utf-8-sig")
    df[columnas_ml].to_csv(
        ruta_ml,
        index=False,
        encoding="utf-8-sig",
    )

    # 10) Reporte por consola (auditoria rapida).
    print("=" * 60)
    print("DATASET GENERADO")
    print("=" * 60)
    print(f"Semilla: {semilla}")
    print(f"Registros: {len(df)}")
    print(f"Columnas completas: {len(df.columns)}")
    print(f"Columnas ML: {len(columnas_ml)}")
    print(f"Departamentos: {df['departamento'].nunique()}")
    print(f"Municipios distintos: {df['municipio'].nunique()}")
    print(f"Ruido del puntaje (std): {ruido_puntaje}")

    print("\nDistribucion de prioridades:")
    conteo = df["prioridad"].value_counts().sort_index()
    porcentaje = (conteo / len(df) * 100).round(2)
    for clase in conteo.index:
        print(f"  {clase:<10} {conteo[clase]:>6}  ({porcentaje[clase]}%)")

    print("\nEstadisticos de indices:")
    for col in ["indice_necesidad", "indice_acceso",
                "indice_vulnerabilidad", "indice_brecha",
                "puntaje_prioridad"]:
        print(f"  {col:<22} {resumen_indice(df[col])}")

    print("\nRegistros por split:")
    for nombre, cantidad in df["split"].value_counts().items():
        print(f"  {nombre:<6} {cantidad:>6}  ({cantidad / len(df) * 100:.1f}%)")

    print("\nDepartamentos con mas registros:")
    print(
        df["departamento"]
        .value_counts()
        .head(5)
        .to_string()
    )
    print("\nDepartamentos con menos registros:")
    print(
        df["departamento"]
        .value_counts()
        .tail(5)
        .to_string()
    )

    # 11) Verificaciones finales sobre el dataset de ML (sin fuga de informacion).
    columnas_ml_leidas = pd.read_csv(ruta_ml, nrows=0).columns
    leakage = [col for col in COL_BORRAR_ML if col in columnas_ml_leidas]
    nulos = int(df[columnas_ml].isna().sum().sum())
    print(f"\nColumnas filtradas del ML: {COL_BORRAR_ML}")
    print(f"Leakage detectado en dataset_ml: {leakage or 'ninguno'}")
    print(f"Valores nulos en dataset_ml: {nulos}")
    print(f"Target de regresion: puntaje_prioridad")
    print(f"Target categorico: prioridad")
    print("\nArchivos creados:")
    print(f"  {ruta_completo.relative_to(BASE_DIR)}")
    print(f"  {ruta_ml.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
