"""Projects, catalogs and documents."""

import uuid
from typing import TypeVar

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import Session

from evigraph_core import catalogs, documents
from evigraph_core.api.deps import SessionDep, SettingsDep
from evigraph_core.api.schemas import (
    CatalogIn,
    CatalogOut,
    CatalogVersionIn,
    CatalogVersionOut,
    DocumentIn,
    DocumentVersionIn,
    DocumentVersionOut,
    ProjectIn,
    ProjectOut,
)
from evigraph_core.models import Catalog, CatalogVersion, Document, DocumentVersion, Project

router = APIRouter()
T = TypeVar("T")


def get_or_404(session: Session, model: type[T], key: uuid.UUID) -> T:
    obj = session.get(model, key)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {key} not found")
    return obj


@router.post("/projects", status_code=201, response_model=ProjectOut)
def create_project(body: ProjectIn, session: SessionDep) -> Project:
    project = Project(name=body.name)
    session.add(project)
    session.flush()
    return project


@router.post("/projects/{project_id}/catalogs", status_code=201, response_model=CatalogOut)
def create_catalog(project_id: uuid.UUID, body: CatalogIn, session: SessionDep) -> Catalog:
    get_or_404(session, Project, project_id)
    catalog = Catalog(project_id=project_id, name=body.name)
    session.add(catalog)
    session.flush()
    return catalog


@router.post("/catalogs/{catalog_id}/versions", status_code=201, response_model=CatalogVersionOut)
def create_catalog_version(
    catalog_id: uuid.UUID, body: CatalogVersionIn, session: SessionDep
) -> CatalogVersion:
    catalog = get_or_404(session, Catalog, catalog_id)
    specs = [catalogs.ConceptSpec(c.key, c.label, c.definition) for c in body.concepts]
    version = catalogs.create_version(session, catalog=catalog, concepts=specs)
    session.refresh(version)
    return version


@router.post("/catalog-versions/{version_id}/publish", response_model=CatalogVersionOut)
def publish_catalog_version(version_id: uuid.UUID, session: SessionDep) -> CatalogVersion:
    return catalogs.publish(session, get_or_404(session, CatalogVersion, version_id))


@router.get("/catalog-versions/{version_id}", response_model=CatalogVersionOut)
def get_catalog_version(version_id: uuid.UUID, session: SessionDep) -> CatalogVersion:
    return get_or_404(session, CatalogVersion, version_id)


def _source(body: DocumentIn | DocumentVersionIn) -> documents.SourceRef | None:
    return documents.SourceRef(body.source.system, body.source.id) if body.source else None


@router.post("/projects/{project_id}/documents", status_code=201, response_model=DocumentVersionOut)
def create_document(
    project_id: uuid.UUID, body: DocumentIn, session: SessionDep, settings: SettingsDep
) -> DocumentVersion:
    get_or_404(session, Project, project_id)
    return documents.create_document(
        session,
        project_id=project_id,
        title=body.title,
        raw_text=body.text,
        source=_source(body),
        settings=settings,
    )


@router.post(
    "/documents/{document_id}/versions", status_code=201, response_model=DocumentVersionOut
)
def add_document_version(
    document_id: uuid.UUID, body: DocumentVersionIn, session: SessionDep, settings: SettingsDep
) -> DocumentVersion:
    document = get_or_404(session, Document, document_id)
    return documents.add_version(
        session,
        project_id=document.project_id,
        document=document,
        raw_text=body.text,
        source=_source(body),
        settings=settings,
    )


@router.get("/document-versions/{version_id}", response_model=DocumentVersionOut)
def get_document_version(version_id: uuid.UUID, session: SessionDep) -> DocumentVersion:
    return get_or_404(session, DocumentVersion, version_id)
