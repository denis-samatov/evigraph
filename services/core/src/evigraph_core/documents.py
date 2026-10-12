"""Document ingestion and provenance assignment.

A new document version joins an existing provenance group, checked in this order:
1. the same (source_system, source_id) was ingested before;
2. identical canonical text exists in the project;
3. a near copy (MinHash Jaccard >= threshold) is found through the LSH band index;
4. its word types are contained in an earlier version (containment >= threshold), found
   through an LSH index over word-type MinHash. This catches copies with words deleted,
   which 5-gram MinHash misses from about 5% deletion on (research protocol 4.0).
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
    WordTypeBand,
)
from evigraph_core.settings import Settings


class NotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class SourceRef:
    system: str
    id: str


@dataclass(frozen=True)
class Attribution:
    group_id: uuid.UUID | None
    reason: ProvenanceReason
    jaccard: float | None = None
    containment: float | None = None


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
    types: set[str],
    type_sig,
    source: SourceRef | None,
    settings: Settings,
) -> Attribution:
    if source is not None:
        group = session.scalar(
            select(SourceIdentity.provenance_group_id).where(
                SourceIdentity.project_id == project_id,
                SourceIdentity.source_system == source.system,
                SourceIdentity.source_id == source.id,
            )
        )
        if group is not None:
            return Attribution(group, ProvenanceReason.source_id)

    group = session.scalar(
        select(DocumentVersion.provenance_group_id)
        .where(DocumentVersion.project_id == project_id, DocumentVersion.text_sha256 == digest)
        .order_by(DocumentVersion.created_at)
        .limit(1)
    )
    if group is not None:
        return Attribution(group, ProvenanceReason.exact, jaccard=1.0)

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
        return Attribution(best[1], ProvenanceReason.near, jaccard=round(best[0], 4))
    if type_sig is not None:
        found = _find_container(
            session, project_id=project_id, types=types, type_sig=type_sig, settings=settings
        )
        if found is not None:
            return Attribution(found[1], ProvenanceReason.contained, containment=round(found[0], 4))
    return Attribution(None, ProvenanceReason.new)


def _find_container(
    session: Session, *, project_id: uuid.UUID, types: set[str], type_sig, settings: Settings
) -> tuple[float, uuid.UUID] | None:
    """Best earlier version containing the new version's word types, or None."""
    pairs = list(enumerate(tx.band_buckets(type_sig, settings.minhash_bands)))
    candidates = session.execute(
        select(DocumentVersion.id, DocumentVersion.type_minhash)
        .join(WordTypeBand, WordTypeBand.document_version_id == DocumentVersion.id)
        .where(
            WordTypeBand.project_id == project_id,
            tuple_(WordTypeBand.band, WordTypeBand.bucket).in_(pairs),
        )
        .distinct()
    ).all()
    ranked = sorted(
        ((tx.jaccard(type_sig, tx.from_bytes(blob)), vid) for vid, blob in candidates if blob),
        key=lambda c: c[0],
        reverse=True,
    )[: settings.containment_candidates]
    best: tuple[float, uuid.UUID] | None = None
    for _, vid in ranked:
        row = session.execute(
            select(DocumentVersion.canonical_text, DocumentVersion.provenance_group_id).where(
                DocumentVersion.id == vid
            )
        ).one()
        c = tx.containment(types, tx.word_types(row.canonical_text))
        if c >= settings.containment_threshold and (best is None or c > best[0]):
            best = (c, row.provenance_group_id)
    return best


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
    types = tx.word_types(canonical)
    type_sig = (
        tx.type_minhash(types, settings.minhash_perm)
        if len(types) >= settings.containment_min_types
        else None
    )
    found = _find_group(
        session,
        project_id=project_id,
        canonical=canonical,
        digest=digest,
        sig=sig,
        types=types,
        type_sig=type_sig,
        source=source,
        settings=settings,
    )
    group_id, reason = found.group_id, found.reason
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
        provenance_jaccard=found.jaccard,
        provenance_containment=found.containment,
        type_minhash=tx.to_bytes(type_sig) if type_sig is not None else None,
    )
    session.add(version)
    session.flush()
    for band, bucket in enumerate(tx.band_buckets(sig, settings.minhash_bands)):
        session.add(
            MinhashBand(
                document_version_id=version.id, band=band, project_id=project_id, bucket=bucket
            )
        )
    if type_sig is not None:
        index_word_types(session, version, type_sig, settings)
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


def index_word_types(
    session: Session, version: DocumentVersion, type_sig, settings: Settings
) -> None:
    """Add a version to the word-type LSH index (also used to backfill older versions)."""
    for band, bucket in enumerate(tx.band_buckets(type_sig, settings.minhash_bands)):
        session.add(
            WordTypeBand(
                document_version_id=version.id,
                band=band,
                project_id=version.project_id,
                bucket=bucket,
            )
        )


def backfill_word_types(session: Session, settings: Settings) -> int:
    """Index versions created before containment attribution existed. Returns their number."""
    done = 0
    for version in session.scalars(
        select(DocumentVersion).where(DocumentVersion.type_minhash.is_(None))
    ):
        types = tx.word_types(version.canonical_text)
        if len(types) < settings.containment_min_types:
            continue
        type_sig = tx.type_minhash(types, settings.minhash_perm)
        version.type_minhash = tx.to_bytes(type_sig)
        index_word_types(session, version, type_sig, settings)
        done += 1
    session.flush()
    return done


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
