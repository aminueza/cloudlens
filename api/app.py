"""CloudLens FastAPI application."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.auth import AuthMiddleware
from api.errors import CloudLensError, cloudlens_error_handler, generic_error_handler
from api.ratelimit import limiter
from api.routes import (
    accounts,
    ai_routes,
    changes,
    compliance,
    export,
    health_checks,
    incidents,
    topology,
)
from config.logging import setup_logging
from config.settings import settings
from db.session import close_db, init_db
from providers.fetcher import BackgroundFetcher
from providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.info("Starting CloudLens")

    await init_db(settings.DB_PATH)
    logger.info("Database initialized")

    enabled = [p.strip() for p in settings.ENABLED_PROVIDERS.split(",") if p.strip()]
    registry = ProviderRegistry(enabled)

    fetcher = BackgroundFetcher(
        registry=registry,
        poll_interval=settings.CLOUDLENS_POLL_INTERVAL,
    )
    fetcher.start()

    app.state.fetcher = fetcher
    app.state.registry = registry

    logger.info("CloudLens started with providers: %s", enabled)
    yield

    fetcher.stop()
    await close_db()
    logger.info("CloudLens shutdown complete")


app = FastAPI(
    title="CloudLens — Network Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip() for o in settings.CLOUDLENS_CORS_ORIGINS.split(",") if o.strip()
    ],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)
app.add_middleware(AuthMiddleware)

# Error handlers
app.add_exception_handler(CloudLensError, cloudlens_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_error_handler)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Routes
app.include_router(accounts.router)
app.include_router(topology.router)
app.include_router(export.router)
app.include_router(changes.router)
app.include_router(health_checks.router)
app.include_router(compliance.router)
app.include_router(incidents.router)
app.include_router(ai_routes.router)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 1)
    logger.info(
        "%s %s -> %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/health")
async def health():
    registry = getattr(app.state, "registry", None)
    providers: dict[str, dict] = {}
    if registry:
        for name, provider in registry.get_all_providers().items():
            err = provider.get_auth_error()
            providers[name] = {"ok": err is None, "error": err}
    has_errors = any(not p["ok"] for p in providers.values())
    return {
        "status": "degraded" if has_errors else "ok",
        "providers": providers,
    }


@app.get("/api/auth/status")
async def auth_status():
    registry = getattr(app.state, "registry", None)
    providers: dict[str, dict] = {}
    if registry:
        for name, provider in registry.get_all_providers().items():
            err = provider.get_auth_error()
            providers[name] = {"ok": err is None, "error": err}
    return {"providers": providers}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    fetcher = getattr(request.app.state, "fetcher", None)
    products = fetcher.get_discovered_products() if fetcher else []
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "products": products},
    )
