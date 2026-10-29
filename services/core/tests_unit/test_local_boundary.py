"""Local HTTP boundaries; no PostgreSQL fixture or listening socket is needed."""

from fastapi.testclient import TestClient

from evigraph_core.app import create_app
from evigraph_core.settings import Settings


def app():
    return create_app(Settings(database_url="sqlite:///:memory:"))


def test_foreign_host_cannot_address_the_local_api():
    client = TestClient(app(), base_url="http://attacker.invalid")
    assert client.get("/health").status_code == 400


def test_foreign_browser_origin_cannot_reach_a_mutation():
    client = TestClient(app(), base_url="http://127.0.0.1", raise_server_exceptions=False)
    response = client.post(
        "/projects", headers={"Origin": "https://attacker.invalid"}, json={"name": "untrusted"}
    )
    assert response.status_code == 403


def test_configured_local_studio_and_same_origin_keep_health_access():
    client = TestClient(app(), base_url="http://localhost:8000")
    assert client.get("/health", headers={"Origin": "http://localhost:3000"}).status_code == 200
    assert client.get("/health", headers={"Origin": "http://localhost:8000"}).status_code == 200


def test_readiness_checks_the_database_and_fails_closed():
    application = app()
    client = TestClient(application, base_url="http://127.0.0.1")
    assert client.get("/health/ready").status_code == 200

    def unavailable():
        raise RuntimeError("database unavailable")

    application.state.session_factory = unavailable
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health").status_code == 200
