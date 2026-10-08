"""Engine releases, suggestions and the review queue."""

import uuid

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import func, select

from evigraph_core import releases
from evigraph_core.api.deps import SessionDep, SettingsDep
from evigraph_core.api.schemas import Out, Strict, UUIDIn
from evigraph_core.models import Assertion, AssertionState, Assessment, Concept, Release

router = APIRouter()


class ReleaseOut(Out):
    id: uuid.UUID
    catalog_version_id: uuid.UUID
    active: bool
    manifest: dict


class SuggestIn(Strict):
    catalog_version_id: UUIDIn
    top_k: int = Field(default=10, ge=1, le=200)


class EvidenceOut(Strict):
    document_version_id: str
    similarity: float
    has_concept: bool


class SuggestionOut(Strict):
    assertion_id: uuid.UUID
    concept_id: uuid.UUID
    concept_key: str
    concept_label: str
    score: float
    rank: int
    state: str
    decision: str
    revision: int
    evidence: list[EvidenceOut]


class SuggestionsOut(Strict):
    release_id: uuid.UUID
    release_kind: str
    certification_id: uuid.UUID | None
    suggestions: list[SuggestionOut]


class QueueItem(Strict):
    document_version_id: uuid.UUID
    undecided: int
    max_uncertainty: float


@router.post("/catalog-versions/{version_id}/releases", status_code=201, response_model=ReleaseOut)
def train_release(version_id: uuid.UUID, session: SessionDep, settings: SettingsDep) -> Release:
    return releases.train(session, version_id, settings)


@router.get("/catalog-versions/{version_id}/releases", response_model=list[ReleaseOut])
def list_releases(version_id: uuid.UUID, session: SessionDep):
    return session.scalars(
        select(Release)
        .where(Release.catalog_version_id == version_id)
        .order_by(Release.created_at.desc())
    ).all()


@router.post("/document-versions/{version_id}/suggestions", response_model=SuggestionsOut)
def suggest(
    version_id: uuid.UUID, body: SuggestIn, session: SessionDep, settings: SettingsDep
) -> SuggestionsOut:
    release, cert, items = releases.suggest(
        session,
        document_version_id=version_id,
        catalog_version_id=body.catalog_version_id,
        top_k=body.top_k,
        settings=settings,
    )
    return SuggestionsOut(
        release_id=release.id,
        release_kind=release.manifest["kind"],
        certification_id=cert.id if cert is not None else None,
        suggestions=[
            SuggestionOut(
                assertion_id=s.assertion.id,
                concept_id=s.concept.id,
                concept_key=s.concept.key,
                concept_label=s.concept.label,
                score=round(s.score, 4),
                rank=s.rank,
                state=s.assertion.state.value,
                decision=s.decision,
                revision=s.assertion.revision,
                evidence=[EvidenceOut(**e) for e in s.evidence],
            )
            for s in items
        ],
    )


@router.get("/catalog-versions/{version_id}/review-queue", response_model=list[QueueItem])
def review_queue(version_id: uuid.UUID, session: SessionDep, limit: int = 20):
    """Documents with undecided proposals, most uncertain first (score closest to 0.5)."""
    release = releases.active_release(session, version_id)
    uncertainty = 1 - 2 * func.abs(Assessment.score - 0.5)
    rows = session.execute(
        select(
            Assertion.document_version_id,
            func.count(Assertion.id),
            func.max(uncertainty),
        )
        .join(Concept, Concept.id == Assertion.concept_id)
        .join(Assessment, Assessment.assertion_id == Assertion.id)
        .where(
            Concept.catalog_version_id == version_id,
            Assessment.release_id == release.id,
            Assertion.state == AssertionState.proposed,
        )
        .group_by(Assertion.document_version_id)
        .order_by(func.max(uncertainty).desc())
        .limit(min(limit, 200))
    ).all()
    return [
        QueueItem(document_version_id=r[0], undecided=r[1], max_uncertainty=round(float(r[2]), 4))
        for r in rows
    ]
