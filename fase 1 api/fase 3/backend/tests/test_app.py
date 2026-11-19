import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIGADAS_STORAGE", str(tmp_path))
    from app import main
    importlib.reload(main)
    with main.db() as con:
        con.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)", ("admin", main.password_hash("test-password-123"), "admin"))
        con.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)", ("operador", main.password_hash("test-password-123"), "operador"))
    return TestClient(main.app)


def login(client, username):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "test-password-123"})
    assert response.status_code == 200


def test_access_and_permissions(client):
    assert client.get("/api/v1/statistics").status_code == 401
    login(client, "operador")
    assert client.get("/api/v1/statistics").status_code == 403
    assert client.post("/api/v1/users", json={"username": "other", "password": "test-password-123", "role": "admin"}).status_code == 403
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_operational_data_preview_and_confirmation(client):
    login(client, "admin")
    assert client.get("/api/v1/data/template/csv").status_code == 200
    assert client.get("/api/v1/data/template/xlsx").status_code == 200
    payload = ("cod_mpio,a_o,fuente,fecha_referencia,poblacion\n"
               "20001,2026,DANE,2025-01-01,1000\n"
               "99999,2026,DANE,2025-01-01,1000\n").encode()
    preview = client.post("/api/v1/data/preview", files={"file": ("datos.csv", payload, "text/csv")})
    assert preview.status_code == 200
    data = preview.json()
    assert not data["rows"][0]["errores"]
    assert data["rows"][0]["elegibilidad"] == "incompleto"
    assert data["rows"][1]["errores"]
    assert client.get("/api/v1/data/records").json() == []
    response = client.post("/api/v1/data/confirm/" + data["token"])
    assert response.json() == {"guardados": 1, "rechazados": 1}
    assert len(client.get("/api/v1/data/records").json()) == 1
    assert client.post("/api/v1/data/confirm/" + data["token"]).status_code == 404
    duplicate = client.post("/api/v1/data/preview", files={"file": ("datos.csv", payload, "text/csv")}).json()
    assert duplicate["rows"][0]["errores"]


def test_territorial_operational_records_are_filtered_and_admin_only(client):
    login(client, "admin")
    row = {"cod_mpio": "20001", "a_o": "2026", "fuente": "Fuente declarada", "fecha_referencia": "2025-01-01", "poblacion": 1000}
    preview = client.post("/api/v1/data/preview-record", json=row).json()
    assert client.post("/api/v1/data/confirm/" + preview["token"]).status_code == 200
    result = client.get("/api/v1/data/territorial-records?department=20&year=2026")
    assert result.status_code == 200
    assert result.json()[0]["data"]["poblacion"] == 1000
    assert result.json()[0]["source"] == "Fuente declarada"
    assert client.get("/api/v1/data/territorial-records?department=20&year=2027").json() == []
    assert client.get("/api/v1/data/territorial-records?department=05&year=2026").json() == []
    assert client.get("/api/v1/data/territorial-records?department=2&year=2026").status_code == 422
    client.post("/api/v1/auth/logout")
    login(client, "operador")
    assert client.get("/api/v1/data/territorial-records?department=20&year=2026").status_code == 403


def test_operational_priorities_and_journey_snapshot(client):
    from app import main
    login(client, "admin")
    row = {"cod_mpio": "20001", "a_o": "2026", "fuente": "Fuente de prueba", "fecha_referencia": "2026-01-01",
           **{field: 0 for field in main.FEATURES}, "latitud": 10.46, "longitud": -73.25,
           "poblacion": 1000, "pct_rural_disperso": 50}
    preview = client.post("/api/v1/data/preview-record", json=row).json()
    assert not preview["rows"][0]["errores"]
    assert client.post("/api/v1/data/confirm/" + preview["token"]).status_code == 200
    record = client.get("/api/v1/data/records").json()[0]
    candidates = client.get("/api/v1/journeys/candidates?department=20&data_source=operativo&year=2026").json()
    assert len(candidates["items"]) == 1
    assert candidates["items"][0]["fuente"] == "Fuente de prueba"
    assert len(candidates["model_sha256"]) == 64
    assert client.get("/api/v1/operational-catalog").json()["years"] == [2026]
    with main.db() as con:
        base = con.execute("INSERT INTO bases(name,municipality_code,latitude,longitude,coordinate_source,created,created_by) VALUES(?,?,?,?,?,?,?)",
                           ("Base", "20001", 10.46, -73.25, "Prueba", "2026-01-01", "admin")).lastrowid
    body = {"date": "2026-12-01", "department": "20", "year": 2026, "data_source": "operativo",
            "max_km": 100, "bases": [{"id": base, "brigades": 1}], "expected_candidates_hash": candidates["candidates_hash"]}
    plan = client.post("/api/v1/journeys/preview", json=body)
    assert plan.status_code == 200, plan.text
    saved = client.post(f"/api/v1/journeys/drafts/{plan.json()['draft_token']}/save", json={})
    assert saved.status_code == 200
    assert saved.json()["candidates"][0]["poblacion"] == 1000
    correction = client.post(f"/api/v1/data/records/{record['id']}/preview", json={**row, "poblacion": 2000}).json()
    assert client.post("/api/v1/data/corrections/" + correction["token"] + "/confirm").status_code == 200
    assert client.post("/api/v1/journeys/preview", json=body).status_code == 409
    assert client.get("/api/v1/plans").json()[0]["candidates"][0]["poblacion"] == 1000


def test_automatic_label_requires_complete_annual_cohort(client):
    from app import main
    login(client, "admin")
    row = {"cod_mpio": "20001", "a_o": "2026", "fuente": "Prueba", "fecha_referencia": "2026-01-01",
           **{field: 0 for field in main.FEATURES}, "poblacion": 1000, "consultas": 500}
    preview = client.post("/api/v1/data/preview-record", json=row).json()
    assert not preview["rows"][0]["errores"]
    assert client.post("/api/v1/data/confirm/" + preview["token"]).status_code == 200
    record = client.get("/api/v1/data/records").json()[0]
    entry = {"record_id": record["id"], "data_sha256": record["data_sha256"]}
    result = client.post("/api/v1/dataset-versions", json={"operational_inputs": [entry]})
    assert result.status_code == 422
    assert "30 registros" in result.json()["detail"]


def test_annual_labels_and_zero_median():
    import json
    from fastapi import HTTPException
    from app.main import annual_labels
    rows = [{"id": band * 30 + i + 1, "code": str(band * 30 + i), "year": 2026,
             "data": json.dumps({"consultas": i + 1, "poblacion": 1000, "banda_pob": band})}
            for band in range(5) for i in range(30)]
    labels, snapshots = annual_labels(rows, {2026})
    assert labels[1] == 1 and labels[30] == 0
    assert len(json.loads(snapshots[2026])["records"]) == 150
    for row in rows:
        data = json.loads(row["data"])
        data["consultas"] = 0
        row["data"] = json.dumps(data)
    with pytest.raises(HTTPException):
        annual_labels(rows, {2026})


def test_sample_import_and_automatic_version(client):
    from app import main
    login(client, "admin")
    path = main.ROOT.parent.parent / "data" / "municipios_prueba.csv"
    xlsx = path.with_suffix(".xlsx")
    excel_preview = client.post("/api/v1/data/preview", files={"file": (xlsx.name, xlsx.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert excel_preview.status_code == 200, excel_preview.text
    assert not [r for r in excel_preview.json()["rows"] if r["errores"]]
    preview = client.post("/api/v1/data/preview", files={"file": (path.name, path.read_bytes(), "text/csv")})
    assert preview.status_code == 200, preview.text
    invalid = [r for r in preview.json()["rows"] if r["errores"]]
    assert not invalid, invalid[:3]
    assert client.post("/api/v1/data/confirm/" + preview.json()["token"]).json()["guardados"] == 150
    records = client.get("/api/v1/data/records").json()
    selected = [{"record_id": r["id"], "data_sha256": r["data_sha256"]} for r in records]
    result = client.post("/api/v1/dataset-versions", json={"operational_inputs": selected})
    assert result.status_code == 200, result.text
    assert result.json()["operational_count"] == 150
    with main.db() as con:
        assert con.execute("SELECT COUNT(*) FROM dataset_label_cohorts").fetchone()[0] == 1


def test_data_template_rejects_formulas(client):
    import io
    from openpyxl import load_workbook
    login(client, "admin")
    workbook = load_workbook(io.BytesIO(client.get("/api/v1/data/template/xlsx").content))
    sheet = workbook["Registros"]
    sheet.append(["20001", 2026, "DANE", "2025-01-01", "=1+1"])
    output = io.BytesIO()
    workbook.save(output)
    response = client.post("/api/v1/data/preview", files={"file": ("datos.xlsx", output.getvalue())})
    assert response.status_code == 422


def test_operational_correction_keeps_history_and_rejects_stale_preview(client):
    login(client, "admin")
    row = {"cod_mpio": "20001", "a_o": "2026", "fuente": "DANE", "fecha_referencia": "2025-01-01"}
    initial = client.post("/api/v1/data/preview-record", json=row).json()
    assert client.post("/api/v1/data/confirm/" + initial["token"]).status_code == 200
    record = client.get("/api/v1/data/records").json()[0]
    record_id = record["id"]
    assert client.post(f"/api/v1/data/records/{record_id}/preview", json={**row, "a_o": "2027"}).status_code == 422
    correction = client.post(f"/api/v1/data/records/{record_id}/preview", json={**row, "poblacion": "1000"}).json()
    stale = client.post(f"/api/v1/data/records/{record_id}/preview", json={**row, "poblacion": "2000"}).json()
    assert not correction["rows"][0]["errores"]
    assert client.post("/api/v1/data/corrections/" + correction["token"] + "/confirm").status_code == 200
    assert client.post("/api/v1/data/corrections/" + stale["token"] + "/confirm").status_code == 409
    history = client.get(f"/api/v1/data/records/{record_id}/history").json()
    assert len(history) == 2
    assert history[0]["data"]["poblacion"] is None
    assert history[1]["data"]["poblacion"] == 1000
    assert client.get("/api/v1/data/records").json()[0]["data"]["poblacion"] == 1000


def test_exploratory_inference_requires_complete_inputs_and_keeps_snapshot(client):
    from app import main
    login(client, "admin")
    assert len(client.get("/api/v1/data/schema").json()["dictionary"]) == 32
    assert client.get("/api/v1/data/template/diccionario.csv").status_code == 200
    row = {"cod_mpio": "20001", "a_o": "2026", "fuente": "Prueba", "fecha_referencia": "2025-01-01"}
    preview = client.post("/api/v1/data/preview-record", json=row).json()
    assert client.post("/api/v1/data/confirm/" + preview["token"]).status_code == 200
    record_id = client.get("/api/v1/data/records").json()[0]["id"]
    assert client.post(f"/api/v1/data/records/{record_id}/exploratory-prediction").status_code == 422
    complete = {**row, **{name: 0 for name in main.FEATURES}, "poblacion": 1000}
    preview = client.post(f"/api/v1/data/records/{record_id}/preview", json=complete).json()
    assert not preview["rows"][0]["errores"]
    assert client.post("/api/v1/data/corrections/" + preview["token"] + "/confirm").status_code == 200
    result = client.post(f"/api/v1/data/records/{record_id}/exploratory-prediction")
    assert result.status_code == 200
    prediction = result.json()
    assert len(prediction["model_sha256"]) == 64
    assert prediction["data"]["poblacion"] == 1000
    assert "no validada temporalmente" in prediction["warning"]
    assert len(client.get(f"/api/v1/data/records/{record_id}/exploratory-predictions").json()) == 1


def test_territories_and_operational_bases(client):
    assert client.get("/api/v1/territories").status_code == 401
    login(client, "operador")
    catalog = client.get("/api/v1/territories?department=20")
    assert catalog.status_code == 200
    assert len(catalog.json()["departments"]) == 33
    assert any(item["code"] == "20001" for item in catalog.json()["items"])
    assert catalog.json()["metadata"]["sha256"]
    assert client.get("/api/v1/territories?department=2").status_code == 422
    body = {"name": "Hospital de prueba", "municipality_code": "20001",
            "latitude": 10.46, "longitude": -73.25, "coordinate_source": "Verificación manual",
            "coordinates_confirmed": False}
    assert client.post("/api/v1/bases", json=body).status_code == 422
    body["coordinates_confirmed"] = True
    assert client.post("/api/v1/bases", json={**body, "municipality_code": "20999"}).status_code == 422
    assert client.post("/api/v1/bases", json={**body, "latitude": 100}).status_code == 422
    assert client.post("/api/v1/bases", json=body).status_code == 200
    assert client.get("/api/v1/bases").json()[0]["municipality_code"] == "20001"


def test_geographic_api_rejects_bad_points(client):
    login(client, "operador")
    body = {"name": "Base", "municipality_code": "20001", "latitude": 4.6,
            "longitude": -74.1, "coordinate_source": "Prueba", "coordinates_confirmed": True}
    check = client.post("/api/v1/geography/validate", json=body)
    assert check.json()["status"] == "FUERA_DE_DEPARTAMENTO"
    assert client.post("/api/v1/bases", json=body).status_code == 422
    body.update(latitude=10.46, longitude=-73.25)
    assert client.post("/api/v1/bases", json=body).status_code == 200
    base = client.get("/api/v1/bases").json()[0]
    assert base["geo_status"] == "VALIDADA"
    assert base["geo_version"].startswith("DANE-MGN-2025-")
    assert base["geo_validated_at"]


def test_municipality_outline_api(client, monkeypatch):
    from app import main
    assert client.get("/api/v1/geography/municipalities/20001").status_code == 401
    login(client, "operador")
    assert client.get("/api/v1/geography/municipalities/20").status_code == 422
    feature = client.get("/api/v1/geography/municipalities/20001")
    assert feature.status_code == 200
    assert feature.json()["properties"]["code"] == "20001"
    assert feature.json()["geometry"]["type"] in ("Polygon", "MultiPolygon")
    monkeypatch.setattr(main.geography, "municipality_outline", lambda code: None)
    assert client.get("/api/v1/geography/municipalities/20001").status_code == 404


def test_department_municipalities_api(client):
    assert client.get("/api/v1/geography/departments/20/municipalities").status_code == 401
    login(client, "operador")
    assert client.get("/api/v1/geography/departments/2/municipalities").status_code == 422
    response = client.get("/api/v1/geography/departments/20/municipalities")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert any(f["properties"]["code"] == "20001" and f["properties"]["name"] for f in data["features"])
    assert all(f["properties"]["code"].startswith("20") for f in data["features"])


def test_legacy_base_review_does_not_change_data(client):
    from app import main
    login(client, "operador")
    with main.db() as con:
        con.execute("""INSERT INTO bases(name,municipality_code,latitude,longitude,coordinate_source,created,created_by)
                       VALUES ('Existente','20001',4.6,-74.1,'Manual','2026-01-01','operador')""")
    item = client.get("/api/v1/bases").json()[0]
    assert item["geo_status"] == "PENDIENTE_REVISION"
    assert item["geo_review"]["status"] == "FUERA_DE_DEPARTAMENTO"
    with main.db() as con:
        saved = con.execute("SELECT latitude,longitude,geo_status FROM bases WHERE name='Existente'").fetchone()
        assert tuple(saved) == (4.6, -74.1, None)


def test_base_contact_fields_and_existing_data(client):
    from app import main
    login(client, "operador")
    body = {"name": "Hospital", "municipality_code": "20001", "latitude": 10.46,
            "longitude": -73.25, "coordinate_source": "Mapa", "coordinates_confirmed": True,
            "nit": " 900123456-7 ", "address": "Calle 1", "phone": " 605 1234567 ",
            "contact_name": "Contacto institucional"}
    assert client.post("/api/v1/bases", json=body).status_code == 200
    main.initialize()
    base = client.get("/api/v1/bases").json()[0]
    assert base["nit"] == "900123456-7"
    assert base["phone"] == "605 1234567"
    assert base["contact_name"] == "Contacto institucional"
    assert base["address"] == "Calle 1"
    assert client.post("/api/v1/bases", json={**body, "phone": "1" * 41}).status_code == 422


def test_base_schema_upgrade_preserves_rows(tmp_path, monkeypatch):
    import sqlite3
    storage = tmp_path / "storage"
    database = storage / "database" / "brigadas.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE bases (id INTEGER PRIMARY KEY, name TEXT NOT NULL, municipality_code TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL, coordinate_source TEXT NOT NULL, created TEXT NOT NULL, created_by TEXT NOT NULL)")
        con.execute("INSERT INTO bases VALUES (1,'Base existente','20001',10,-73,'Manual','2026-01-01','operador')")
    monkeypatch.setenv("BRIGADAS_STORAGE", str(storage))
    from app import main
    importlib.reload(main)
    with main.db() as con:
        row = con.execute("SELECT * FROM bases WHERE id=1").fetchone()
        assert row["name"] == "Base existente"
        assert row["nit"] is None
        assert row["phone"] is None


def test_multibase_journey_and_snapshot(client):
    login(client, "operador")
    def add_base(name, code, lat, lon):
        response = client.post("/api/v1/bases", json={"name": name, "municipality_code": code,
            "latitude": lat, "longitude": lon, "coordinate_source": "Prueba",
            "coordinates_confirmed": True})
        assert response.status_code == 200
        return response.json()["id"]
    a = add_base("A", "20001", 10.460472, -73.259398)
    b = add_base("B", "20011", 8.31, -73.62)
    body = {"date": "2026-12-01", "department": "20", "year": 2021, "max_km": 350,
            "bases": [{"id": a, "brigades": 1}, {"id": b, "brigades": 2}]}
    assert client.post("/api/v1/journeys", json={**body, "bases": [body["bases"][0]] * 2}).status_code == 422
    assert client.post("/api/v1/journeys", json={**body, "bases": [{"id": 99999, "brigades": 1}]}).status_code == 422
    result = client.post("/api/v1/journeys", json=body)
    assert result.status_code == 200, result.text
    plan = result.json()
    assert len(plan["selected"]) <= 3
    assert len({r["cod_mpio"] for r in plan["selected"]}) == len(plan["selected"])
    for base in plan["bases"]:
        assert sum(s["base_id"] == base["id"] for s in plan["selected"]) <= base["brigades"]
        assert base["unused"] == base["brigades"] - base["assigned"]
    assert plan["distance_provider"] == "Haversine"
    saved = client.get("/api/v1/plans").json()[0]
    assert saved["selected"] == plan["selected"]
    assert saved["parameters"]["date"] == "2026-12-01"
    empty = client.post("/api/v1/journeys", json={**body, "department": "99", "year": 1900})
    assert empty.status_code == 200, empty.text
    assert not empty.json()["selected"]
    assert sum(base["unused"] for base in empty.json()["bases"]) == 3


def test_multibase_hub_and_distance_limit(client, monkeypatch):
    from app import main
    login(client, "operador")
    base = client.post("/api/v1/bases", json={"name": "Base", "municipality_code": "20001",
        "latitude": 10.46, "longitude": -73.25, "coordinate_source": "Prueba", "coordinates_confirmed": True}).json()["id"]
    row = {"cod_mpio": "20001", "nom_mpio": "Valledupar", "latitud": 10.46, "longitud": -73.25,
           "poblacion": 1000, "pct_rural_disperso": 50, "pob_resguardos": 0, "probability": .9, "es_hub": 1}
    far = {**row, "cod_mpio": "20011", "nom_mpio": "Lejos", "latitud": 0}
    monkeypatch.setattr(main, "priorities", lambda *args: {"items": [row, far], "model": "Prueba"})
    response = client.post("/api/v1/journeys", json={"date": "2026-12-01", "department": "20",
        "year": 2021, "max_km": 10, "bases": [{"id": base, "brigades": 2}]})
    assert response.status_code == 200, response.text
    data = response.json()
    assert [s["cod_mpio"] for s in data["selected"]] == ["20001"]
    assert data["bases"][0]["unused"] == 1
    assert data["unassigned_municipalities"][0]["code"] == "20011"


def test_journey_preview_explicit_save_and_candidate_fingerprint(client):
    login(client, "operador")
    body = {"name": "Base", "municipality_code": "20001", "latitude": 10.46, "longitude": -73.25,
            "coordinate_source": "Prueba", "coordinates_confirmed": True}
    base_id = client.post("/api/v1/bases", json=body).json()["id"]
    candidates = client.get("/api/v1/journeys/candidates?department=20").json()
    assert candidates["items"]
    scenario = {"date": "2026-12-01", "department": "20", "year": candidates["year"], "max_km": 350,
                "bases": [{"id": base_id, "brigades": 1}], "expected_candidates_hash": candidates["candidates_hash"]}
    assert client.post("/api/v1/journeys/preview", json={**scenario, "expected_candidates_hash": "0" * 64}).status_code == 409
    response = client.post("/api/v1/journeys/preview", json=scenario)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert "id" not in preview
    assert client.get("/api/v1/plans").json() == []
    saved = client.post(f"/api/v1/journeys/drafts/{preview['draft_token']}/save").json()
    assert saved["selected"] == preview["selected"]
    assert client.post(f"/api/v1/journeys/drafts/{preview['draft_token']}/save").json()["id"] == saved["id"]
    assert len(client.get("/api/v1/plans").json()) == 1
    assert client.post("/api/v1/journeys/drafts/inexistente/save").status_code == 404


def test_manual_journey_assignments_validate_and_save(client, monkeypatch):
    from app import main
    login(client, "operador")
    base = client.post("/api/v1/bases", json={"name": "Base", "municipality_code": "20001",
        "latitude": 10.46, "longitude": -73.25, "coordinate_source": "Prueba", "coordinates_confirmed": True}).json()["id"]
    row = {"cod_mpio": "20001", "nom_mpio": "Valledupar", "latitud": 10.46, "longitud": -73.25,
           "poblacion": 1000, "pct_rural_disperso": 50, "pob_resguardos": 0, "probability": .9, "es_hub": 1}
    near = {**row, "cod_mpio": "20011", "nom_mpio": "Cercano", "latitud": 10.47}
    far = {**row, "cod_mpio": "20013", "nom_mpio": "Lejano", "latitud": 0}
    monkeypatch.setattr(main, "priorities", lambda *args: {"items": [row, near, far], "model": "Prueba"})
    draft = client.post("/api/v1/journeys/preview", json={"date": "2026-12-01", "department": "20",
        "year": 2021, "max_km": 10, "bases": [{"id": base, "brigades": 1}]}).json()
    url = f"/api/v1/journeys/drafts/{draft['draft_token']}/assignments"
    a = {"base_id": base, "municipality_code": "20001"}
    b = {"base_id": base, "municipality_code": "20011"}
    assert client.put(url, json={"assignments": [a, a]}).status_code == 422
    assert client.put(url, json={"assignments": [a, b]}).status_code == 422
    assert client.put(url, json={"assignments": [{"base_id": base, "municipality_code": "20013"}]}).status_code == 422
    edited = client.put(url, json={"assignments": [b]})
    assert edited.status_code == 200, edited.text
    assert edited.json()["selected"][0]["cod_mpio"] == "20011"
    assert edited.json()["manually_reviewed"]
    saved = client.post(f"/api/v1/journeys/drafts/{draft['draft_token']}/save").json()
    assert saved["selected"] == edited.json()["selected"]
    assert client.put(url, json={"assignments": []}).status_code == 409


def test_journey_user_order_selection_and_saved_snapshot(client, monkeypatch):
    from app import main
    login(client, "operador")
    with main.db() as con:
        base = con.execute(
            "INSERT INTO bases(name,municipality_code,latitude,longitude,coordinate_source,created,created_by) VALUES(?,?,?,?,?,?,?)",
            ("Base", "20001", 10.46, -73.25, "Prueba", "2026-01-01", "operador"),
        ).lastrowid
    row = {"cod_mpio": "20001", "nom_mpio": "Primero IA", "latitud": 10.46, "longitud": -73.25,
           "poblacion": 1000, "pct_rural_disperso": 50, "pob_resguardos": 0, "probability": .9, "es_hub": 0}
    other = {**row, "cod_mpio": "20011", "nom_mpio": "Elegido", "probability": .1}
    far = {**row, "cod_mpio": "20013", "nom_mpio": "Lejano", "latitud": 0}
    monkeypatch.setattr(main, "priorities", lambda *args: {"items": [row, other, far], "model": "Prueba"})
    body = {"date": "2026-12-01", "department": "20", "year": 2021, "max_km": 10,
            "bases": [{"id": base, "brigades": 1}], "priority_order": ["20013", "20011", "20001"]}
    response = client.post("/api/v1/journeys/preview", json=body)
    assert response.status_code == 200, response.text
    draft = response.json()
    assert [item["cod_mpio"] for item in draft["selected"]] == ["20011"]
    assert draft["unassigned_municipalities"][0]["code"] == "20013"
    assert "capacidad" in draft["unassigned_municipalities"][1]["reason"]
    assert [item["cod_mpio"] for item in draft["suggested_candidates"]] == ["20001", "20011", "20013"]
    saved = client.post(f"/api/v1/journeys/drafts/{draft['draft_token']}/save").json()
    assert saved["parameters"]["priority_order"] == body["priority_order"]
    assert client.get("/api/v1/plans").json()[0]["selected"] == saved["selected"]
    for invalid in ([], ["20011", "20011"], ["99999"]):
        assert client.post("/api/v1/journeys/preview", json={**body, "priority_order": invalid}).status_code == 422
    only = client.post("/api/v1/journeys/preview", json={**body, "priority_order": ["20011"]}).json()
    assert [item["cod_mpio"] for item in only["candidates"]] == ["20011"]


def test_journey_priority_reassigns_base_to_preserve_earlier_choices(client, monkeypatch):
    from app import main
    login(client, "operador")
    with main.db() as con:
        bases = [con.execute(
            "INSERT INTO bases(name,municipality_code,latitude,longitude,coordinate_source,created,created_by) VALUES(?,?,?,?,?,?,?)",
            (name, "20001", 10.46, -73.25, "Prueba", "2026-01-01", "operador"),
        ).lastrowid for name in ("A", "B")]
    row = {"cod_mpio": "20001", "nom_mpio": "Primero", "latitud": 10.46, "longitud": -73.25,
           "poblacion": 1000, "pct_rural_disperso": 50, "pob_resguardos": 0, "probability": .1, "es_hub": 0}
    other = {**row, "cod_mpio": "20011", "nom_mpio": "Segundo"}
    monkeypatch.setattr(main, "priorities", lambda *args: {"items": [row, other], "model": "Prueba"})
    monkeypatch.setattr(main, "journey_distances", lambda *args: [[1, 1], [2, None]])
    response = client.post("/api/v1/journeys/preview", json={"date": "2026-12-01", "department": "20",
        "year": 2021, "max_km": 10, "bases": [{"id": b, "brigades": 1} for b in bases],
        "priority_order": ["20001", "20011"]})
    assert response.status_code == 200, response.text
    assert [(s["cod_mpio"], s["base_id"]) for s in response.json()["selected"]] == [
        ("20001", bases[1]), ("20011", bases[0])]


def test_journey_road_route_for_draft_and_saved_plan(client, monkeypatch):
    import json
    from app import main

    login(client, "operador")
    user = client.get("/api/v1/auth/me").json()
    plan = {
        "created": "2026-01-01",
        "distance_provider": "Haversine",
        "bases": [{"id": 1, "latitude": 10.46, "longitude": -73.25}],
        "selected": [{"base_id": 1, "cod_mpio": "20032", "latitud": 9.49, "longitud": -73.97, "distance_km": 130}],
    }
    with main.db() as con:
        con.execute("INSERT INTO journey_drafts(token,user_id,created,data) VALUES(?,?,?,?)",
                    ("test-route", user["id"], plan["created"], json.dumps(plan)))
    geometry = {"type": "LineString", "coordinates": [[-73.25, 10.46], [-73.5, 10.2], [-73.97, 9.49]]}
    payload = {"code": "Ok", "waypoints": [{"distance": 5}, {"distance": 10}],
               "routes": [{"geometry": geometry, "distance": 155000, "duration": 7800}]}

    class Response:
        def json(self): return payload
        def raise_for_status(self): pass

    def road_route(url, **kwargs):
        assert url.endswith("/route/v1/driving/-73.25,10.46;-73.97,9.49")
        assert kwargs["params"]["geometries"] == "geojson"
        return Response()

    monkeypatch.setattr(main, "reserve_osrm_request", lambda: None)
    monkeypatch.setattr(main.httpx, "get", road_route)
    url = "/api/v1/journeys/road-route"
    pair = {"base_id": 1, "municipality_code": "20032"}
    draft = {**pair, "draft_token": "test-route"}
    response = client.get(url, params=draft)
    assert response.status_code == 200, response.text
    assert response.json() == {"geometry": geometry, "distance_km": 155, "duration_minutes": 130}
    assert client.get(url, params={**draft, "municipality_code": "20011"}).status_code == 404
    saved = client.post("/api/v1/journeys/drafts/test-route/save").json()
    assert saved["selected"][0]["distance_km"] == 130
    saved_pair = {**pair, "plan_id": saved["id"]}
    assert client.get(url, params=saved_pair).status_code == 200
    payload["waypoints"][1]["distance"] = 1001
    assert client.get(url, params=saved_pair).status_code == 422
    payload["code"] = "NoRoute"
    assert client.get(url, params=saved_pair).status_code == 422
    client.post("/api/v1/auth/logout")
    assert client.get(url, params=saved_pair).status_code == 401
    login(client, "admin")
    assert client.get(url, params=draft).status_code == 404


def test_osrm_distance_unreachable_snap_and_failure(monkeypatch):
    import httpx
    from app import main
    bases = [{"latitude": 10.46, "longitude": -73.25}]
    candidates = [{"latitud": 8.31, "longitud": -73.62}, {"latitud": 9.0, "longitud": -73.0}]
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"code": "Ok", "distances": [[10000, None]],
                    "sources": [{"distance": 2}], "destinations": [{"distance": 1200}, {"distance": 3}]}
    monkeypatch.setattr(main.httpx, "get", lambda *a, **k: Response())
    monkeypatch.setattr(main, "osrm_last_request", 0)
    assert main.journey_distances(bases, candidates, "OSRM") == [[None, None]]
    monkeypatch.setattr(main, "osrm_last_request", 0)
    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(main.httpx, "get", fail)
    with pytest.raises(main.HTTPException) as exc:
        main.journey_distances(bases, candidates, "OSRM")
    assert exc.value.status_code == 503


def test_records_and_duplicate(client):
    login(client, "admin")
    bad = {"cod_mpio": "20", "nom_mpio": "Prueba", "a_o": 2022, "poblacion": -1}
    assert client.post("/api/v1/records", json=bad).status_code == 422
    valid = {"cod_mpio": "20011", "nom_mpio": "Prueba", "a_o": 2022, "poblacion": 1000}
    assert client.post("/api/v1/records", json=valid).status_code == 200
    assert client.post("/api/v1/records", json=valid).status_code == 409


def test_csv_and_csrf_origin(client):
    login(client, "admin")
    content = b"cod_mpio,nom_mpio,a_o,poblacion\n20011,Aguachica,2022,1000\n123,Bad,2022,-1\n"
    result = client.post("/api/v1/imports", files={"file": ("data.csv", content, "text/csv")})
    assert result.status_code == 200
    assert result.json()["accepted"] == 1
    assert len(result.json()["rejected"]) == 1
    assert client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403


def test_data_and_plan(client):
    login(client, "operador")
    result = client.get("/api/v1/priorities?department=20&year=2021")
    assert result.status_code == 200
    assert len(result.json()["items"]) > 0
    result = client.post("/api/v1/plans", json={"department": "20", "year": 2021, "brigades": 4, "max_km": 350, "min_resguardos": 0})
    assert result.status_code == 200, result.text
    assert len(result.json()["selected"]) <= 4
    assert client.get("/api/v1/plans").json()[0]["id"] == result.json()["id"]


def test_manual_prediction(client):
    login(client, "operador")
    template = client.get("/api/v1/predictions/template?code=20011&year=2021")
    assert template.status_code == 200, template.text
    features = template.json()["features"]
    result = client.post("/api/v1/predictions", json=features)
    assert result.status_code == 200, result.text
    assert 0 <= result.json()["probability"] <= 1
    features["poblacion"] = -1
    assert client.post("/api/v1/predictions", json=features).status_code == 422


def test_training_lifecycle_and_publication(client):
    from app import main
    login(client, "admin")
    version = client.post("/api/v1/dataset-versions")
    assert version.status_code == 200, version.text
    dataset_id = version.json()["id"]
    with main.db() as con:
        cur = con.execute("INSERT INTO experiments(dataset_id,created,author,status,info) VALUES(?,?,?,?,?)", (dataset_id, "2026-01-01", "admin", "pendiente", "{}"))
        experiment_id = cur.lastrowid
    main.train_experiment(experiment_id, dataset_id)
    experiments = client.get("/api/v1/experiments").json()
    exp = next(e for e in experiments if e["id"] == experiment_id)
    assert exp["status"] == "completado", exp
    assert exp["info"]["test"] is None
    assert "test_codes" not in exp["info"]
    assert client.post(f"/api/v1/experiments/{experiment_id}/publish").status_code == 409
    evaluated = client.post(f"/api/v1/experiments/{experiment_id}/test")
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["rows"] > 0
    assert client.post(f"/api/v1/experiments/{experiment_id}/publish").status_code == 200
    assert client.get("/api/v1/models/active").json()["id"] == experiment_id
    scored = client.get("/api/v1/priorities?department=20&year=2021")
    assert scored.status_code == 200, scored.text
    assert scored.json()["model"] == f"Experimento #{experiment_id}"
