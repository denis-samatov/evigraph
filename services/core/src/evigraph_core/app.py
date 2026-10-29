"""FastAPI application factory."""

import ipaddress
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from evigraph_core import catalogs, certification, evidence, releases, reviews
from evigraph_core.api.routes_base import router as base_router
from evigraph_core.api.routes_certification import router as certification_router
from evigraph_core.api.routes_engine import router as engine_router
from evigraph_core.api.routes_evidence import router as evidence_router
from evigraph_core.api.routes_review import router as review_router
from evigraph_core.api.routes_studio import router as studio_router
from evigraph_core.db import get_engine, session_factory
from evigraph_core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="EviGraph Core", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory(get_engine(settings.database_url))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    @app.middleware("http")
    async def local_browser_boundary(request: Request, call_next):
        # This is a local demonstrator, not remote authentication. Network binding
        # must remain loopback; Host/Origin checks additionally stop browser rebinding/CSRF.
        host_header = request.headers.get("host", "")
        try:
            parsed = urlsplit("http://" + host_header)
            host = parsed.hostname or ""
            _ = parsed.port  # reject malformed/out-of-range ports
            local = host == "localhost" or ipaddress.ip_address(host).is_loopback
            if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                local = False
        except ValueError:
            local = False
        if not local:
            return JSONResponse(status_code=400, content={"detail": "local Host required"})
        origin = request.headers.get("origin")
        same_origin = f"{request.url.scheme}://{host_header}"
        if origin is not None and origin not in {*settings.cors_origins, same_origin}:
            return JSONResponse(status_code=403, content={"detail": "untrusted browser origin"})
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            with app.state.session_factory() as session:
                session.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return {"status": "ready"}

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

    @app.exception_handler(certification.CertificationError)
    def _certification(_: Request, exc: certification.CertificationError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(evidence.EvidenceError)
    def _evidence(_: Request, exc: evidence.EvidenceError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "conflict with existing data"})

    app.include_router(base_router)
    app.include_router(review_router)
    app.include_router(engine_router)
    app.include_router(certification_router)
    app.include_router(evidence_router)
    app.include_router(studio_router)
    return app
