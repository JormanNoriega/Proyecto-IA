"""Diccionario del esquema heredado. Las fuentes son las usadas en fase 1, no datos actuales verificados."""

PREDICTORS = {
    "latitud": ("Latitud de referencia municipal", "grados decimales", "DIVIPOLA procesada"),
    "longitud": ("Longitud de referencia municipal", "grados decimales", "DIVIPOLA procesada"),
    "poblacion": ("Población municipal", "personas", "Población DANE procesada por municipio y año"),
    "pct_rural_disperso": ("Población rural dispersa", "% de población", "Población DANE procesada"),
    "banda_pob": ("Quintil nacional de población; categorías 0 a 4", "categoría", "Calculado en fase 1 con el último año de referencia"),
    "nbi_total": ("Necesidades básicas insatisfechas, total", "%", "NBI DANE 2018 procesado"),
    "nbi_miseria": ("Población en miseria", "%", "NBI DANE 2018 procesado"),
    "nbi_vivienda": ("Componente vivienda", "%", "NBI DANE 2018 procesado"),
    "nbi_servicios": ("Componente servicios", "%", "NBI DANE 2018 procesado"),
    "nbi_hacinamiento": ("Componente hacinamiento", "%", "NBI DANE 2018 procesado"),
    "nbi_inasistencia": ("Componente inasistencia", "%", "NBI DANE 2018 procesado"),
    "nbi_dependencia": ("Componente dependencia económica", "%", "NBI DANE 2018 procesado"),
    "nbi_rural": ("Necesidades básicas insatisfechas, rural", "%", "NBI DANE 2018 procesado"),
    "nbi_rural_miseria": ("Miseria rural", "%", "NBI DANE 2018 procesado"),
    "nbi_rural_servicios": ("Componente servicios rural", "%", "NBI DANE 2018 procesado"),
    "nbi_rural_hacinamiento": ("Componente hacinamiento rural", "%", "NBI DANE 2018 procesado"),
    "n_sedes": ("Número de sedes registradas", "sedes", "REPS procesado en fase 1"),
    "n_sedes_ese": ("Número de sedes ESE registradas", "sedes", "REPS procesado en fase 1"),
    "sedes_10k_hab": ("Sedes por 10.000 habitantes", "sedes por 10.000 personas", "Calculado como n_sedes / poblacion × 10.000"),
    "n_resguardos": ("Número de resguardos", "resguardos", "Contexto étnico procesado en fase 1"),
    "pob_resguardos": ("Población de resguardos", "personas", "Contexto étnico procesado en fase 1"),
    "n_comunidades": ("Número de comunidades", "comunidades", "Contexto étnico procesado en fase 1"),
    "pct_cap_O": ("Diagnósticos CIE-10 capítulo O", "% de diagnósticos", "RIPS procesado por municipio y capítulo"),
    "pct_cap_A": ("Diagnósticos CIE-10 capítulo A", "% de diagnósticos", "RIPS procesado por municipio y capítulo"),
    "pct_cap_J": ("Diagnósticos CIE-10 capítulo J", "% de diagnósticos", "RIPS procesado por municipio y capítulo"),
    "pct_cap_K": ("Diagnósticos CIE-10 capítulo K", "% de diagnósticos", "RIPS procesado por municipio y capítulo"),
    "pct_cap_Z": ("Diagnósticos CIE-10 capítulo Z", "% de diagnósticos", "RIPS procesado por municipio y capítulo"),
}

META = {
    "cod_mpio": ("Código DIVIPOLA municipal", "texto de cinco dígitos", "Catálogo territorial local"),
    "a_o": ("Año del registro", "año", "Informado por quien registra"),
    "fuente": ("Origen declarado del conjunto", "texto", "Informado por quien registra"),
    "fecha_referencia": ("Fecha declarada del conjunto", "AAAA-MM-DD", "Informado por quien registra"),
    "consultas": ("Consultas ambulatorias del municipio y año", "consultas", "Fuente declarada; requerido para calcular la etiqueta"),
}
