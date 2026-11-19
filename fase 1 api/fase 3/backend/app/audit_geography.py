"""Auditoría reproducible de códigos del catálogo frente a GeoJSON MGN.

No modifica la base de datos ni certifica la calidad de las geometrías.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def audit(catalog: Path, departments: Path, municipalities: Path) -> dict:
    paths = {"catalog": catalog, "departments": departments, "municipalities": municipalities}
    raw = {key: path.read_bytes() for key, path in paths.items()}
    rows = list(csv.DictReader(raw["catalog"].decode("utf-8-sig").splitlines()))
    catalog_municipalities = {row["cod_mpio"].strip() for row in rows}
    catalog_departments = {row["cod_dpto"].strip() for row in rows}

    def inspect(data: bytes, field: str, length: int) -> dict:
        collection = json.loads(data)
        if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
            raise ValueError("Se esperaba un GeoJSON FeatureCollection.")
        codes, invalid = [], []
        for index, feature in enumerate(collection["features"]):
            properties = feature.get("properties") or {}
            code = properties.get(field)
            geometry = feature.get("geometry") or {}
            if not isinstance(code, str) or len(code) != length or not code.isdigit():
                invalid.append({"index": index, "reason": "código ausente o inválido", "code": code})
            elif geometry.get("type") not in ("Polygon", "MultiPolygon") or not geometry.get("coordinates"):
                invalid.append({"index": index, "reason": "geometría ausente o no poligonal", "code": code})
            else:
                codes.append(code)
        counts = Counter(codes)
        return {"codes": sorted(counts), "duplicates": sorted(k for k, n in counts.items() if n > 1), "invalid": invalid}

    dept = inspect(raw["departments"], "DPTO_CCDGO", 2)
    muni = inspect(raw["municipalities"], "MPIO_CDPMP", 5)
    dept_codes, muni_codes = set(dept["codes"]), set(muni["codes"])
    return {
        "sha256": {key: hashlib.sha256(value).hexdigest() for key, value in raw.items()},
        "department": {"catalog_count": len(catalog_departments), "geometry_count": len(dept_codes),
                       "missing": sorted(catalog_departments - dept_codes), "extra": sorted(dept_codes - catalog_departments),
                       "duplicates": dept["duplicates"], "invalid": dept["invalid"]},
        "municipality": {"catalog_count": len(catalog_municipalities), "geometry_count": len(muni_codes),
                         "missing": sorted(catalog_municipalities - muni_codes), "extra": sorted(muni_codes - catalog_municipalities),
                         "duplicates": muni["duplicates"], "invalid": muni["invalid"]},
        "limitations": "Auditoría de códigos y estructura únicamente; no comprueba topología, precisión ni cobertura insular.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("departments", type=Path)
    parser.add_argument("municipalities", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.catalog, args.departments, args.municipalities), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
