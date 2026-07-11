import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_domain_safe_scan_unauthorized(client):
    response = client.post(
        "/domain-safe-scan/analyze",
        json={"domain": "example.com", "scheme": "https", "confirm_authorized": False},
    )
    assert response.status_code == 400
    assert "Scan not authorized" in response.json()["detail"]


def test_domain_safe_scan_localhost(client):
    response = client.post(
        "/domain-safe-scan/analyze",
        json={"domain": "localhost", "scheme": "http", "confirm_authorized": True},
    )
    assert response.status_code == 400
    assert "Local or internal domains" in response.json()["detail"]


def test_domain_safe_scan_private_ip(client):
    response = client.post(
        "/domain-safe-scan/analyze",
        json={"domain": "127.0.0.1", "scheme": "http", "confirm_authorized": True},
    )
    assert response.status_code == 400
    assert (
        "private" in response.json()["detail"]
        or "loopback" in response.json()["detail"]
    )
