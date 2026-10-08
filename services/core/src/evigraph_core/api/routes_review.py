"""Review commands and assertion reads."""

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import select

from evigraph_core import certification, reviews
from evigraph_core.api.deps import SessionDep, SettingsDep
from evigraph_core.api.schemas import Out, Strict, UUIDIn
from evigraph_core.models import AuditSample, ReviewKind

router = APIRouter()


class ReviewIn(Strict):
    kind: Literal["accept", "reject", "withdraw"]
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=200)
    reviewer: str = Field(min_length=1, max_length=200)
    comment: str | None = None


class AddConceptIn(Strict):
    concept_id: UUIDIn
    idempotency_key: str = Field(min_length=8, max_length=200)
    reviewer: str = Field(min_length=1, max_length=200)
    comment: str | None = None


class CompleteIn(Strict):
    catalog_version_id: UUIDIn
    idempotency_key: str = Field(min_length=8, max_length=200)
    reviewer: str = Field(min_length=1, max_length=200)


class AssertionOut(Out):
    id: uuid.UUID
    document_version_id: uuid.UUID
    concept_id: uuid.UUID
    state: str
    revision: int


class ReviewOut(Strict):
    assertion: AssertionOut
    event_id: uuid.UUID
    replayed: bool


class CompletionOut(Out):
    id: uuid.UUID
    document_version_id: uuid.UUID
    catalog_version_id: uuid.UUID
    reviewer: str


def _out(result: reviews.ReviewResult) -> ReviewOut:
    return ReviewOut(
        assertion=AssertionOut.model_validate(result.assertion),
        event_id=result.event.id,
        replayed=result.replayed,
    )


@router.post("/assertions/{assertion_id}/review", response_model=ReviewOut)
def review_assertion(
    assertion_id: uuid.UUID, body: ReviewIn, session: SessionDep, settings: SettingsDep
) -> ReviewOut:
    result = reviews.review(
        session,
        assertion_id=assertion_id,
        kind=ReviewKind(body.kind),
        reviewer=body.reviewer,
        expected_revision=body.expected_revision,
        idempotency_key=body.idempotency_key,
        comment=body.comment,
    )
    audit = session.scalar(select(AuditSample).where(AuditSample.assertion_id == assertion_id))
    if audit is not None:  # an audited auto-applied tag was reviewed: re-check the guarantee
        certification.evaluate(session, audit.certification_id, settings)
    return _out(result)


@router.post(
    "/document-versions/{version_id}/assertions", status_code=201, response_model=ReviewOut
)
def add_concept(version_id: uuid.UUID, body: AddConceptIn, session: SessionDep) -> ReviewOut:
    return _out(
        reviews.add_concept(
            session,
            document_version_id=version_id,
            concept_id=body.concept_id,
            reviewer=body.reviewer,
            idempotency_key=body.idempotency_key,
            comment=body.comment,
        )
    )


@router.get("/document-versions/{version_id}/assertions", response_model=list[AssertionOut])
def list_assertions(version_id: uuid.UUID, catalog_version_id: uuid.UUID, session: SessionDep):
    return reviews.assertions_for(session, version_id, catalog_version_id)


@router.post(
    "/document-versions/{version_id}/review-completions",
    status_code=201,
    response_model=CompletionOut,
)
def complete_review(version_id: uuid.UUID, body: CompleteIn, session: SessionDep):
    return reviews.complete(
        session,
        document_version_id=version_id,
        catalog_version_id=body.catalog_version_id,
        reviewer=body.reviewer,
        idempotency_key=body.idempotency_key,
    )
