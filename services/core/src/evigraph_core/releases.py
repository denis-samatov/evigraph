"""Training, storing and activating engine releases; producing suggestions.

Reviewed documents are split by provenance group into a *fit* part and a *certification*
part (CERT_SHARE of groups, chosen by a stable hash). The certification part is never used
for training, so a threshold can later be certified on it (milestone M5). With fewer than
MIN_TRAINED fit documents a cold-start release ranks concepts by their label and definition.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from evigraph_core.catalogs import require_published
from evigraph_core.engine.model import ColdStartEngine, TrainedEngine
from evigraph_core.models import (
    Assertion,
    AssertionState,
    Assessment,
    Catalog,
    CatalogVersion,
    Concept,
    DocumentVersion,
    Release,
)
from evigraph_core.reviews import gold_labels
from evigraph_core.settings import Settings

CERT_SHARE = 0.3
MIN_TRAINED = 30
MAX_COLD_START_CORPUS = 5000


class ReleaseError(Exception):
    pass


def is_cert_group(catalog_version_id: uuid.UUID, group_id: uuid.UUID) -> bool:
    digest = hashlib.sha256(f"{catalog_version_id}:{group_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < CERT_SHARE


@dataclass
class ReviewedSet:
    version_ids: list[uuid.UUID]
    texts: list[str]
    groups: list[uuid.UUID]
    y: np.ndarray


def reviewed(
    session: Session, catalog_version: CatalogVersion, concepts: list[Concept], *, part: str
) -> ReviewedSet:
    """Fully reviewed documents of the catalog version, `part` = "fit" or "cert"."""
    gold = gold_labels(session, catalog_version)
    col = {c.id: j for j, c in enumerate(concepts)}
    rows = session.execute(
        select(
            DocumentVersion.id, DocumentVersion.canonical_text, DocumentVersion.provenance_group_id
        )
        .where(DocumentVersion.id.in_(list(gold)))
        .order_by(DocumentVersion.id)
    ).all()
    keep = [r for r in rows if is_cert_group(catalog_version.id, r[2]) == (part == "cert")]
    y = np.zeros((len(keep), len(concepts)), dtype=bool)
    for i, (vid, _, _) in enumerate(keep):
        for cid in gold[vid]:
            y[i, col[cid]] = True
    return ReviewedSet([r[0] for r in keep], [r[1] for r in keep], [r[2] for r in keep], y)


def _concept_text(c: Concept) -> str:
    return f"{c.label}. {c.definition or ''}"


def train(session: Session, catalog_version_id: uuid.UUID, settings: Settings) -> Release:
    version = require_published(session, catalog_version_id)
    concepts = sorted(version.concepts, key=lambda c: c.key)
    fit = reviewed(session, version, concepts, part="fit")
    started = dt.datetime.now(dt.UTC)
    if len(fit.version_ids) >= MIN_TRAINED and len(set(fit.groups)) >= 2:
        engine: TrainedEngine | ColdStartEngine = TrainedEngine(
            k=settings.knn_k,
            candidates=settings.knn_candidates,
            min_positives=settings.min_positives_for_text_model,
            folds=settings.stacker_folds,
        ).fit(fit.texts, fit.y, np.array([str(g) for g in fit.groups]))
        pool_ids = fit.version_ids
    else:
        project_id = session.get_one(Catalog, version.catalog_id).project_id
        corpus = list(
            session.scalars(
                select(DocumentVersion.canonical_text)
                .where(DocumentVersion.project_id == project_id)
                .limit(MAX_COLD_START_CORPUS)
            )
        )
        engine = ColdStartEngine().fit([_concept_text(c) for c in concepts], corpus)
        pool_ids = []

    release = Release(catalog_version_id=version.id, artifact_uri="", manifest={}, active=False)
    session.add(release)
    session.flush()
    path = Path(settings.artifact_dir) / "releases" / f"{release.id}.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "engine": engine,
            "concept_ids": [str(c.id) for c in concepts],
            "pool_ids": [str(p) for p in pool_ids],
        },
        path,
    )
    release.artifact_uri = str(path)
    release.manifest = {
        "kind": engine.kind,
        "catalog_version_id": str(version.id),
        "concepts": len(concepts),
        "fit_documents": len(fit.version_ids),
        "fit_groups": len(set(fit.groups)),
        "fit_data_sha256": hashlib.sha256(
            "\n".join(sorted(map(str, fit.version_ids))).encode()
        ).hexdigest(),
        "cert_share": CERT_SHARE,
        "text_models": len(engine.text_models) if isinstance(engine, TrainedEngine) else 0,
        "settings": {
            "knn_k": settings.knn_k,
            "knn_candidates": settings.knn_candidates,
            "min_positives_for_text_model": settings.min_positives_for_text_model,
            "stacker_folds": settings.stacker_folds,
        },
        "versions": {"scikit-learn": sklearn.__version__, "numpy": np.__version__},
        "trained_at": started.isoformat(timespec="seconds"),
    }
    session.execute(
        update(Release).where(Release.catalog_version_id == version.id).values(active=False)
    )
    release.active = True
    session.flush()
    return release


@lru_cache(maxsize=8)
def _load(artifact_uri: str) -> dict:
    return joblib.load(artifact_uri)


def active_release(session: Session, catalog_version_id: uuid.UUID) -> Release:
    release = session.scalar(
        select(Release).where(
            Release.catalog_version_id == catalog_version_id, Release.active.is_(True)
        )
    )
    if release is None:
        msg = "no active release for this catalog version; train one first"
        raise ReleaseError(msg)
    return release


@dataclass
class Suggestion:
    assertion: Assertion
    concept: Concept
    score: float
    rank: int
    evidence: list[dict]


def suggest(
    session: Session,
    *,
    document_version_id: uuid.UUID,
    catalog_version_id: uuid.UUID,
    top_k: int,
) -> tuple[Release, list[Suggestion]]:
    version = session.get(DocumentVersion, document_version_id)
    if version is None:
        msg = f"document version {document_version_id} not found"
        raise ReleaseError(msg)
    release = active_release(session, catalog_version_id)
    bundle = _load(release.artifact_uri)
    concepts = {
        c.id: c
        for c in session.scalars(
            select(Concept).where(Concept.catalog_version_id == catalog_version_id)
        )
    }
    order = [concepts[uuid.UUID(c)] for c in bundle["concept_ids"]]
    pool_ids = bundle["pool_ids"]
    own = pool_ids.index(str(version.id)) if str(version.id) in pool_ids else None
    scored = bundle["engine"].score([version.canonical_text], exclude=[own])
    scores = scored.scores[0]
    ranking = np.argsort(-scores, kind="stable")[:top_k]

    existing = {
        a.concept_id: a
        for a in session.scalars(
            select(Assertion).where(Assertion.document_version_id == version.id)
        )
    }
    out = []
    for rank, j in enumerate(ranking, start=1):
        concept = order[j]
        assertion = existing.get(concept.id)
        if assertion is None:
            assertion = Assertion(
                document_version_id=version.id,
                concept_id=concept.id,
                state=AssertionState.proposed,
                revision=1,
            )
            session.add(assertion)
            session.flush()
        evidence = [
            {
                "document_version_id": pool_ids[e.pool_index],
                "similarity": e.similarity,
                "has_concept": e.has_concept,
            }
            for e in scored.evidence[0][j]
        ]
        assessment = session.scalar(
            select(Assessment).where(
                Assessment.assertion_id == assertion.id, Assessment.release_id == release.id
            )
        )
        if assessment is None:
            session.add(
                Assessment(
                    assertion_id=assertion.id,
                    release_id=release.id,
                    score=float(scores[j]),
                    rank=rank,
                    evidence={"supporting": evidence},
                )
            )
        out.append(Suggestion(assertion, concept, float(scores[j]), rank, evidence))
    session.flush()
    return release, out
