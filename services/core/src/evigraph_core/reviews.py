"""Expert review commands.

Every change of an assertion's state is a ReviewEvent. Commands carry
* `expected_revision`: the assertion revision the expert saw; a mismatch means someone else
  changed it meanwhile (optimistic concurrency, the row is locked while checking);
* `idempotency_key`: replaying a command with the same key returns the original result
  instead of applying it twice; reusing a key for a different command is a conflict.

A document version has gold labels for a catalog version once a ReviewCompletion exists,
which is only allowed when no proposed or auto-applied assertion is left undecided.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from evigraph_core.catalogs import require_published
from evigraph_core.models import (
    Assertion,
    AssertionState,
    Catalog,
    CatalogVersion,
    Concept,
    DocumentVersion,
    ReviewCompletion,
    ReviewEvent,
    ReviewKind,
)


class ReviewConflictError(Exception):
    """The command cannot be applied in the current state (HTTP 409)."""


class ReviewNotFoundError(LookupError):
    pass


# allowed transitions: kind -> {from_state: to_state}
TRANSITIONS: dict[ReviewKind, dict[AssertionState, AssertionState]] = {
    ReviewKind.accept: {
        AssertionState.proposed: AssertionState.accepted,
        AssertionState.auto_applied: AssertionState.accepted,
        AssertionState.rejected: AssertionState.accepted,
    },
    ReviewKind.reject: {
        AssertionState.proposed: AssertionState.rejected,
        AssertionState.auto_applied: AssertionState.rejected,
        AssertionState.accepted: AssertionState.rejected,
    },
    ReviewKind.withdraw: {
        AssertionState.accepted: AssertionState.proposed,
        AssertionState.rejected: AssertionState.proposed,
    },
}
UNDECIDED = (AssertionState.proposed, AssertionState.auto_applied)


@dataclass(frozen=True)
class ReviewResult:
    assertion: Assertion
    event: ReviewEvent
    replayed: bool


def _replay(session: Session, key: str, assertion_id: uuid.UUID | None, kind: ReviewKind):
    event = session.scalar(select(ReviewEvent).where(ReviewEvent.idempotency_key == key))
    if event is None:
        return None
    if (assertion_id is not None and event.assertion_id != assertion_id) or event.kind != kind:
        msg = f"idempotency key {key!r} was used for a different command"
        raise ReviewConflictError(msg)
    return ReviewResult(session.get_one(Assertion, event.assertion_id), event, replayed=True)


def review(
    session: Session,
    *,
    assertion_id: uuid.UUID,
    kind: ReviewKind,
    reviewer: str,
    expected_revision: int,
    idempotency_key: str,
    comment: str | None = None,
) -> ReviewResult:
    if kind is ReviewKind.add:
        msg = "use add_concept for additions"
        raise ValueError(msg)
    if (done := _replay(session, idempotency_key, assertion_id, kind)) is not None:
        return done
    assertion = session.scalar(
        select(Assertion).where(Assertion.id == assertion_id).with_for_update()
    )
    if assertion is None:
        raise ReviewNotFoundError(f"assertion {assertion_id} not found")
    if assertion.revision != expected_revision:
        msg = f"assertion is at revision {assertion.revision}, not {expected_revision}"
        raise ReviewConflictError(msg)
    target = TRANSITIONS[kind].get(assertion.state)
    if target is None:
        msg = f"cannot {kind} an assertion in state {assertion.state}"
        raise ReviewConflictError(msg)
    event = ReviewEvent(
        assertion_id=assertion.id,
        kind=kind,
        reviewer=reviewer,
        comment=comment,
        idempotency_key=idempotency_key,
        from_state=assertion.state,
        to_state=target,
        resulting_revision=assertion.revision + 1,
    )
    assertion.state = target
    assertion.revision += 1
    session.add(event)
    session.flush()
    return ReviewResult(assertion, event, replayed=False)


def _concept_for_document(
    session: Session, document_version_id: uuid.UUID, concept_id: uuid.UUID
) -> tuple[DocumentVersion, Concept]:
    version = session.get(DocumentVersion, document_version_id)
    concept = session.get(Concept, concept_id)
    if version is None or concept is None:
        raise ReviewNotFoundError("document version or concept not found")
    catalog_version = require_published(session, concept.catalog_version_id)
    catalog = session.get_one(Catalog, catalog_version.catalog_id)
    if catalog.project_id != version.project_id:
        msg = "the concept belongs to another project's catalog"
        raise ReviewConflictError(msg)
    return version, concept


def add_concept(
    session: Session,
    *,
    document_version_id: uuid.UUID,
    concept_id: uuid.UUID,
    reviewer: str,
    idempotency_key: str,
    comment: str | None = None,
) -> ReviewResult:
    if (done := _replay(session, idempotency_key, None, ReviewKind.add)) is not None:
        return done
    _concept_for_document(session, document_version_id, concept_id)
    existing = session.scalar(
        select(Assertion).where(
            Assertion.document_version_id == document_version_id,
            Assertion.concept_id == concept_id,
        )
    )
    if existing is not None:
        msg = "the concept is already asserted for this document; review that assertion instead"
        raise ReviewConflictError(msg)
    assertion = Assertion(
        document_version_id=document_version_id,
        concept_id=concept_id,
        state=AssertionState.accepted,
        revision=1,
    )
    session.add(assertion)
    session.flush()
    event = ReviewEvent(
        assertion_id=assertion.id,
        kind=ReviewKind.add,
        reviewer=reviewer,
        comment=comment,
        idempotency_key=idempotency_key,
        from_state=None,
        to_state=AssertionState.accepted,
        resulting_revision=1,
    )
    session.add(event)
    session.flush()
    return ReviewResult(assertion, event, replayed=False)


def assertions_for(
    session: Session, document_version_id: uuid.UUID, catalog_version_id: uuid.UUID
) -> list[Assertion]:
    return list(
        session.scalars(
            select(Assertion)
            .join(Concept, Concept.id == Assertion.concept_id)
            .where(
                Assertion.document_version_id == document_version_id,
                Concept.catalog_version_id == catalog_version_id,
            )
            .order_by(Concept.key)
        )
    )


def complete(
    session: Session,
    *,
    document_version_id: uuid.UUID,
    catalog_version_id: uuid.UUID,
    reviewer: str,
    idempotency_key: str,
) -> ReviewCompletion:
    prior = session.scalar(
        select(ReviewCompletion).where(ReviewCompletion.idempotency_key == idempotency_key)
    )
    if prior is not None:
        if (prior.document_version_id, prior.catalog_version_id) != (
            document_version_id,
            catalog_version_id,
        ):
            msg = f"idempotency key {idempotency_key!r} was used for a different command"
            raise ReviewConflictError(msg)
        return prior
    if session.get(DocumentVersion, document_version_id) is None:
        raise ReviewNotFoundError(f"document version {document_version_id} not found")
    require_published(session, catalog_version_id)
    undecided = [
        a
        for a in assertions_for(session, document_version_id, catalog_version_id)
        if a.state in UNDECIDED
    ]
    if undecided:
        msg = f"{len(undecided)} assertion(s) are still undecided"
        raise ReviewConflictError(msg)
    existing = session.scalar(
        select(ReviewCompletion).where(
            ReviewCompletion.document_version_id == document_version_id,
            ReviewCompletion.catalog_version_id == catalog_version_id,
        )
    )
    if existing is not None:
        return existing
    completion = ReviewCompletion(
        document_version_id=document_version_id,
        catalog_version_id=catalog_version_id,
        reviewer=reviewer,
        idempotency_key=idempotency_key,
    )
    session.add(completion)
    session.flush()
    return completion


def gold_labels(
    session: Session, catalog_version: CatalogVersion
) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Fully reviewed document versions -> accepted concept ids (empty set is a valid label)."""
    rows = session.execute(
        select(ReviewCompletion.document_version_id).where(
            ReviewCompletion.catalog_version_id == catalog_version.id
        )
    ).all()
    gold: dict[uuid.UUID, set[uuid.UUID]] = {r[0]: set() for r in rows}
    accepted = session.execute(
        select(Assertion.document_version_id, Assertion.concept_id)
        .join(Concept, Concept.id == Assertion.concept_id)
        .where(
            Concept.catalog_version_id == catalog_version.id,
            Assertion.state == AssertionState.accepted,
            Assertion.document_version_id.in_(list(gold)),
        )
    ).all()
    for doc, concept in accepted:
        gold[doc].add(concept)
    return gold
