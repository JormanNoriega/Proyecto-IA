import json

from app.audit_geography import audit


def test_audit_reports_missing_extra_invalid_and_duplicates(tmp_path):
    catalog = tmp_path / "catalog.csv"
    departments = tmp_path / "departments.geojson"
    municipalities = tmp_path / "municipalities.geojson"
    catalog.write_text("cod_dpto,cod_mpio\n20,20001\n20,20002\n", encoding="utf-8")
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 1], [0, 0]]]}

    def collection(field, codes):
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {field: code}, "geometry": geometry} for code in codes
        ]}

    departments.write_text(json.dumps(collection("DPTO_CCDGO", ["20"])), encoding="utf-8")
    municipalities.write_text(json.dumps(collection("MPIO_CDPMP", ["20001", "20001", "20003", None])), encoding="utf-8")
    report = audit(catalog, departments, municipalities)
    assert report["department"]["missing"] == []
    assert report["municipality"]["missing"] == ["20002"]
    assert report["municipality"]["extra"] == ["20003"]
    assert report["municipality"]["duplicates"] == ["20001"]
    assert len(report["municipality"]["invalid"]) == 1
    assert len(report["sha256"]["catalog"]) == 64
