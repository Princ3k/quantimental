"""
Quantimental Backend — FastAPI application entry point.

Market signals that make sense to humans: quantitative indicators fused with
market sentiment, explained in plain English.

The app is designed to start and serve useful results with nothing configured
but Python itself. Postgres, Kafka and the various API keys each unlock extra
features, and their absence degrades the product rather than breaking it.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import market, news, signals
from app.core.config import get_settings
from app.db.session import check_connection, database_available, dispose_engines

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Report what is and isn't configured at startup, then clean up at exit."""
    logger.info("Starting %s v%s", settings.PROJECT_NAME, settings.VERSION)

    if database_available():
        connected = await check_connection()
        logger.info("Database: %s", "connected" if connected else "configured but unreachable")
    else:
        logger.info("Database: not configured — news archive and batch pipeline disabled")

    optional_keys = {
        "Reddit": settings.REDDIT_CLIENT_ID,
        "MarketAux news": settings.MARKETAUX_API_KEY,
        "Twitter": settings.TWITTER_API_KEY,
        "Groq LLM": settings.GROQ_API_KEY,
    }
    missing = [name for name, value in optional_keys.items() if not value]
    if missing:
        logger.info("Sentiment sources without credentials: %s", ", ".join(missing))

    logger.info("CORS origins: %s", ", ".join(settings.cors_origins))

    yield

    await dispose_engines()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Market signals that make sense to humans. "
        "Technical analysis and market sentiment, combined and explained in plain English."
    ),
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Vercel preview deployments get a new subdomain per build, so they are
    # matched by pattern rather than being listed one by one.
    allow_origin_regex=r"^https://[a-z0-9-]+\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Record how long each request took, for the frontend's latency display."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Process-Time"] = f"{elapsed_ms:.1f}ms"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for unexpected errors.

    Logs the full traceback server-side but returns a generic message, so
    internal details never leak to the browser.
    """
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": "Something went wrong on our end."},
    )


app.include_router(signals.router, prefix="/api/v1/signals", tags=["Signals"])
app.include_router(news.router, prefix="/api/v1/news", tags=["News"])
app.include_router(market.router, prefix="/api/v1/market", tags=["Market"])


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    """
    Health check for monitoring and deploy gates.

    Reports overall status plus which optional subsystems are live. Returns
    healthy whenever signals can be served, since that is the core product.
    """
    return {
        "status": "healthy",
        "service": "quantimental-api",
        "version": settings.VERSION,
        "subsystems": {
            "market_data": True,
            "database": await check_connection(),
            # Reported per provider rather than as one flag. A single combined
            # boolean says "some credential is present", which is useless when
            # the question is which one is missing — and that is exactly the
            # question a deploy raises. Booleans only: never echo a key.
            "sentiment": {
                "groq": bool(settings.GROQ_API_KEY),
                "groq_model": settings.GROQ_MODEL if settings.GROQ_API_KEY else None,
                "marketaux": bool(settings.MARKETAUX_API_KEY),
                "alpha_vantage": bool(settings.ALPHA_VANTAGE_API_KEY),
                "reddit": bool(settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET),
                "twitter": bool(settings.TWITTER_API_KEY),
            },
        },
    }


@app.get("/", tags=["System"])
async def root() -> dict:
    """API root — points at the docs."""
    return {
        "message": "Quantimental API",
        "tagline": "Market signals that make sense to humans",
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health",
    }
