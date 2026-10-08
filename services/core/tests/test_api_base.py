import pytest
from fastapi.testclient import TestClient

from evigraph_core.app import create_app


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def test_project_catalog_and_document_flow(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    project = client.post("/projects", json={"name": "contracts"}).json()
    catalog = client.post(f"/projects/{project['id']}/catalogs", json={"name": "risks"}).json()
    version = client.post(
        f"/catalogs/{catalog['id']}/versions",
        json={
            "concepts": [
                {"key": "incident", "label": "Уведомление об инциденте"},
                {"key": "pdata", "label": "Персональные данные"},
            ]
        },
    ).json()
    assert version["status"] == "draft"
    assert [c["key"] for c in version["concepts"]] == ["incident", "pdata"]
    published = client.post(f"/catalog-versions/{version['id']}/publish").json()
    assert published["status"] == "published"

    text = "Поставщик уведомляет покупателя об инциденте в течение 24 часов. " * 5
    first = client.post(
        f"/projects/{project['id']}/documents",
        json={"text": text, "source": {"system": "dms", "id": "42"}},
    )
    assert first.status_code == 201
    copy = client.post(f"/projects/{project['id']}/documents", json={"text": text}).json()
    assert copy["provenance_reason"] == "exact"
    assert copy["provenance_group_id"] == first.json()["provenance_group_id"]


def test_validation_and_errors(client: TestClient) -> None:
    assert client.post("/projects", json={"name": ""}).status_code == 422
    assert client.post("/projects", json={"name": 5}).status_code == 422  # strict: no coercion
    project = client.post("/projects", json={"name": "x"}).json()
    assert client.post("/projects", json={"name": "x"}).status_code == 409
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/projects/{missing}/catalogs", json={"name": "c"}).status_code == 404
    catalog = client.post(f"/projects/{project['id']}/catalogs", json={"name": "c"}).json()
    dup = {"concepts": [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}]}
    assert client.post(f"/catalogs/{catalog['id']}/versions", json=dup).status_code == 409
