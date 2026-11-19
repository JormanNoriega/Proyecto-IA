"""Genera un mismo lote sintético en CSV y Excel para probar el flujo de fase 3.

No escribe en la base de datos. Los valores son solo para demostración y no
deben usarse para decisiones reales. Ejecutar con el Python de fase 3.
"""

import argparse
import csv
import io
import math
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook

DATA = Path(__file__).resolve().parent
HISTORICAL = DATA.parent / "fase 1 api" / "data" / "modelo" / "municipio_anio.csv"
META = ("cod_mpio", "a_o", "fuente", "fecha_referencia", "consultas")
SOURCE = "DATOS SINTETICOS DE PRUEBA - NO USAR EN DECISIONES"
PER_BAND = 30
TOTAL_ROWS = 2000
YEARS = 3
MAX_BYTES = 2_000_000


def read_templates():
    with (DATA / "plantilla_municipios.csv").open(encoding="utf-8-sig", newline="") as file:
        headers = tuple(next(csv.reader(file)))
    workbook = load_workbook(DATA / "plantilla_municipios.xlsx", read_only=True)
    try:
        excel_headers = tuple(next(workbook["Registros"].values))
    finally:
        workbook.close()
    if headers != excel_headers or len(headers) != 32 or headers[:5] != META or len(set(headers)) != 32:
        raise ValueError("Las plantillas deben coincidir y contener consultas y los 27 predictores actuales.")
    return headers


def make_rows(headers, year):
    features = headers[len(META):]
    with HISTORICAL.open(encoding="utf-8-sig", newline="") as file:
        historical = list(csv.DictReader(file))
    hub_status = {}
    for row in historical:
        if row["es_hub"].strip():
            hub_status.setdefault(row["cod_mpio"], set()).add(float(row["es_hub"]))
    latest_year = max(int(row["a_o"]) for row in historical)
    if year - YEARS + 1 <= latest_year:
        raise ValueError(f"Los tres años de prueba deben ser posteriores al histórico ({latest_year}).")
    bands = {band: [] for band in range(5)}
    for row in historical:
        if int(row["a_o"]) != latest_year or hub_status.get(row["cod_mpio"]) != {0.0}:
            continue
        try:
            values = {name: float(row[name]) for name in features}
            if not all(math.isfinite(value) for value in values.values()):
                continue
            band = int(values["banda_pob"])
            if band not in bands or values["banda_pob"] != band:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        bands[band].append((row["cod_mpio"].zfill(5), values))
    counts = {band: len(rows) for band, rows in bands.items()}
    if any(count < PER_BAND for count in counts.values()):
        raise ValueError(f"No hay 30 municipios completos no hub por banda: {counts}")
    rows = []
    for index, current_year in enumerate(range(year - YEARS + 1, year + 1)):
        target = TOTAL_ROWS // YEARS + (index < TOTAL_ROWS % YEARS)
        queues = {band: list(items) for band, items in bands.items()}
        chosen = []
        while len(chosen) < target:
            progressed = False
            for band in range(5):
                if queues[band] and len(chosen) < target:
                    code, values = queues[band].pop(0)
                    chosen.append((code, values))
                    progressed = True
            if not progressed:
                raise ValueError(f"No hay suficientes municipios completos para {current_year}.")
        for i, (code, values) in enumerate(chosen):
            consultations = round(values["poblacion"] * (0.5 + (i % 30) / 30))
            rows.append({"cod_mpio": code, "a_o": current_year, "fuente": SOURCE,
                         "fecha_referencia": f"{current_year}-01-01", "consultas": consultations, **values})
    return rows


def encode_csv(headers, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def encode_excel(headers, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Registros"
    sheet.freeze_panes = "B2"
    sheet.append(headers)
    for row in rows:
        sheet.append([row[name] for name in headers])
        sheet.cell(sheet.max_row, 1).number_format = "@"
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anio", type=int, default=date.today().year, help="Último de los tres años de los registros sintéticos.")
    parser.add_argument("--salida", type=Path, default=DATA, help="Directorio de salida (predeterminado: data).")
    args = parser.parse_args()
    if not 1900 <= args.anio <= min(date.today().year, 2100):
        parser.error("El año debe estar entre 1900 y el año actual.")
    headers = read_templates()
    rows = make_rows(headers, args.anio)
    outputs = {"municipios_prueba.csv": encode_csv(headers, rows),
               "municipios_prueba.xlsx": encode_excel(headers, rows)}
    if any(len(content) > MAX_BYTES for content in outputs.values()):
        raise ValueError("Un archivo supera el límite de 2 MB de importación.")
    args.salida.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        path = args.salida / name
        path.write_bytes(content)
        print(f"{path}: {len(rows)} filas, {len(content)} bytes")
    print("Ambos archivos contienen el mismo lote de tres años: importa solo uno. Datos sintéticos, no aptos para decisiones.")


if __name__ == "__main__":
    main()
