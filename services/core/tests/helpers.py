"""Builders shared by tests."""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from evigraph_core import catalogs, documents
from evigraph_core.models import (
    Assertion,
    AssertionState,
    Catalog,
    CatalogVersion,
    DocumentVersion,
    Project,
)
from evigraph_core.settings import Settings


@dataclass
class World:
    project: Project
    catalog_version: CatalogVersion
    concepts: dict[str, uuid.UUID]


def world(session: Session, keys: list[str], name: str | None = None) -> World:
    project = Project(name=name or f"p-{uuid.uuid4().hex[:8]}")
    session.add(project)
    session.flush()
    catalog = Catalog(project_id=project.id, name="tags")
    session.add(catalog)
    session.flush()
    version = catalogs.create_version(
        session, catalog=catalog, concepts=[catalogs.ConceptSpec(k, k.title()) for k in keys]
    )
    catalogs.publish(session, version)
    session.refresh(version)
    return World(project, version, {c.key: c.id for c in version.concepts})


def doc(session: Session, settings: Settings, w: World, text: str, **kw) -> DocumentVersion:
    return documents.create_document(
        session,
        project_id=w.project.id,
        title=None,
        raw_text=text,
        source=kw.get("source"),
        settings=settings,
    )


def proposed(session: Session, version: DocumentVersion, concept_id: uuid.UUID) -> Assertion:
    a = Assertion(
        document_version_id=version.id,
        concept_id=concept_id,
        state=AssertionState.proposed,
        revision=1,
    )
    session.add(a)
    session.flush()
    return a
