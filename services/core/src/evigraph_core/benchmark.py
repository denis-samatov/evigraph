"""Pilot benchmark: the full product workflow at a given amount of reviewed data.

For one catalog and N reviewed documents: create the project and catalog, ingest the documents
(provenance groups are assigned as in production), simulate expert review with gold labels,
train a release, certify it at each alpha, then score later documents with the certified
release and measure what an expert would see: ranking quality, automation and realised risk.
"""

import time
import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session, sessionmaker

from evigraph_core import catalogs, certification, documents, releases, reviews
from evigraph_core import evidence as ev
from evigraph_core.models import Catalog, CertificationStatus, Project
from evigraph_core.settings import Settings


@dataclass(frozen=True)
class Doc:
    key: str
    text: str
    labels: frozenset[str]


def _r_precision(y: np.ndarray, scores: np.ndarray) -> float:
    vals = []
    order = np.argsort(-scores, axis=1, kind="stable")
    for i in range(len(y)):
        r = int(y[i].sum())
        if r:
            vals.append(y[i, order[i, :r]].mean())
    return float(np.mean(vals)) if vals else float("nan")


def run_pilot(
    factory: sessionmaker[Session],
    settings: Settings,
    *,
    name: str,
    concepts: list[catalogs.ConceptSpec],
    reviewed: list[Doc],
    evaluation: list[Doc],
    alphas: tuple[float, ...] = (0.10, 0.05),
    delta: float = 0.1,
    source_system: str = "benchmark",
    evidence_sample: int = 300,
) -> dict:
    t0 = time.perf_counter()
    with factory() as s:
        project = Project(name=f"{name}-{uuid.uuid4().hex[:6]}")
        s.add(project)
        s.flush()
        catalog = Catalog(project_id=project.id, name=name)
        s.add(catalog)
        s.flush()
        version = catalogs.create_version(s, catalog=catalog, concepts=concepts)
        catalogs.publish(s, version)
        s.commit()
        concept_ids = {c.key: c.id for c in version.concepts}

    for d in reviewed:
        with factory() as s:
            dv = documents.create_document(
                s,
                project_id=project.id,
                title=d.key,
                raw_text=d.text,
                source=documents.SourceRef(source_system, d.key),
                settings=settings,
            )
            for k in sorted(d.labels):
                reviews.add_concept(
                    s,
                    document_version_id=dv.id,
                    concept_id=concept_ids[k],
                    reviewer="benchmark",
                    idempotency_key=uuid.uuid4().hex,
                )
            reviews.complete(
                s,
                document_version_id=dv.id,
                catalog_version_id=version.id,
                reviewer="benchmark",
                idempotency_key=uuid.uuid4().hex,
            )
            s.commit()
    t_ingest = time.perf_counter() - t0

    with factory() as s:
        release = releases.train(s, version.id, settings)
        s.commit()
    certs = {}
    for a in alphas:
        with factory() as s:
            certs[a] = certification.certify_release(
                s, release_id=release.id, alpha=a, delta=delta, settings=settings
            )
            s.commit()

    engine = releases.load(release.artifact_uri)["engine"]
    keys = [c.key for c in sorted(concepts, key=lambda c: c.key)]
    col = {k: j for j, k in enumerate(keys)}
    y = np.zeros((len(evaluation), len(keys)), dtype=bool)
    for i, d in enumerate(evaluation):
        for k in d.labels:
            y[i, col[k]] = True
    scores = engine.score([d.text for d in evaluation]).scores
    top1 = scores.argmax(axis=1)

    result: dict = {
        "catalog": name,
        "concepts": len(keys),
        "reviewed_documents": len(reviewed),
        "release": {
            k: release.manifest[k] for k in ("kind", "fit_documents", "fit_groups", "text_models")
        },
        "evaluation_documents": len(evaluation),
        "top1_precision": round(float(y[np.arange(len(y)), top1].mean()), 4),
        "mrp": round(_r_precision(y, scores), 4),
        "certifications": {},
        "seconds": None,
    }
    for a, c in certs.items():
        entry = {
            "status": c.status.value,
            "tau": c.tau,
            "cert_documents": c.cert_documents,
            "ucb": c.ucb,
            "auto_recall_heldout": c.auto_recall,
            "reason": c.status_reason,
        }
        if c.status is CertificationStatus.active or c.tau is not None:
            auto = scores >= c.tau
            applied = int(auto.sum())
            errors = int((auto & ~y).sum())
            entry.update(
                {
                    "eval_applied": applied,
                    "eval_realised_risk": round(errors / applied, 4) if applied else None,
                    "eval_auto_recall": round((applied - errors) / max(int(y.sum()), 1), 4),
                    "eval_docs_fully_auto": round(float(np.all(auto == y, axis=1).mean()), 4),
                }
            )
        result["certifications"][str(a)] = entry
    result["evidence"] = evidence_faithfulness(
        engine, evaluation, scores, y, sample=evidence_sample
    )
    result["seconds"] = {
        "ingest_and_review": round(t_ingest),
        "total": round(time.perf_counter() - t0),
    }
    return result


def evidence_faithfulness(engine, evaluation: list[Doc], scores, y, *, sample: int) -> dict:
    """Deletion test on correct top suggestions: removing the two evidence passages should lower
    the concept's score more than removing two random passages of the same document."""
    rng = np.random.default_rng(0)
    drops, random_drops, wins = [], [], 0
    for i in rng.permutation(len(evaluation))[:sample]:
        j = int(np.argmax(scores[i]))
        if not y[i, j]:
            continue
        text = evaluation[i].text
        passages = ev.segment(text)
        spans = ev.select_spans(engine, text, j, max_spans=2)
        if len(passages) < 4 or not spans:
            continue
        picks = rng.choice(len(passages), size=len(spans), replace=False)
        rand = [ev.Span(passages[p][0], passages[p][1], 0.0) for p in picks]
        d, r = ev.deletion_drop(engine, text, j, spans), ev.deletion_drop(engine, text, j, rand)
        drops.append(d)
        random_drops.append(r)
        wins += d > r
    n = len(drops)
    return {
        "documents": n,
        "mean_drop_evidence": round(float(np.mean(drops)), 4) if n else None,
        "mean_drop_random": round(float(np.mean(random_drops)), 4) if n else None,
        "share_evidence_beats_random": round(wins / n, 4) if n else None,
    }
