"""Relational model.

The claim "concept C applies to document version D" (Assertion), a model's score for it
(Assessment) and an expert's decision about it (ReviewEvent) are stored separately, so a new
model release can re-score documents without touching the review history.

A document version is immutable. Each version belongs to a provenance group: copies and
near-copies share a group and count as one source wherever evidence is aggregated.
A document version has gold labels only after a ReviewCompletion: before that, an unaccepted
concept is unknown, not negative.
"""

import datetime as dt
import enum
import uuid
from typing import ClassVar

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map: ClassVar = {dict: JSON}


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _enum(cls: type[enum.Enum]) -> Enum:
    return Enum(cls, native_enum=False, length=32, validate_strings=True)


class Timestamped:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Project(Timestamped, Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class Catalog(Timestamped, Base):
    __tablename__ = "catalogs"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))


class CatalogStatus(enum.StrEnum):
    draft = "draft"
    published = "published"


class CatalogVersion(Timestamped, Base):
    __tablename__ = "catalog_versions"
    __table_args__ = (UniqueConstraint("catalog_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    catalog_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalogs.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[CatalogStatus] = mapped_column(_enum(CatalogStatus))
    concepts: Mapped[list["Concept"]] = relationship(order_by="Concept.key")


class Concept(Base):
    __tablename__ = "concepts"
    __table_args__ = (UniqueConstraint("catalog_version_id", "key"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    catalog_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_versions.id"))
    key: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(500))
    definition: Mapped[str | None] = mapped_column(Text)


class ProvenanceGroup(Timestamped, Base):
    __tablename__ = "provenance_groups"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))


class Document(Timestamped, Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str | None] = mapped_column(String(1000))


class ProvenanceReason(enum.StrEnum):
    new = "new"  # no earlier source found
    source_id = "source_id"  # same (source_system, source_id) seen before
    exact = "exact"  # identical canonical text
    near = "near"  # MinHash Jaccard >= threshold


class DocumentVersion(Timestamped, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version"),
        Index("ix_document_versions_sha", "project_id", "text_sha256"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    version: Mapped[int] = mapped_column(Integer)
    canonical_text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    source_system: Mapped[str | None] = mapped_column(String(200))
    source_id: Mapped[str | None] = mapped_column(String(500))
    minhash: Mapped[bytes] = mapped_column(LargeBinary)
    provenance_group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provenance_groups.id"))
    provenance_reason: Mapped[ProvenanceReason] = mapped_column(_enum(ProvenanceReason))
    provenance_jaccard: Mapped[float | None] = mapped_column(Float)


class MinhashBand(Base):
    """LSH index: one row per (version, band); candidates share (band, bucket)."""

    __tablename__ = "minhash_bands"
    __table_args__ = (Index("ix_minhash_bands_lookup", "project_id", "band", "bucket"),)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), primary_key=True
    )
    band: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    bucket: Mapped[int] = mapped_column(BigInteger)


class SourceIdentity(Base):
    """A source-system identifier seen before maps to its provenance group."""

    __tablename__ = "source_identities"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(200), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(500), primary_key=True)
    provenance_group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provenance_groups.id"))


class AssertionState(enum.StrEnum):
    proposed = "proposed"  # suggested by a model, not reviewed
    accepted = "accepted"  # confirmed or added by an expert
    rejected = "rejected"  # rejected by an expert
    auto_applied = "auto_applied"  # applied by a certified policy, not reviewed


class Assertion(Timestamped, Base):
    __tablename__ = "assertions"
    __table_args__ = (UniqueConstraint("document_version_id", "concept_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"))
    concept_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concepts.id"))
    state: Mapped[AssertionState] = mapped_column(_enum(AssertionState))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Release(Timestamped, Base):
    """A trained engine for one catalog version: artifact plus its full manifest."""

    __tablename__ = "releases"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    catalog_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_versions.id"))
    artifact_uri: Mapped[str] = mapped_column(String(1000))
    manifest: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class Assessment(Timestamped, Base):
    __tablename__ = "assessments"
    __table_args__ = (UniqueConstraint("assertion_id", "release_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    assertion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assertions.id"))
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"))
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[dict] = mapped_column(JSON)  # supporting reviewed documents


class ReviewKind(enum.StrEnum):
    accept = "accept"
    reject = "reject"
    add = "add"  # expert adds a concept the model did not propose
    withdraw = "withdraw"  # undo the previous decision; the assertion returns to proposed


class ReviewEvent(Timestamped, Base):
    __tablename__ = "review_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    assertion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assertions.id"))
    kind: Mapped[ReviewKind] = mapped_column(_enum(ReviewKind))
    reviewer: Mapped[str] = mapped_column(String(200))
    comment: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    from_state: Mapped[AssertionState | None] = mapped_column(_enum(AssertionState))  # None: add
    to_state: Mapped[AssertionState] = mapped_column(_enum(AssertionState))
    resulting_revision: Mapped[int] = mapped_column(Integer)


class ReviewCompletion(Timestamped, Base):
    """An expert declares a document fully reviewed for a catalog version: gold labels exist."""

    __tablename__ = "review_completions"
    __table_args__ = (UniqueConstraint("document_version_id", "catalog_version_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"))
    catalog_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_versions.id"))
    reviewer: Mapped[str] = mapped_column(String(200))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)


class CertificationStatus(enum.StrEnum):
    active = "active"  # auto-apply enabled for the release
    failed = "failed"  # no threshold could be certified
    superseded = "superseded"  # replaced by a newer certification
    suspended = "suspended"  # monitoring found evidence that realised risk exceeds alpha


class CertificationRecord(Timestamped, Base):
    """Learn-then-Test certification of a release's threshold on held-out reviewed data."""

    __tablename__ = "certifications"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"))
    catalog_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_versions.id"))
    alpha: Mapped[float] = mapped_column(Float)
    delta: Mapped[float] = mapped_column(Float)
    tau: Mapped[float | None] = mapped_column(Float)
    status: Mapped[CertificationStatus] = mapped_column(_enum(CertificationStatus))
    cert_documents: Mapped[int] = mapped_column(Integer)
    n_applied: Mapped[int] = mapped_column(Integer)
    n_errors: Mapped[int] = mapped_column(Integer)
    ucb: Mapped[float] = mapped_column(Float)
    auto_recall: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON)
    status_reason: Mapped[str | None] = mapped_column(Text)


class AuditSample(Timestamped, Base):
    """An auto-applied assertion drawn for expert audit under a certification."""

    __tablename__ = "audit_samples"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    assertion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assertions.id"), unique=True)
    certification_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("certifications.id"))
