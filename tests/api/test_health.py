from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.main import app


def test_health_endpoint_reports_process_liveness():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint_checks_database_connectivity():
    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_endpoint_returns_service_unavailable_without_database():
    with patch("app.api.health.engine.connect", side_effect=SQLAlchemyError("database offline")):
        response = TestClient(app).get("/ready")

    assert response.status_code == 503
