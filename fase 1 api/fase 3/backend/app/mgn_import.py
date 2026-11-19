"""Audita los ZIP oficiales y genera contornos simplificados por departamento."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import shapefile
from shapely.geometry import shape, mapping
from shapely.validation import explain_validity

ROOT = Path(__file__).resolve().parents[2]
ORIGINALS = ROOT / "data/geography/mgn_2025/originals"
OUTPUT = ROOT / "data/geography/mgn_2025/processed"
CATALOG = ROOT.parent / "data/processed/dim_municipio.csv"
FILES = {"department": "MGN2025_DPTO_POLITICO.zip", "municipality": "MGN2025_MPIO_GRAFICO.zip"}


def run():
    with CATALOG.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    report = {"created": datetime.now(timezone.utc).isoformat(), "source": "DANE MGN 2025",
              "note": "Referencia geoestadística; no constituye deslinde jurídico.",
              "layers": {}}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for kind, filename in FILES.items():
        path = ORIGINALS / filename
        field = "dpto_ccdgo" if kind == "department" else "mpio_cdpmp"
        catalog_field = "cod_dpto" if kind == "department" else "cod_mpio"
        catalog = {row[catalog_field].strip() for row in rows}
        reader = shapefile.Reader(str(path), encoding="utf-8")
        codes, invalid, nonpolygon, features = [], [], [], []
        for sr in reader.iterShapeRecords():
            code = sr.record.as_dict()[field].strip()
            codes.append(code)
            geom = shape(sr.shape.__geo_interface__)
            if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
                nonpolygon.append(code)
            elif not geom.is_valid:
                invalid.append({"code": code, "reason": explain_validity(geom)})
            if kind == "department" and not geom.is_empty:
                features.append({"type": "Feature", "properties": {"code": code},
                                 "geometry": mapping(geom.simplify(0.001, preserve_topology=True))})
        counts = Counter(codes)
        report["layers"][kind] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "count": len(codes),
            "missing": sorted(catalog - counts.keys()), "extra": sorted(counts.keys() - catalog),
            "duplicates": sorted(k for k, v in counts.items() if v > 1),
            "invalid": invalid, "nonpolygon": nonpolygon,
        }
        if kind == "department":
            (OUTPUT / "departments.geojson").write_text(
                json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUTPUT / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
