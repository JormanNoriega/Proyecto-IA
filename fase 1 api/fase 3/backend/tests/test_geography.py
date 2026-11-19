from shapely.geometry import Polygon, MultiPolygon
from app import geography


def test_geographic_states_and_islands(monkeypatch):
    department = MultiPolygon([Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]),
                               Polygon([(3, 0), (4, 0), (4, 1), (3, 1)])])
    municipality = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                                Polygon([(3, 0), (4, 0), (4, 1), (3, 1)])])
    monkeypatch.setattr(geography, "source_verified", lambda: True)
    monkeypatch.setattr(geography, "geometry", lambda kind, code: department if kind == "department" else municipality)
    assert geography.validate("20001", .5, .5)["status"] == "VALIDADA"
    assert geography.validate("20001", .5, 3.5)["status"] == "VALIDADA"
    assert geography.validate("20001", 1.5, 1.5)["status"] == "FUERA_DE_MUNICIPIO"
    assert geography.validate("20001", 5, 5)["status"] == "FUERA_DE_DEPARTAMENTO"
    assert geography.validate("20001", .5, 0)["status"] == "CERCA_DEL_LIMITE"
    assert geography.validate("20001", .5, .0001)["status"] == "CERCA_DEL_LIMITE"
    monkeypatch.setattr(geography, "geometry", lambda *args: None)
    assert geography.validate("20001", .5, .5)["status"] == "GEOMETRIA_NO_DISPONIBLE"


def test_missing_audit_blocks_validation(monkeypatch):
    monkeypatch.setattr(geography, "source_verified", lambda: False)
    assert geography.validate("20001", 10.46, -73.25)["status"] == "GEOMETRIA_NO_DISPONIBLE"


def test_real_mgn_islands_and_municipal_mismatch():
    assert geography.validate("88001", 12.5847, -81.7006)["status"] == "VALIDADA"
    assert geography.validate("88564", 13.35, -81.37)["status"] == "VALIDADA"
    assert geography.validate("20011", 10.46, -73.25)["status"] == "FUERA_DE_MUNICIPIO"


def test_department_batch_matches_individual_outlines():
    codes = ("20011", "20001")
    features = geography.municipality_outlines(codes)
    assert features is not None
    assert all(features[code] == geography.municipality_outline(code) for code in codes)
    assert geography.municipality_outlines(("20001", "99999")) is None
