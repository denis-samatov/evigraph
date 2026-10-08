"""Catalogs of concepts. A catalog version is edited as a draft and frozen when published;
assertions, releases and certifications always refer to a published version."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evigraph_core.models import Catalog, CatalogStatus, CatalogVersion, Concept


class CatalogStateError(ValueError):
    pass


@dataclass(frozen=True)
class ConceptSpec:
    key: str
    label: str
    definition: str | None = None


def create_version(
    session: Session, *, catalog: Catalog, concepts: list[ConceptSpec]
) -> CatalogVersion:
    keys = [c.key for c in concepts]
    if len(set(keys)) != len(keys):
        msg = "concept keys must be unique within a catalog version"
        raise CatalogStateError(msg)
    last = session.scalar(
        select(func.max(CatalogVersion.version)).where(CatalogVersion.catalog_id == catalog.id)
    )
    version = CatalogVersion(
        catalog_id=catalog.id, version=(last or 0) + 1, status=CatalogStatus.draft
    )
    session.add(version)
    session.flush()
    for c in concepts:
        session.add(
            Concept(
                catalog_version_id=version.id, key=c.key, label=c.label, definition=c.definition
            )
        )
    session.flush()
    return version


def publish(session: Session, version: CatalogVersion) -> CatalogVersion:
    if version.status is CatalogStatus.published:
        return version
    if not session.scalar(
        select(func.count()).select_from(Concept).where(Concept.catalog_version_id == version.id)
    ):
        msg = "cannot publish an empty catalog version"
        raise CatalogStateError(msg)
    version.status = CatalogStatus.published
    session.flush()
    return version


def require_published(session: Session, catalog_version_id: uuid.UUID) -> CatalogVersion:
    version = session.get(CatalogVersion, catalog_version_id)
    if version is None or version.status is not CatalogStatus.published:
        msg = "catalog version must exist and be published"
        raise CatalogStateError(msg)
    return version
