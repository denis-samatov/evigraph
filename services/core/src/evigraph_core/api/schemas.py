"""Request and response contracts. Requests are strict: no silent type coercion."""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# JSON carries UUIDs as strings; strict models would otherwise reject them.
UUIDIn = Annotated[uuid.UUID, Field(strict=False)]


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectIn(Strict):
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(Out):
    id: uuid.UUID
    name: str


class CatalogIn(Strict):
    name: str = Field(min_length=1, max_length=200)


class CatalogOut(Out):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str


class ConceptIn(Strict):
    key: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=500)
    definition: str | None = None


class ConceptOut(Out):
    id: uuid.UUID
    key: str
    label: str
    definition: str | None


class CatalogVersionIn(Strict):
    concepts: list[ConceptIn] = Field(min_length=1)


class CatalogVersionOut(Out):
    id: uuid.UUID
    catalog_id: uuid.UUID
    version: int
    status: str
    concepts: list[ConceptOut]


class SourceIn(Strict):
    system: str = Field(min_length=1, max_length=200)
    id: str = Field(min_length=1, max_length=500)


class DocumentIn(Strict):
    title: str | None = Field(default=None, max_length=1000)
    text: str = Field(min_length=1)
    source: SourceIn | None = None


class DocumentVersionIn(Strict):
    text: str = Field(min_length=1)
    source: SourceIn | None = None


class DocumentVersionOut(Out):
    id: uuid.UUID
    document_id: uuid.UUID
    version: int
    text_sha256: str
    provenance_group_id: uuid.UUID
    provenance_reason: str
    provenance_jaccard: float | None
