"""Certification, monitoring and review-volume planning."""

import uuid

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import select

from evigraph_core import certification
from evigraph_core.api.deps import SessionDep, SettingsDep
from evigraph_core.api.schemas import Out, Strict
from evigraph_core.models import CertificationRecord

router = APIRouter()


class CertifyIn(Strict):
    alpha: float = Field(gt=0, lt=1)
    delta: float = Field(default=0.1, gt=0, lt=1)


class CertificationOut(Out):
    id: uuid.UUID
    release_id: uuid.UUID
    catalog_version_id: uuid.UUID
    alpha: float
    delta: float
    tau: float | None
    status: str
    cert_documents: int
    n_applied: int
    n_errors: int
    ucb: float
    auto_recall: float
    details: dict
    status_reason: str | None


class MonitorOut(Strict):
    certification_id: uuid.UUID
    status: str
    audited: int
    reviewed: int
    errors: int
    risk_lower: float
    risk_upper: float
    alpha: float
    suspended_now: bool


class PlanOut(Strict):
    applied_pairs: int | None
    cert_documents: int | None
    reviewed_documents: int | None
    note: str


@router.post(
    "/releases/{release_id}/certifications", status_code=201, response_model=CertificationOut
)
def certify(release_id: uuid.UUID, body: CertifyIn, session: SessionDep, settings: SettingsDep):
    return certification.certify_release(
        session, release_id=release_id, alpha=body.alpha, delta=body.delta, settings=settings
    )


@router.get("/catalog-versions/{version_id}/certifications", response_model=list[CertificationOut])
def list_certifications(version_id: uuid.UUID, session: SessionDep):
    return session.scalars(
        select(CertificationRecord)
        .where(CertificationRecord.catalog_version_id == version_id)
        .order_by(CertificationRecord.created_at.desc())
    ).all()


@router.get("/certifications/{certification_id}/monitor", response_model=MonitorOut)
def monitor(certification_id: uuid.UUID, session: SessionDep, settings: SettingsDep):
    report = certification.evaluate(session, certification_id, settings)
    return MonitorOut(**report.__dict__)


@router.get("/planning/certification", response_model=PlanOut)
def plan(
    alpha: float = Query(gt=0, lt=1),
    expected_risk: float = Query(ge=0, lt=1),
    auto_tags_per_document: float = Query(gt=0),
    delta: float = Query(default=0.1, gt=0, lt=1),
) -> PlanOut:
    p = certification.plan(
        alpha=alpha,
        delta=delta,
        expected_risk=expected_risk,
        auto_tags_per_document=auto_tags_per_document,
    )
    return PlanOut(
        **p.__dict__,
        note=(
            "Assumes the expected error rate among auto-applied tags and the number of tags "
            "applied per document; reviewed_documents includes the training share "
            "(certification uses a held-out part of reviewed documents)."
        ),
    )
