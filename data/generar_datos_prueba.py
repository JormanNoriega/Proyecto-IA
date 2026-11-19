"""Genera dos lotes sintéticos para probar la importación, sin escribir en la app."""

import argparse
import csv
import io
import random
from datetime import date
from itertools import product
from pathlib import Path

from openpyxl import Workbook, load_workbook

DATA = Path(__file__).resolve().parent
PIPELINE = DATA.parent / "fase 1 api" / "data"
MAX_ROWS = 2000
MAX_BYTES = 2_000_000
SOURCE = "Datos sintéticos de prueba — NO usar para planificación ni entrenamiento"
METADATA = ("cod_mpio", "a_o", "fuente", "fecha_referencia")


def read_templates():
    with (DATA / "plantilla_municipios.csv").open(encoding="utf-8-sig", newline="") as file:
        headers = tuple(next(csv.reader(file)))
    workbook = load_workbook(DATA / "plantilla_municipios.xlsx", read_only=True)
    try:
        excel_headers = next(workbook["Registros"].values)
    finally:
        workbook.close()
    if headers != excel_headers or len(headers) != 31 or headers[:4] != METADATA:
        raise ValueError("Las plantillas no coinciden con el formato esperado de 31 columnas.")
    return headers


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def make_record(headers, territory, year, rng):
    population = rng.randint(900, 160_000)
    sites = rng.randint(1, 30)
    reserves = rng.randrange(5)
    row = {
        "cod_mpio": territory["cod_mpio"],
        "a_o": year,
        "fuente": SOURCE,
        "fecha_referencia": f"{year}-01-01",
        "latitud": float(territory["latitud"]),
        "longitud": float(territory["longitud"]),
        "poblacion": population,
        "pct_rural_disperso": round(rng.uniform(0, 95), 2),
        "banda_pob": sum(population >= limit for limit in (5000, 15000, 40000, 90000)),
        "n_sedes": sites,
        "n_sedes_ese": rng.randint(0, sites),
        "sedes_10k_hab": round(sites * 10_000 / population, 4),
        "n_resguardos": reserves,
        "pob_resguardos": rng.randint(30, population // 4) if reserves else 0,
        "n_comunidades": rng.randrange(12),
    }
    for name in headers:
        if name.startswith("nbi_"):
            row[name] = round(rng.uniform(0, 65), 2)
        elif name.startswith("pct_cap_"):
            row[name] = round(rng.uniform(0, 16), 2)
    if set(row) != set(headers):
        raise ValueError("El generador no cubre la plantilla actual.")
    return row


def make_batch(headers, catalog, historic_keys, years, rng):
    # 1.980 claves originales + 20 duplicados deliberados.
    choices = [(item, year) for item, year in product(catalog, years)
               if (item["cod_mpio"], year) not in historic_keys]
    if len(choices) < 1980:
        raise ValueError(f"No hay suficientes claves nuevas para los años {list(years)}.")
    rows = [make_record(headers, item, year, rng) for item, year in rng.sample(choices, 1980)]
    for row in rows[1800:1900]:
        row[rng.choice(("nbi_total", "pct_cap_J", "n_comunidades"))] = None
    for i, row in enumerate(rows[1900:1980]):
        case = i // 20
        if case == 0:
            row["cod_mpio"] = f"ERR{i:02d}"
        elif case == 1:
            row["pct_rural_disperso"] = 105
        elif case == 2:
            row["fecha_referencia"] = f"{row['a_o']}-02-30"
        else:
            row["n_sedes_ese"] = row["n_sedes"] + 1
    # Keep each duplicate immediately after its valid original when shuffling.
    entries = [[row] for row in rows]
    for index in rng.sample(range(1800), 20):
        entries[index].append(dict(rows[index]))
    rng.shuffle(entries)
    return [row for entry in entries for row in entry]


def encode_csv(headers, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, headers)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def encode_excel(headers, rows):
    # The importer's read-only reader expects the worksheet dimensions in the file.
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Registros"
    sheet.freeze_panes = "E2"
    sheet.append(headers)
    for row in rows:
        sheet.append([row[name] for name in headers])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42, help="Semilla reproducible (predeterminada: 42).")
    parser.add_argument("--anio-inicial", type=int, default=2022,
                        help="Primero de cuatro años consecutivos sin solapamiento entre archivos.")
    args = parser.parse_args()
    if not 1900 <= args.anio_inicial <= min(date.today().year, 2100) - 3:
        parser.error("Los cuatro años deben estar entre 1900 y el año actual.")
    headers = read_templates()
    catalog = [row for row in read_rows(PIPELINE / "processed" / "dim_municipio.csv")
               if row["latitud"] and row["longitud"]]
    historic_keys = {(row["cod_mpio"], int(row["a_o"]))
                     for row in read_rows(PIPELINE / "modelo" / "municipio_anio.csv")}
    rng = random.Random(args.seed)
    outputs = []
    for i, (extension, encode) in enumerate((("csv", encode_csv), ("xlsx", encode_excel))):
        years = range(args.anio_inicial + i * 2, args.anio_inicial + i * 2 + 2)
        rows = make_batch(headers, catalog, historic_keys, years, rng)
        content = encode(headers, rows)
        if len(rows) != MAX_ROWS or len(content) > MAX_BYTES:
            raise ValueError(f"El lote {extension} no cumple los límites de importación.")
        outputs.append((DATA / f"municipios_prueba.{extension}", content, years))
    for path, content, years in outputs:
        path.write_bytes(content)
        print(f"{path.name}: {MAX_ROWS} filas, {len(content):,} bytes, años {years.start}–{years.stop - 1}")
    print("Por archivo: 1800 completas, 100 incompletas, 100 con error intencional.")
    print("Solo para pruebas. La app también muestra un aviso informativo sobre banda_pob.")


if __name__ == "__main__":
    main()
