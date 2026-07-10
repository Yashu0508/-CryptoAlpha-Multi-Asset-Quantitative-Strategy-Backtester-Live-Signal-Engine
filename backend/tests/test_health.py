"""Smoke tests for operational API endpoints."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok() -> None:
    """The service exposes a stable health response."""

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
