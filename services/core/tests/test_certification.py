"""Certification, auto-apply, audit-driven suspension and planning."""

import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_engine import corpus
from test_suggestions_flow import KEYS, _review_fully, _setup

from evigraph_core.app import create_app
from evigraph_core.engine import policy


@pytest.fixture
def client(settings) -> TestClient:
    settings.audit_rate = 1.0  # audit every auto-applied tag
    settings.min_audit = 5
    settings.cert_grid_min_applied = 20
    return TestClient(create_app(settings))


def _key() -> str:
    return uuid.uuid4().hex


def test_cp_bounds_and_planner_are_consistent() -> None:
    assert policy.cp_upper(0, 0, 0.1) == 1.0
    assert policy.cp_lower(0, 50, 0.1) == 0.0
    assert policy.cp_lower(5, 50, 0.1) < 5 / 50 < policy.cp_upper(5, 50, 0.1)
    n = policy.pairs_needed(alpha=0.10, delta=0.1, expected_risk=0.05)
    assert n is not None
    assert policy.cp_upper(round(0.05 * n), n, 0.1) <= 0.10
    assert policy.cp_upper(round(0.05 * (n - 1)), n - 1, 0.1) > 0.10
    assert policy.pairs_needed(alpha=0.05, delta=0.1, expected_risk=0.05) is None


def test_grid_start_leaves_room_for_zero_error_certification() -> None:
    n_min = policy.zero_error_minimum(0.05, 0.1)
    assert policy.cp_upper(0, n_min, 0.1) <= 0.05 < policy.cp_upper(0, n_min - 1, 0.1)
    start = policy.grid_start(
        alpha=0.05, delta=0.1, fit_documents=2800, cert_documents=1200, floor=50
    )
    assert start * 1200 / 2800 >= 2 * n_min
    assert (
        policy.grid_start(alpha=0.5, delta=0.1, fit_documents=10, cert_documents=10, floor=50) == 50
    )


def test_planner_endpoint(client: TestClient) -> None:
    r = client.get(
        "/planning/certification",
        params={"alpha": 0.1, "expected_risk": 0.05, "auto_tags_per_document": 2},
    ).json()
    assert r["applied_pairs"] > 0
    assert r["cert_documents"] == int(np.ceil(r["applied_pairs"] / 2))
    assert r["reviewed_documents"] >= r["cert_documents"] / 0.3 - 1


def test_certify_auto_apply_audit_and_suspend(client: TestClient) -> None:
    project, version, ids = _setup(client)
    texts, y = corpus(400, seed=11)
    for t, labels in zip(texts, y, strict=True):
        doc = client.post(f"/projects/{project['id']}/documents", json={"text": t}).json()["id"]
        _review_fully(client, doc, version["id"], ids, [j for j in range(3) if labels[j]])

    release = client.post(f"/catalog-versions/{version['id']}/releases").json()
    assert release["manifest"]["kind"] == "trained"
    cert = client.post(
        f"/releases/{release['id']}/certifications", json={"alpha": 0.1, "delta": 0.1}
    ).json()
    assert cert["status"] == "active", cert
    assert cert["tau"] is not None
    assert cert["ucb"] <= 0.1
    assert cert["cert_documents"] > 50

    # new documents: confident tags are applied automatically and all are audited
    new_texts, _ = corpus(20, seed=12)
    auto_assertions = []
    for t in new_texts:
        doc = client.post(f"/projects/{project['id']}/documents", json={"text": t}).json()["id"]
        out = client.post(
            f"/document-versions/{doc}/suggestions",
            json={"catalog_version_id": version["id"], "top_k": 3},
        ).json()
        assert out["certification_id"] == cert["id"]
        auto_assertions += [s for s in out["suggestions"] if s["decision"] == "auto_applied"]
    assert len(auto_assertions) >= 5
    assert all(s["state"] == "auto_applied" for s in auto_assertions)

    # an expert rejects every audited tag: evidence that risk exceeds alpha -> suspension
    for s in auto_assertions[:8]:
        r = client.post(
            f"/assertions/{s['assertion_id']}/review",
            json={
                "kind": "reject",
                "expected_revision": s["revision"],
                "idempotency_key": _key(),
                "reviewer": "auditor",
            },
        )
        assert r.status_code == 200, r.text
    report = client.get(f"/certifications/{cert['id']}/monitor").json()
    assert report["status"] == "suspended"
    assert report["risk_lower"] > 0.1

    doc = client.post(
        f"/projects/{project['id']}/documents", json={"text": corpus(1, seed=13)[0][0]}
    ).json()["id"]
    out = client.post(
        f"/document-versions/{doc}/suggestions",
        json={"catalog_version_id": version["id"], "top_k": 3},
    ).json()
    assert out["certification_id"] is None
    assert {s["decision"] for s in out["suggestions"]} == {"needs_review"}
    assert set(KEYS) >= {s["concept_key"] for s in out["suggestions"]}


def test_cold_start_release_cannot_be_certified(client: TestClient) -> None:
    project, version, _ = _setup(client)
    client.post(f"/projects/{project['id']}/documents", json={"text": corpus(1)[0][0]})
    release = client.post(f"/catalog-versions/{version['id']}/releases").json()
    r = client.post(f"/releases/{release['id']}/certifications", json={"alpha": 0.1})
    assert r.status_code == 409
    assert "cold-start" in r.json()["detail"]
