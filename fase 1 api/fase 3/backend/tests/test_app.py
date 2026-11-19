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
