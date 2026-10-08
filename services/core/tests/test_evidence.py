import itertools

import numpy as np
import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import settings as hsettings
from hypothesis import strategies as st
from sqlalchemy import update
from test_engine import TOPICS, corpus
from test_suggestions_flow import KEYS, _review_fully, _setup

from evigraph_core import evidence
from evigraph_core.app import create_app
from evigraph_core.engine.model import TrainedEngine
from evigraph_core.models import EvidenceSpan

FILLER = "The parties agree that this clause applies under the governing law of the contract."


def test_segment_offsets_are_exact_code_points() -> None:
    text = (
        "Статья 1. Поставщик уведомляет покупателя об инциденте в течение 24 часов 🚨.\n\n"
        "Статья 2. Персональные данные обрабатываются только с согласия субъекта.\n"
        "1) Срок действия договора — один год. 2) Договор продлевается автоматически."
    )
    spans = evidence.segment(text)
    assert len(spans) >= 2
    for a, b in spans:
        quote = text[a:b]
        assert quote == quote.strip() and quote
    assert "🚨" in text[spans[0][0] : spans[0][1]]
    assert all(b1 <= a2 for (_, b1), (a2, _) in itertools.pairwise(spans))


@hsettings(max_examples=50, deadline=None)
@given(st.text(min_size=0, max_size=3000))
def test_segment_never_produces_invalid_spans(text: str) -> None:
    for a, b in evidence.segment(text):
        assert 0 <= a < b <= len(text)
        assert not text[a].isspace() and not text[b - 1].isspace()


def test_selected_span_is_the_topical_sentence_and_deleting_it_lowers_the_score() -> None:
    texts, y = corpus(150)
    engine = TrainedEngine(k=10, candidates=50, min_positives=5, folds=5).fit(
        texts, y, np.arange(len(texts))
    )
    topical = "The supplier shall report every security breach incident within hours."
    doc = " ".join([FILLER] * 4 + [topical] + [FILLER] * 4)
    spans = evidence.select_spans(engine, doc, 0, max_spans=1)
    assert spans and "security breach" in doc[spans[0].start : spans[0].end]
    assert evidence.deletion_drop(engine, doc, 0, spans) > 0.05
    assert TOPICS[0]  # concept 0 is the incident topic


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def test_evidence_endpoint_returns_verified_quotes(client: TestClient, factory) -> None:
    project, version, ids = _setup(client)
    texts, y = corpus(60)
    for t, labels in zip(texts, y, strict=True):
        doc = client.post(f"/projects/{project['id']}/documents", json={"text": t}).json()["id"]
        _review_fully(client, doc, version["id"], ids, [j for j in range(3) if labels[j]])
    client.post(f"/catalog-versions/{version['id']}/releases")

    text = " ".join(
        [FILLER] * 3
        + ["Personal data processing requires the consent of the data subject."]
        + [FILLER] * 3
    )
    doc = client.post(f"/projects/{project['id']}/documents", json={"text": text}).json()["id"]
    out = client.post(
        f"/document-versions/{doc}/suggestions",
        json={"catalog_version_id": version["id"], "top_k": 3},
    ).json()
    pdata = next(s for s in out["suggestions"] if s["concept_key"] == KEYS[1])
    ev = client.get(f"/assertions/{pdata['assertion_id']}/evidence").json()
    assert ev["offsets"] == "unicode-code-points"
    top = ev["spans"][0]
    assert "consent" in top["quote"]
    stored_text = client.get(f"/document-versions/{doc}").json()
    assert stored_text["id"] == doc
    again = client.get(f"/assertions/{pdata['assertion_id']}/evidence").json()
    assert again["spans"] == ev["spans"]  # cached, stable

    with factory() as s:  # tamper with the stored hash: reads must refuse the span
        s.execute(update(EvidenceSpan).values(quote_sha256="0" * 64))
        s.commit()
    bad = client.get(f"/assertions/{pdata['assertion_id']}/evidence")
    assert bad.status_code == 409
