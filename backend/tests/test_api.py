"""API endpoint tests."""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["version"] == "1.0.0"


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "health" in data


def test_upload_no_file(client):
    response = client.post("/api/v1/upload")
    assert response.status_code == 422


def test_upload_wrong_type(client):
    response = client.post(
        "/api/v1/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_too_small(client):
    response = client.post(
        "/api/v1/upload",
        files={"file": ("test.pdf", b"tiny", "application/pdf")},
    )
    assert response.status_code == 400


def test_process_invalid_session(client):
    response = client.post(
        "/api/v1/process",
        json={"session_id": "x" * 32, "pin": "1234"},
    )
    assert response.status_code == 404


def test_download_invalid_token(client):
    response = client.get("/api/v1/download/invalid_token_123")
    assert response.status_code == 404