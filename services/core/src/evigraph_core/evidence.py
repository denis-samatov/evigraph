"""Evidence spans: exact quotes from a document version that support a concept.

Offsets are Unicode code points into the version's canonical text (Python string indices);
browser clients that index UTF-16 must convert (e.g. `Array.from(text)` in JavaScript).
A span is stored with the SHA-256 of its quote and re-verified on every read, so a quote can
never drift from the immutable text it claims to come from.

Selection: the text is split into passages (paragraphs, numbered items, sentences), each
passage is scored by its contribution to the concept (the engine's `passage_scores`), and the
best positive passages are kept. Faithfulness is checked by deletion: the concept's score is
recomputed with the selected passages removed, and the drop is stored with the evidence.
"""

import hashlib
import itertools
import re
import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from evigraph_core import releases
from evigraph_core.models import Assertion, Concept, DocumentVersion, EvidenceSpan

# Cyrillic and typographic characters are intended: passages of Russian documents.
_BOUNDARY = re.compile(
    r"\n\s*\n"  # blank line
    r"|\n(?=\s*(?:\d+(?:\.\d+)*[.)]|[a-zа-яё]\)|[-•—–]|Статья|Article|ГЛАВА|Глава|CHAPTER)\s)"  # noqa: RUF001
    r"|(?<=[.!?;])\s+(?=[A-ZА-ЯЁ0-9«\"(])"  # noqa: RUF001  (sentence end before a capital)
)
MAX_PASSAGE = 600
MIN_PASSAGE = 40


class EvidenceError(Exception):
    pass


def _trim(text: str, a: int, b: int) -> tuple[int, int]:
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


def segment(text: str) -> list[tuple[int, int]]:
    """Passage spans (start, end) in code points, whitespace-trimmed, short ones merged."""
    cuts = [0, *(m.end() for m in _BOUNDARY.finditer(text)), len(text)]
    raw: list[tuple[int, int]] = []
    for lo, hi in itertools.pairwise(cuts):
        a, b = _trim(text, lo, hi)
        while b - a > MAX_PASSAGE:  # split long passages at a space
            cut = text.rfind(" ", a + MIN_PASSAGE, a + MAX_PASSAGE)
            cut = cut if cut > a else a + MAX_PASSAGE
            raw.append(_trim(text, a, cut))
            a, b = _trim(text, cut, b)
        if b > a:
            raw.append((a, b))
    merged: list[tuple[int, int]] = []
    for a, b in raw:
        short = b - a < MIN_PASSAGE or (merged and merged[-1][1] - merged[-1][0] < MIN_PASSAGE)
        if merged and short and b - merged[-1][0] <= MAX_PASSAGE:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def quote_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class Span:
    start: int
    end: int
    score: float


def select_spans(engine, text: str, concept: int, *, max_spans: int) -> list[Span]:
    spans = segment(text)
    if not spans:
        return []
    scores = engine.passage_scores([text[a:b] for a, b in spans], concept)
    order = np.argsort(-scores, kind="stable")
    return [
        Span(spans[i][0], spans[i][1], float(scores[i])) for i in order[:max_spans] if scores[i] > 0
    ]


def without(text: str, spans: list[Span]) -> str:
    out, pos = [], 0
    for s in sorted(spans, key=lambda s: s.start):
        out.append(text[pos : s.start])
        out.append(" ")
        pos = s.end
    out.append(text[pos:])
    return "".join(out)


def deletion_drop(engine, text: str, concept: int, spans: list[Span], exclude=None) -> float:
    full = engine.score([text], exclude=[exclude]).scores[0, concept]
    reduced = engine.score([without(text, spans)], exclude=[exclude]).scores[0, concept]
    return float(full - reduced)


@dataclass
class EvidenceView:
    span: EvidenceSpan
    quote: str


def _verify(version: DocumentVersion, span: EvidenceSpan) -> str:
    quote = version.canonical_text[span.start : span.end]
    if quote_hash(quote) != span.quote_sha256:
        msg = f"evidence span {span.id} does not match document version {version.id}"
        raise EvidenceError(msg)
    return quote


def for_assertion(
    session: Session, assertion_id: uuid.UUID, *, max_spans: int = 2
) -> tuple[uuid.UUID, list[EvidenceView]]:
    """Evidence for an assertion under the active release; computed once, then re-verified."""
    assertion = session.get(Assertion, assertion_id)
    if assertion is None:
        raise EvidenceError(f"assertion {assertion_id} not found")
    concept = session.get_one(Concept, assertion.concept_id)
    version = session.get_one(DocumentVersion, assertion.document_version_id)
    release = releases.active_release(session, concept.catalog_version_id)
    stored = list(
        session.scalars(
            select(EvidenceSpan)
            .where(EvidenceSpan.assertion_id == assertion.id, EvidenceSpan.release_id == release.id)
            .order_by(EvidenceSpan.rank)
        )
    )
    if not stored:
        bundle = releases.load(release.artifact_uri)
        j = bundle["concept_ids"].index(str(concept.id))
        own = (
            bundle["pool_ids"].index(str(version.id))
            if str(version.id) in bundle["pool_ids"]
            else None
        )
        engine = bundle["engine"]
        spans = select_spans(engine, version.canonical_text, j, max_spans=max_spans)
        drop = (
            deletion_drop(engine, version.canonical_text, j, spans, exclude=own) if spans else None
        )
        for rank, s in enumerate(spans, start=1):
            row = EvidenceSpan(
                assertion_id=assertion.id,
                release_id=release.id,
                document_version_id=version.id,
                start=s.start,
                end=s.end,
                quote_sha256=quote_hash(version.canonical_text[s.start : s.end]),
                score=s.score,
                rank=rank,
                method=f"{engine.kind}:passage-contribution",
                deletion_drop=drop,
            )
            session.add(row)
            stored.append(row)
        session.flush()
    return release.id, [EvidenceView(s, _verify(version, s)) for s in stored]
