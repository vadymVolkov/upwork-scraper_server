import os

from fastapi.testclient import TestClient

from src.api.app import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_key_protected_endpoint():
    os.environ["API_KEYS"] = "abc123"
    client = TestClient(app)
    response = client.post("/v1/search", json={"search": {"query": "n8n", "limit": 1}})
    assert response.status_code == 401
