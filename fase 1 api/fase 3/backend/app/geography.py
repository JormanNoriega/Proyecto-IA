"""Consulta de la referencia local MGN; nunca utiliza geometrías simplificadas para validar."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import zipfile

import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import Point, shape, mapping

ROOT = Path(__file__).resolve().parents[2] / "data/geography/mgn_2025"
VERSION = "DANE-MGN-2025"
BOUNDARY_METERS = 100
FILES = {"department": ("MGN2025_DPTO_POLITICO.zip", "dpto_ccdgo"),
         "municipality": ("MGN2025_MPIO_GRAFICO.zip", "mpio_cdpmp")}


@lru_cache(maxsize=1)
def source_verified():
    try:
        report = json.loads((ROOT / "processed/audit.json").read_text(encoding="utf-8"))
        for kind, (filename, _) in FILES.items():
            layer = report["layers"][kind]
            if any(layer[k] for k in ("missing", "extra", "duplicates", "invalid", "nonpolygon")):
                return False
            with (ROOT / "originals" / filename).open("rb") as f:
                if hashlib.file_digest(f, "sha256").hexdigest() != layer["sha256"]:
                    return False
        return True
    except (OSError, ValueError, KeyError):
        return False


@lru_cache(maxsize=2)
def record_indexes(kind: str):
    filename, field = FILES[kind]
    try:
        reader = shapefile.Reader(str(ROOT / "originals" / filename), encoding="utf-8")
        indexes = {}
        for index, row in enumerate(reader.iterRecords(fields=[field])):
            code = row[0]
            indexes[code] = index if code not in indexes else None
        return indexes
    except (OSError, ValueError, shapefile.ShapefileException, KeyError, zipfile.BadZipFile):
        return {}


@lru_cache(maxsize=1200)
def geometry(kind: str, code: str):
    filename, _ = FILES[kind]
    try:
        index = record_indexes(kind).get(code)
        if index is None:
            return None
        reader = shapefile.Reader(str(ROOT / "originals" / filename), encoding="utf-8")
        geom = shape(reader.shape(index).__geo_interface__)
        if geom.is_empty or not geom.is_valid or geom.geom_type not in ("Polygon", "MultiPolygon"):
            return None
        return geom
    except (OSError, ValueError, shapefile.ShapefileException, KeyError, zipfile.BadZipFile):
        return None


def outline(code: str):
    try:
        if not source_verified():
            return None
        data = json.loads((ROOT / "processed/departments.geojson").read_text(encoding="utf-8"))
        return next((f for f in data["features"] if f["properties"]["code"] == code), None)
    except (OSError, ValueError, KeyError):
        return None


@lru_cache(maxsize=1200)
def municipality_outline(code: str):
    if not source_verified():
        return None
    geom = geometry("municipality", code)
    if geom is None:
        return None
    # Visualization only: validation continues to use the original geometry.
    simplified = geom.simplify(0.0002, preserve_topology=True)
    return {"type": "Feature", "properties": {"code": code}, "geometry": mapping(simplified)}


@lru_cache(maxsize=33)
def municipality_outlines(codes: tuple[str, ...]):
    """Read a department in index order, avoiding repeated decompression of the ZIP."""
    if not source_verified():
        return None
    try:
        indexes = record_indexes("municipality")
        if any(indexes.get(code) is None for code in codes):
            return None
        filename, _ = FILES["municipality"]
        reader = shapefile.Reader(str(ROOT / "originals" / filename), encoding="utf-8")
        features = {}
        for code in sorted(codes, key=indexes.__getitem__):
            geom = shape(reader.shape(indexes[code]).__geo_interface__)
            if geom.is_empty or not geom.is_valid or geom.geom_type not in ("Polygon", "MultiPolygon"):
                return None
            simplified = geom.simplify(0.0002, preserve_topology=True)
            features[code] = {"type": "Feature", "properties": {"code": code}, "geometry": mapping(simplified)}
        return features
    except (OSError, ValueError, shapefile.ShapefileException, KeyError, zipfile.BadZipFile):
        return None


def validate(code: str, latitude: float, longitude: float):
    dept, muni = (geometry("department", code[:2]), geometry("municipality", code)) if source_verified() else (None, None)
    version = VERSION
    if dept is not None and muni is not None:
        report = json.loads((ROOT / "processed/audit.json").read_text(encoding="utf-8"))
        version += "-" + report["layers"]["department"]["sha256"][:12] + "-" + report["layers"]["municipality"]["sha256"][:12]
    result = {"version": version, "threshold_m": BOUNDARY_METERS}
    if dept is None or muni is None:
        return {**result, "status": "GEOMETRIA_NO_DISPONIBLE", "message": "No hay geometría válida disponible para el departamento o municipio."}
    point = Point(longitude, latitude)
    if not dept.covers(point):
        return {**result, "status": "FUERA_DE_DEPARTAMENTO", "message": "La ubicación está fuera del departamento seleccionado."}
    if not muni.covers(point):
        return {**result, "status": "FUERA_DE_MUNICIPIO", "message": "La ubicación está fuera del municipio seleccionado."}
    projection = CRS.from_proj4(f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} +datum=WGS84 +units=m")
    project = Transformer.from_crs("EPSG:4326", projection, always_xy=True).transform
    # Project only the nearest boundary point instead of the whole polygon.
    from shapely.ops import nearest_points
    distances = []
    for g in (dept, muni):
        nearest = nearest_points(point, g.boundary)[1]
        x, y = project(nearest.x, nearest.y)
        distances.append((x * x + y * y) ** 0.5)
    nearest = min(distances)
    if nearest <= BOUNDARY_METERS:
        return {**result, "status": "CERCA_DEL_LIMITE", "distance_m": round(nearest, 1),
                "message": "Ubicación próxima a un límite geoestadístico; requiere revisión antes del registro."}
    return {**result, "status": "VALIDADA", "distance_m": round(nearest, 1), "message": "Ubicación dentro del departamento y municipio según MGN 2025."}
