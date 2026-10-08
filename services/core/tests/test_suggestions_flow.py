"""End to end over HTTP: cold start -> review -> trained release -> suggestions with evidence."""

import uuid

import pytest
from fastapi.testclient import TestClient
from test_engine import TOPICS, corpus

from evigraph_core.app import create_app

KEYS = ["incident", "pdata", "termination"]


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def _key() -> str:
    return uuid.uuid4().hex


def _setup(client: TestClient):
    project = client.post("/projects", json={"name": f"p-{_key()[:6]}"}).json()
    catalog = client.post(f"/projects/{project['id']}/catalogs", json={"name": "c"}).json()
    concepts = [{"key": k, "label": k, "definition": TOPICS[i]} for i, k in enumerate(KEYS)]
    version = client.post(f"/catalogs/{catalog['id']}/versions", json={"concepts": concepts}).json()
    client.post(f"/catalog-versions/{version['id']}/publish")
    ids = {c["key"]: c["id"] for c in version["concepts"]}
    return project, version, ids


def _review_fully(client, doc_id, version_id, ids, labels) -> None:
    for j in labels:
        r = client.post(
            f"/document-versions/{doc_id}/assertions",
            json={"concept_id": ids[KEYS[j]], "idempotency_key": _key(), "reviewer": "ann"},
        )
        assert r.status_code == 201, r.text
    r = client.post(
        f"/document-versions/{doc_id}/review-completions",
        json={"catalog_version_id": version_id, "idempotency_key": _key(), "reviewer": "ann"},
    )
    assert r.status_code == 201, r.text


def test_cold_start_then_trained_release(client: TestClient) -> None:
    project, version, ids = _setup(client)
    texts, y = corpus(90)

    assert (
        client.post(
            f"/document-versions/{uuid.uuid4()}/suggestions",
            json={"catalog_version_id": version["id"]},
        ).status_code
        == 409
    )  # no release yet

    docs = []
    for t in texts:
        r = client.post(f"/projects/{project['id']}/documents", json={"text": t})
        docs.append(r.json()["id"])

    cold = client.post(f"/catalog-versions/{version['id']}/releases").json()
    assert cold["manifest"]["kind"] == "cold_start"
    s = client.post(
        f"/document-versions/{docs[0]}/suggestions",
        json={"catalog_version_id": version["id"], "top_k": 3},
    ).json()
    assert s["release_kind"] == "cold_start"
    assert [x["state"] for x in s["suggestions"]] == ["proposed"] * 3

    for doc_id, labels in zip(docs[1:], y[1:], strict=True):
        _review_fully(client, doc_id, version["id"], ids, [j for j in range(3) if labels[j]])

    trained = client.post(f"/catalog-versions/{version['id']}/releases").json()
    assert trained["manifest"]["kind"] == "trained"
    assert trained["active"] is True
    assert trained["manifest"]["fit_documents"] >= 30

    test_texts, test_y = corpus(15, seed=7)
    hits = 0
    for t, labels in zip(test_texts, test_y, strict=True):
        doc_id = client.post(f"/projects/{project['id']}/documents", json={"text": t}).json()["id"]
        out = client.post(
            f"/document-versions/{doc_id}/suggestions",
            json={"catalog_version_id": version["id"], "top_k": 3},
        ).json()
        top = out["suggestions"][0]
        hits += bool(labels[KEYS.index(top["concept_key"])])
        assert top["evidence"], "a trained release explains suggestions with reviewed documents"
    assert hits / len(test_texts) > 0.8

    queue = client.get(f"/catalog-versions/{version['id']}/review-queue").json()
    assert queue and all(item["undecided"] > 0 for item in queue)
