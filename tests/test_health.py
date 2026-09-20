import pytest
from django.db.utils import OperationalError

pytestmark = pytest.mark.django_db


def test_liveness_ok(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"
    assert "release" in response.json()


def test_readiness_ok(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_fails_when_db_down(client, monkeypatch):
    def broken_cursor(*args, **kwargs):
        raise OperationalError("unable to open database file")

    monkeypatch.setattr("config.health.connection.cursor", broken_cursor)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_liveness_still_200_when_db_down(client, monkeypatch):
    def broken_cursor(*args, **kwargs):
        raise OperationalError("unable to open database file")

    monkeypatch.setattr("config.health.connection.cursor", broken_cursor)
    assert client.get("/health/live").status_code == 200


def test_page_routes_degrade_to_503_when_db_down(client, user, monkeypatch):
    client.login(username="smoke", password="s3cret-pass")

    def broken_cursor(*args, **kwargs):
        raise OperationalError("unable to open database file")

    monkeypatch.setattr("config.health.connection.cursor", broken_cursor)
    response = client.get("/")
    assert response.status_code == 503
    assert response.json()["error"] == "database unavailable"
