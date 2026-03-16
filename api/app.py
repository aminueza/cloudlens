"""CloudLens FastAPI application with lifespan management."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded

from api.auth import AuthMiddleware
from api.errors import CloudLensError, cloudlens_error_handler, generic_error_handler
from api.models import AuthStatusResponse
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
from config.settings import PRODUCTS, settings
from db.session import close_db, init_db
from providers.fetcher import BackgroundFetcher
from providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")


def setup_logging() -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown."""
    setup_logging()
    logger.info("Starting CloudLens Network Intelligence Platform")

    # Initialize database
    init_db(settings.DB_PATH)

    # Initialize provider registry with enabled providers
    registry = ProviderRegistry(enabled_providers=settings.ENABLED_PROVIDERS)

    # Create and start background fetcher
    fetcher = BackgroundFetcher(
        registry=registry,
        poll_interval=settings.POLL_INTERVAL,
    )
    fetcher.start()

    # Store on app state
    app.state.fetcher = fetcher
    app.state.registry = registry

    logger.info("CloudLens started with providers: %s", settings.ENABLED_PROVIDERS)
    yield

    # Shutdown
    logger.info("Shutting down CloudLens")
    fetcher.stop()
    close_db()
    logger.info("CloudLens shutdown complete")


app = FastAPI(
    title="CloudLens — Network Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Rate limiter ---
app.state.limiter = limiter

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Log request method, path, and duration."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.debug(
        "%s %s -> %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# --- Error handlers ---
app.add_exception_handler(CloudLensError, cloudlens_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_error_handler)  # type: ignore[arg-type]


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"error": "Rate limit exceeded"}, status_code=429)


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)  # type: ignore[arg-type]

# --- Prometheus instrumentation ---
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)
except ImportError:
    logger.debug("prometheus-fastapi-instrumentator not installed, skipping metrics")

# --- Static files ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Route registration ---
app.include_router(accounts.router)
app.include_router(topology.router)
app.include_router(export.router)
app.include_router(changes.router)
app.include_router(health_checks.router)
app.include_router(compliance.router)
app.include_router(incidents.router)
app.include_router(ai_routes.router)


# --- Root endpoints ---


@app.get("/health")
async def health_check(request: Request) -> dict:
    """Health check with per-provider status."""
    registry = request.app.state.registry
    providers_status = {}
    for name, provider in registry.providers.items():
        err = getattr(provider, "auth_error", None)
        providers_status[name] = {"ok": err is None, "error": err}
    return {"status": "ok", "providers": providers_status}


@app.get("/api/auth/status", response_model=AuthStatusResponse)
async def auth_status(request: Request) -> dict:
    """Per-provider authentication state."""
    registry = request.app.state.registry
    providers_state = {}
    for name, provider in registry.providers.items():
        err = getattr(provider, "auth_error", None)
        providers_state[name] = {
            "authenticated": err is None,
            "error": err,
        }
    return {"providers": providers_state}


@app.get("/")
async def index(request: Request):
    """Render the main dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "products": PRODUCTS,
        },
    )
