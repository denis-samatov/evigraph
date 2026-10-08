"""FastAPI application factory."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from evigraph_core import catalogs, releases, reviews
from evigraph_core.api.routes_base import router as base_router
from evigraph_core.api.routes_engine import router as engine_router
from evigraph_core.api.routes_review import router as review_router
from evigraph_core.db import get_engine, session_factory
from evigraph_core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="EviGraph Core", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory(get_engine(settings.database_url))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(catalogs.CatalogStateError)
    def _catalog_state(_: Request, exc: catalogs.CatalogStateError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(reviews.ReviewConflictError)
    def _review_conflict(_: Request, exc: reviews.ReviewConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(reviews.ReviewNotFoundError)
    def _review_missing(_: Request, exc: reviews.ReviewNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(releases.ReleaseError)
    def _release(_: Request, exc: releases.ReleaseError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "conflict with existing data"})

    app.include_router(base_router)
    app.include_router(review_router)
    app.include_router(engine_router)
    return app
