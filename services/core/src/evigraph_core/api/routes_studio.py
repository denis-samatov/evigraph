"""Read models for EviGraph Studio (the IDE): listings, document text, review view, local graph."""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from evigraph_core import releases
from evigraph_core.api.deps import SessionDep
from evigraph_core.api.schemas import Out, Strict
from evigraph_core.models import (
    Assertion,
    Assessment,
    Catalog,
    CatalogVersion,
    CertificationRecord,
    CertificationStatus,
    Concept,
    Document,
    DocumentVersion,
    Project,
    Release,
    ReviewCompletion,
)

router = APIRouter()


class ProjectOut(Out):
    id: uuid.UUID
    name: str


class CatalogSummary(Strict):
    id: uuid.UUID
    name: str
    versions: list[dict]


class DocumentSummary(Strict):
    document_id: uuid.UUID
    version_id: uuid.UUID
    version: int
    title: str | None
    chars: int
    provenance_group_id: uuid.UUID
    provenance_reason: str
    group_size: int


class TextOut(Strict):
    version_id: uuid.UUID
    text: str
    offsets: str


class ReviewRow(Strict):
    assertion_id: uuid.UUID
    concept_id: uuid.UUID
    concept_key: str
    concept_label: str
    state: str
    revision: int
    score: float | None
    rank: int | None
    decision: str | None


class ReviewView(Strict):
    document_version_id: uuid.UUID
    catalog_version_id: uuid.UUID
    release_id: uuid.UUID | None
    certification: dict | None
    completed: bool
    assertions: list[ReviewRow]


class GraphNode(Strict):
    id: str
    kind: str  # document | concept | reviewed_document | copy
    label: str
    state: str | None = None
    score: float | None = None


class GraphEdge(Strict):
    id: str
    source: str
    target: str
    kind: str  # asserts | supported_by | same_provenance
    weight: float | None = None


class GraphOut(Strict):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: SessionDep):
    return session.scalars(select(Project).order_by(Project.created_at.desc()).limit(200)).all()


@router.get("/projects/{project_id}/catalogs", response_model=list[CatalogSummary])
def list_catalogs(project_id: uuid.UUID, session: SessionDep):
    out = []
    for c in session.scalars(select(Catalog).where(Catalog.project_id == project_id)):
        versions = session.scalars(
            select(CatalogVersion)
            .where(CatalogVersion.catalog_id == c.id)
            .order_by(CatalogVersion.version.desc())
        ).all()
        out.append(
            CatalogSummary(
                id=c.id,
                name=c.name,
                versions=[
                    {"id": str(v.id), "version": v.version, "status": v.status.value}
                    for v in versions
                ],
            )
        )
    return out


@router.get("/projects/{project_id}/documents", response_model=list[DocumentSummary])
def list_documents(project_id: uuid.UUID, session: SessionDep, limit: int = 200, offset: int = 0):
    latest = (
        select(DocumentVersion.document_id, func.max(DocumentVersion.version).label("v"))
        .where(DocumentVersion.project_id == project_id)
        .group_by(DocumentVersion.document_id)
        .subquery()
    )
    group_size = (
        select(DocumentVersion.provenance_group_id, func.count().label("n"))
        .where(DocumentVersion.project_id == project_id)
        .group_by(DocumentVersion.provenance_group_id)
        .subquery()
    )
    rows = session.execute(
        select(DocumentVersion, Document.title, group_size.c.n)
        .join(
            latest,
            (latest.c.document_id == DocumentVersion.document_id)
            & (latest.c.v == DocumentVersion.version),
        )
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(group_size, group_size.c.provenance_group_id == DocumentVersion.provenance_group_id)
        .order_by(DocumentVersion.created_at.desc())
        .limit(min(limit, 1000))
        .offset(offset)
    ).all()
    return [
        DocumentSummary(
            document_id=v.document_id,
            version_id=v.id,
            version=v.version,
            title=title,
            chars=len(v.canonical_text),
            provenance_group_id=v.provenance_group_id,
            provenance_reason=v.provenance_reason.value,
            group_size=n,
        )
        for v, title, n in rows
    ]


@router.get("/document-versions/{version_id}/text", response_model=TextOut)
def document_text(version_id: uuid.UUID, session: SessionDep) -> TextOut:
    v = session.get(DocumentVersion, version_id)
    if v is None:
        raise HTTPException(404, "document version not found")
    return TextOut(version_id=v.id, text=v.canonical_text, offsets="unicode-code-points")


def _active(
    session, catalog_version_id: uuid.UUID
) -> tuple[Release | None, CertificationRecord | None]:
    try:
        release = releases.active_release(session, catalog_version_id)
    except releases.ReleaseError:
        return None, None
    return release, releases.certification_for(session, release)


@router.get("/document-versions/{version_id}/review", response_model=ReviewView)
def review_view(version_id: uuid.UUID, catalog_version_id: uuid.UUID, session: SessionDep):
    release, cert = _active(session, catalog_version_id)
    scores = (
        select(Assessment.assertion_id, Assessment.score, Assessment.rank)
        .where(Assessment.release_id == (release.id if release else None))
        .subquery()
    )
    rows = session.execute(
        select(Assertion, Concept, scores.c.score, scores.c.rank)
        .join(Concept, Concept.id == Assertion.concept_id)
        .outerjoin(scores, scores.c.assertion_id == Assertion.id)
        .where(
            Assertion.document_version_id == version_id,
            Concept.catalog_version_id == catalog_version_id,
        )
        .order_by(scores.c.rank.nulls_last(), Concept.key)
    ).all()
    completed = session.scalar(
        select(func.count())
        .select_from(ReviewCompletion)
        .where(
            ReviewCompletion.document_version_id == version_id,
            ReviewCompletion.catalog_version_id == catalog_version_id,
        )
    )
    tau = cert.tau if cert is not None and cert.status is CertificationStatus.active else None
    return ReviewView(
        document_version_id=version_id,
        catalog_version_id=catalog_version_id,
        release_id=release.id if release else None,
        certification=(
            {"id": str(cert.id), "alpha": cert.alpha, "delta": cert.delta, "tau": cert.tau}
            if cert
            else None
        ),
        completed=bool(completed),
        assertions=[
            ReviewRow(
                assertion_id=a.id,
                concept_id=c.id,
                concept_key=c.key,
                concept_label=c.label,
                state=a.state.value,
                revision=a.revision,
                score=None if score is None else round(float(score), 4),
                rank=rank,
                decision=None
                if score is None
                else ("auto_applied" if tau is not None and score >= tau else "needs_review"),
            )
            for a, c, score, rank in rows
        ],
    )


@router.get("/document-versions/{version_id}/graph", response_model=GraphOut)
def local_graph(
    version_id: uuid.UUID, catalog_version_id: uuid.UUID, session: SessionDep, max_concepts: int = 8
) -> GraphOut:
    """The document, its strongest concepts, the reviewed documents supporting them and the
    other members of its provenance group."""
    v = session.get(DocumentVersion, version_id)
    if v is None:
        raise HTTPException(404, "document version not found")
    view = review_view(version_id, catalog_version_id, session)
    doc_id = f"doc:{v.id}"
    title = session.scalar(select(Document.title).where(Document.id == v.document_id))
    nodes = {doc_id: GraphNode(id=doc_id, kind="document", label=title or f"v{v.version}")}
    edges: list[GraphEdge] = []
    release_id = view.release_id
    for row in view.assertions[:max_concepts]:
        cid = f"concept:{row.concept_id}"
        nodes[cid] = GraphNode(
            id=cid, kind="concept", label=row.concept_label[:60], state=row.state, score=row.score
        )
        edges.append(
            GraphEdge(
                id=f"a:{row.assertion_id}",
                source=doc_id,
                target=cid,
                kind="asserts",
                weight=row.score,
            )
        )
        if release_id is None:
            continue
        assessment = session.scalar(
            select(Assessment).where(
                Assessment.assertion_id == row.assertion_id, Assessment.release_id == release_id
            )
        )
        for e in (assessment.evidence.get("supporting", []) if assessment else [])[:3]:
            if not e["has_concept"]:
                continue
            rid = f"doc:{e['document_version_id']}"
            if rid not in nodes:
                other = session.get(DocumentVersion, uuid.UUID(e["document_version_id"]))
                label = (
                    session.scalar(select(Document.title).where(Document.id == other.document_id))
                    if other
                    else None
                )
                nodes[rid] = GraphNode(id=rid, kind="reviewed_document", label=label or "reviewed")
            edges.append(
                GraphEdge(
                    id=f"s:{row.assertion_id}:{rid}",
                    source=cid,
                    target=rid,
                    kind="supported_by",
                    weight=e["similarity"],
                )
            )
    siblings = session.scalars(
        select(DocumentVersion)
        .where(
            DocumentVersion.provenance_group_id == v.provenance_group_id,
            DocumentVersion.id != v.id,
        )
        .limit(10)
    ).all()
    for s in siblings:
        sid = f"doc:{s.id}"
        nodes.setdefault(sid, GraphNode(id=sid, kind="copy", label=f"copy v{s.version}"))
        edges.append(
            GraphEdge(id=f"p:{v.id}:{s.id}", source=doc_id, target=sid, kind="same_provenance")
        )
    return GraphOut(nodes=list(nodes.values()), edges=edges)
