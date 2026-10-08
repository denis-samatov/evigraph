"""Evidence spans for assertions."""

import uuid

from fastapi import APIRouter, Query

from evigraph_core import evidence
from evigraph_core.api.deps import SessionDep
from evigraph_core.api.schemas import Strict

router = APIRouter()


class SpanOut(Strict):
    id: uuid.UUID
    start: int
    end: int
    quote: str
    score: float
    rank: int
    method: str
    deletion_drop: float | None


class EvidenceOut(Strict):
    assertion_id: uuid.UUID
    release_id: uuid.UUID
    offsets: str
    spans: list[SpanOut]


@router.get("/assertions/{assertion_id}/evidence", response_model=EvidenceOut)
def get_evidence(
    assertion_id: uuid.UUID, session: SessionDep, max_spans: int = Query(default=2, ge=1, le=5)
) -> EvidenceOut:
    """Quotes supporting the assertion under the active release (computed once, then cached
    and re-verified against the document text on every read)."""
    release_id, views = evidence.for_assertion(session, assertion_id, max_spans=max_spans)
    return EvidenceOut(
        assertion_id=assertion_id,
        release_id=release_id,
        offsets="unicode-code-points",
        spans=[
            SpanOut(
                id=v.span.id,
                start=v.span.start,
                end=v.span.end,
                quote=v.quote,
                score=round(v.span.score, 4),
                rank=v.span.rank,
                method=v.span.method,
                deletion_drop=None
                if v.span.deletion_drop is None
                else round(v.span.deletion_drop, 4),
            )
            for v in views
        ],
    )
