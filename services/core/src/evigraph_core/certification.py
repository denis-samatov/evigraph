"""Certifying a release for auto-apply, planning review volume, and monitoring.

Certification: the threshold grid comes from the release's out-of-fold scores on its fit
documents; Learn-then-Test runs on the held-out certification documents (never used for
training, never in the kNN pool). A certification belongs to one release: retraining
produces a new release that must be certified again, so documents added to the pool after
certification can never change a certified model silently.

Monitoring: a share of auto-applied tags is sampled for audit. When the lower Clopper-Pearson
bound of the error rate among audited tags exceeds alpha, there is evidence the guarantee no
longer holds and the certification is suspended; auto-apply stops.
"""

import hashlib
import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from evigraph_core import releases
from evigraph_core.engine import policy
from evigraph_core.models import (
    Assertion,
    AssertionState,
    AuditSample,
    CatalogVersion,
    CertificationRecord,
    CertificationStatus,
    Concept,
    Release,
)
from evigraph_core.settings import Settings


class CertificationError(Exception):
    pass


def certify_release(
    session: Session, *, release_id: uuid.UUID, alpha: float, delta: float, settings: Settings
) -> CertificationRecord:
    release = session.get(Release, release_id)
    if release is None:
        raise CertificationError(f"release {release_id} not found")
    if release.manifest.get("kind") != "trained":
        msg = "only trained releases can be certified; a cold-start release has no held-out scores"
        raise CertificationError(msg)
    bundle = releases.load(release.artifact_uri)
    engine = bundle["engine"]
    version = session.get_one(CatalogVersion, release.catalog_version_id)
    by_id = {
        str(c.id): c
        for c in session.scalars(select(Concept).where(Concept.catalog_version_id == version.id))
    }
    concepts = [by_id[c] for c in bundle["concept_ids"]]
    cert = releases.reviewed(session, version, concepts, part="cert")
    grid = policy.thresholds(
        engine.oof_scores,
        min_applied=settings.cert_grid_min_applied,
        ratio=settings.cert_grid_ratio,
    )

    result = policy.Certification(tau=None)
    auto_recall = 0.0
    if cert.version_ids and len(grid):
        scores = engine.score(cert.texts).scores
        result = policy.certify(scores, cert.y, grid, alpha=alpha, delta=delta)
        if result.tau is not None:
            applied = scores >= result.tau
            correct = int((applied & cert.y).sum())
            auto_recall = correct / max(int(cert.y.sum()), 1)

    status = CertificationStatus.active if result.tau is not None else CertificationStatus.failed
    reason = None
    if not cert.version_ids:
        reason = "no reviewed documents in the certification part"
    elif not len(grid):
        reason = "too few out-of-fold scores to build a threshold grid"
    elif result.tau is None:
        n_docs = len(cert.version_ids)
        reason = f"no threshold reaches alpha={alpha} at delta={delta} on {n_docs} documents"

    if status is CertificationStatus.active:
        session.execute(
            update(CertificationRecord)
            .where(
                CertificationRecord.catalog_version_id == version.id,
                CertificationRecord.status == CertificationStatus.active,
            )
            .values(status=CertificationStatus.superseded)
        )
    record = CertificationRecord(
        release_id=release.id,
        catalog_version_id=version.id,
        alpha=alpha,
        delta=delta,
        tau=result.tau,
        status=status,
        cert_documents=len(cert.version_ids),
        n_applied=result.n_applied,
        n_errors=result.n_errors,
        ucb=round(result.ucb, 5),
        auto_recall=round(auto_recall, 4),
        details={
            "grid_size": len(grid),
            "tested": result.tested[-3:],
            "cert_data_sha256": hashlib.sha256(
                "\n".join(sorted(map(str, cert.version_ids))).encode()
            ).hexdigest(),
        },
        status_reason=reason,
    )
    session.add(record)
    session.flush()
    return record


@dataclass
class MonitorReport:
    certification_id: uuid.UUID
    status: str
    audited: int
    reviewed: int
    errors: int
    risk_lower: float
    risk_upper: float
    alpha: float
    suspended_now: bool


def evaluate(session: Session, certification_id: uuid.UUID, settings: Settings) -> MonitorReport:
    record = session.get(CertificationRecord, certification_id)
    if record is None:
        raise CertificationError(f"certification {certification_id} not found")
    states = list(
        session.scalars(
            select(Assertion.state)
            .join(AuditSample, AuditSample.assertion_id == Assertion.id)
            .where(AuditSample.certification_id == record.id)
        )
    )
    reviewed = [s for s in states if s in (AssertionState.accepted, AssertionState.rejected)]
    errors = sum(s is AssertionState.rejected for s in reviewed)
    lower = policy.cp_lower(errors, len(reviewed), record.delta)
    upper = policy.cp_upper(errors, len(reviewed), record.delta)
    suspended_now = False
    if (
        record.status is CertificationStatus.active
        and len(reviewed) >= settings.min_audit
        and lower > record.alpha
    ):
        record.status = CertificationStatus.suspended
        record.status_reason = (
            f"audit: {errors}/{len(reviewed)} auto-applied tags rejected; "
            f"lower bound {lower:.3f} > alpha {record.alpha}"
        )
        suspended_now = True
        session.flush()
    return MonitorReport(
        certification_id=record.id,
        status=record.status.value,
        audited=len(states),
        reviewed=len(reviewed),
        errors=errors,
        risk_lower=round(lower, 4),
        risk_upper=round(upper, 4),
        alpha=record.alpha,
        suspended_now=suspended_now,
    )


@dataclass
class Plan:
    applied_pairs: int | None
    cert_documents: int | None
    reviewed_documents: int | None


def plan(
    *, alpha: float, delta: float, expected_risk: float, auto_tags_per_document: float
) -> Plan:
    """How many reviewed documents a certification needs, under stated assumptions."""
    pairs = policy.pairs_needed(alpha, delta, expected_risk)
    if pairs is None or auto_tags_per_document <= 0:
        return Plan(pairs, None, None)
    cert_docs = int(np.ceil(pairs / auto_tags_per_document))
    return Plan(pairs, cert_docs, int(np.ceil(cert_docs / releases.CERT_SHARE)))
