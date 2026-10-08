import threading

import pytest
from helpers import doc, proposed, world

from evigraph_core import reviews
from evigraph_core.models import AssertionState, ReviewKind

TEXT = "The supplier shall notify the buyer of any security incident within 24 hours. " * 3


def _setup(factory, settings):
    with factory() as s:
        w = world(s, ["incident", "pdata", "term"])
        v = doc(s, settings, w, TEXT)
        a = proposed(s, v, w.concepts["incident"])
        b = proposed(s, v, w.concepts["pdata"])
        s.commit()
        return w, v, a, b


def test_accept_is_idempotent_and_bumps_revision(factory, settings) -> None:
    _, _, a, _ = _setup(factory, settings)
    with factory() as s:
        r1 = reviews.review(
            s,
            assertion_id=a.id,
            kind=ReviewKind.accept,
            reviewer="ann",
            expected_revision=1,
            idempotency_key="key-0001",
        )
        s.commit()
    with factory() as s:
        r2 = reviews.review(
            s,
            assertion_id=a.id,
            kind=ReviewKind.accept,
            reviewer="ann",
            expected_revision=1,
            idempotency_key="key-0001",
        )
    assert (r1.assertion.state, r1.assertion.revision, r1.replayed) == (
        AssertionState.accepted,
        2,
        False,
    )
    assert r2.replayed
    assert r2.event.id == r1.event.id
    assert r2.assertion.revision == 2


def test_stale_revision_key_reuse_and_invalid_transition_conflict(factory, settings) -> None:
    _, _, a, b = _setup(factory, settings)
    with factory() as s:
        reviews.review(
            s,
            assertion_id=a.id,
            kind=ReviewKind.reject,
            reviewer="ann",
            expected_revision=1,
            idempotency_key="key-0002",
        )
        s.commit()
    with factory() as s, pytest.raises(reviews.ReviewConflictError, match="revision 2"):
        reviews.review(
            s,
            assertion_id=a.id,
            kind=ReviewKind.accept,
            reviewer="bob",
            expected_revision=1,
            idempotency_key="key-0003",
        )
    with factory() as s, pytest.raises(reviews.ReviewConflictError, match="different command"):
        reviews.review(
            s,
            assertion_id=b.id,
            kind=ReviewKind.reject,
            reviewer="ann",
            expected_revision=1,
            idempotency_key="key-0002",
        )
    with factory() as s, pytest.raises(reviews.ReviewConflictError, match="cannot withdraw"):
        reviews.review(
            s,
            assertion_id=b.id,
            kind=ReviewKind.withdraw,
            reviewer="ann",
            expected_revision=1,
            idempotency_key="key-0004",
        )


def test_concurrent_reviews_exactly_one_wins(factory, settings) -> None:
    _, _, a, _ = _setup(factory, settings)
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def act(kind: ReviewKind, key: str) -> None:
        with factory() as s:
            barrier.wait()
            try:
                reviews.review(
                    s,
                    assertion_id=a.id,
                    kind=kind,
                    reviewer=key,
                    expected_revision=1,
                    idempotency_key=key,
                )
                s.commit()
                outcomes.append("ok")
            except reviews.ReviewConflictError:
                s.rollback()
                outcomes.append("conflict")

    threads = [
        threading.Thread(target=act, args=(ReviewKind.accept, "key-acc-1")),
        threading.Thread(target=act, args=(ReviewKind.reject, "key-rej-1")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["conflict", "ok"]


def test_completion_requires_decisions_and_defines_gold(factory, settings) -> None:
    w, v, a, b = _setup(factory, settings)
    with factory() as s, pytest.raises(reviews.ReviewConflictError, match="undecided"):
        reviews.complete(
            s,
            document_version_id=v.id,
            catalog_version_id=w.catalog_version.id,
            reviewer="ann",
            idempotency_key="done-0001",
        )
    with factory() as s:
        reviews.review(
            s,
            assertion_id=a.id,
            kind=ReviewKind.accept,
            reviewer="ann",
            expected_revision=1,
            idempotency_key="key-0010",
        )
        reviews.review(
            s,
            assertion_id=b.id,
            kind=ReviewKind.reject,
            reviewer="ann",
            expected_revision=1,
            idempotency_key="key-0011",
        )
        added = reviews.add_concept(
            s,
            document_version_id=v.id,
            concept_id=w.concepts["term"],
            reviewer="ann",
            idempotency_key="key-0012",
        )
        reviews.complete(
            s,
            document_version_id=v.id,
            catalog_version_id=w.catalog_version.id,
            reviewer="ann",
            idempotency_key="done-0002",
        )
        s.commit()
        gold = reviews.gold_labels(s, w.catalog_version)
    assert added.assertion.state is AssertionState.accepted
    assert gold == {v.id: {w.concepts["incident"], w.concepts["term"]}}


def test_add_concept_rejects_duplicates_and_foreign_catalogs(factory, settings) -> None:
    w, v, _, _ = _setup(factory, settings)
    with factory() as s:
        other = world(s, ["x"])
        s.commit()
    with factory() as s, pytest.raises(reviews.ReviewConflictError, match="already asserted"):
        reviews.add_concept(
            s,
            document_version_id=v.id,
            concept_id=w.concepts["incident"],
            reviewer="ann",
            idempotency_key="key-0020",
        )
    with factory() as s, pytest.raises(reviews.ReviewConflictError, match="another project"):
        reviews.add_concept(
            s,
            document_version_id=v.id,
            concept_id=other.concepts["x"],
            reviewer="ann",
            idempotency_key="key-0021",
        )
