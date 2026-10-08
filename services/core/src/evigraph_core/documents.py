"""Document ingestion and provenance assignment.

A new document version joins an existing provenance group, checked in this order:
1. the same (source_system, source_id) was ingested before;
2. identical canonical text exists in the project;
3. a near copy (MinHash Jaccard >= threshold) is found through the LSH band index.
Otherwise it starts a new group. Ingestion is serialised per project with an advisory lock so
that two concurrent copies cannot end up in different groups.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text, tuple_
from sqlalchemy.orm import Session

from evigraph_core import text as tx
from evigraph_core.models import (
    Document,
    DocumentVersion,
    MinhashBand,
    ProvenanceGroup,
    ProvenanceReason,
    SourceIdentity,
)
from evigraph_core.settings import Settings


class NotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class SourceRef:
    system: str
    id: str


def _lock_project(session: Session, project_id: uuid.UUID) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"ingest:{project_id}"}
    )


def _find_group(
    session: Session,
    *,
    project_id: uuid.UUID,
    canonical: str,
    digest: str,
    sig,
    source: SourceRef | None,
    settings: Settings,
) -> tuple[uuid.UUID | None, ProvenanceReason, float | None]:
    if source is not None:
        group = session.scalar(
            select(SourceIdentity.provenance_group_id).where(
                SourceIdentity.project_id == project_id,
                SourceIdentity.source_system == source.system,
                SourceIdentity.source_id == source.id,
            )
        )
        if group is not None:
            return group, ProvenanceReason.source_id, None

    group = session.scalar(
        select(DocumentVersion.provenance_group_id)
        .where(DocumentVersion.project_id == project_id, DocumentVersion.text_sha256 == digest)
        .order_by(DocumentVersion.created_at)
        .limit(1)
    )
    if group is not None:
        return group, ProvenanceReason.exact, 1.0

    buckets = tx.band_buckets(sig, settings.minhash_bands)
    pairs = list(enumerate(buckets))
    candidates = session.execute(
        select(DocumentVersion.id, DocumentVersion.minhash, DocumentVersion.provenance_group_id)
        .join(MinhashBand, MinhashBand.document_version_id == DocumentVersion.id)
        .where(
            MinhashBand.project_id == project_id,
            tuple_(MinhashBand.band, MinhashBand.bucket).in_(pairs),
        )
        .distinct()
    ).all()
    best: tuple[float, uuid.UUID] | None = None
    for _, blob, grp in candidates:
        j = tx.jaccard(sig, tx.from_bytes(blob))
        if j >= settings.near_duplicate_threshold and (best is None or j > best[0]):
            best = (j, grp)
    if best is not None:
        return best[1], ProvenanceReason.near, round(best[0], 4)
    return None, ProvenanceReason.new, None


def add_version(
    session: Session,
    *,
    project_id: uuid.UUID,
    document: Document,
    raw_text: str,
    source: SourceRef | None,
    settings: Settings,
) -> DocumentVersion:
    _lock_project(session, project_id)
    canonical = tx.canonicalize(raw_text)
    digest = tx.sha256(canonical)
    sig = tx.minhash(canonical, settings.minhash_perm)
    group_id, reason, jac = _find_group(
        session,
        project_id=project_id,
        canonical=canonical,
        digest=digest,
        sig=sig,
        source=source,
        settings=settings,
    )
    if group_id is None:
        group = ProvenanceGroup(project_id=project_id)
        session.add(group)
        session.flush()
        group_id = group.id

    last = session.scalar(
        select(func.max(DocumentVersion.version)).where(DocumentVersion.document_id == document.id)
    )
    version = DocumentVersion(
        document_id=document.id,
        project_id=project_id,
        version=(last or 0) + 1,
        canonical_text=canonical,
        text_sha256=digest,
        source_system=source.system if source else None,
        source_id=source.id if source else None,
        minhash=tx.to_bytes(sig),
        provenance_group_id=group_id,
        provenance_reason=reason,
        provenance_jaccard=jac,
    )
    session.add(version)
    session.flush()
    for band, bucket in enumerate(tx.band_buckets(sig, settings.minhash_bands)):
        session.add(
            MinhashBand(
                document_version_id=version.id, band=band, project_id=project_id, bucket=bucket
            )
        )
    if source is not None and reason is not ProvenanceReason.source_id:
        session.add(
            SourceIdentity(
                project_id=project_id,
                source_system=source.system,
                source_id=source.id,
                provenance_group_id=group_id,
            )
        )
    session.flush()
    return version


def create_document(
    session: Session,
    *,
    project_id: uuid.UUID,
    title: str | None,
    raw_text: str,
    source: SourceRef | None,
    settings: Settings,
) -> DocumentVersion:
    document = Document(project_id=project_id, title=title)
    session.add(document)
    session.flush()
    return add_version(
        session,
        project_id=project_id,
        document=document,
        raw_text=raw_text,
        source=source,
        settings=settings,
    )
