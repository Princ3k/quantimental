"""
Quantimental Backend — FastAPI application entry point.

Market signals that make sense to humans: quantitative indicators fused with
market sentiment, explained in plain English.

The app is designed to start and serve useful results with nothing configured
but Python itself. Postgres, Kafka and the various API keys each unlock extra
features, and their absence degrades the product rather than breaking it.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import market, news, signals
from app.core.config import get_settings
from app.core.rate_limit import client_key, is_exempt, rate_limiter, request_cost
from app.core.source_health import source_health
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


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """
    Charge every API call against the caller's budget.

    Cost is proportional to work, not to request count: a 60-ticker batch costs
    sixty, a full-depth analyse costs twenty-five. See app/core/rate_limit.py
    for why a token bucket rather than a fixed window.
    """
    path = request.url.path

    if request.method == "OPTIONS" or is_exempt(path):
        return await call_next(request)

    # Pricing a batch needs its ticker count, which is in the body. Reading the
    # body here consumes the stream, so it is put back for the route handler —
    # without this, every POST downstream sees an empty body.
    ticker_count = 1
    if request.method == "POST" and path.endswith("/batch"):
        body = await request.body()

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # noqa: SLF001 - the documented way to rewind

        try:
            payload = json.loads(body or b"{}")
            tickers = payload.get("tickers")
            if isinstance(tickers, list):
                ticker_count = len(tickers)
        except (ValueError, AttributeError):
            # Malformed JSON is the route's problem to report, not ours. Charge
            # the default and let it produce a proper 422.
            ticker_count = 1

    key = client_key(
        request.headers.get("x-forwarded-for"),
        request.headers.get("x-real-ip"),
        request.client.host if request.client else None,
    )
    allowed, retry_after = rate_limiter.check(key, request_cost(path, ticker_count))

    if not allowed:
        seconds = max(1, int(retry_after) + 1)
        logger.warning("Rate limited %s on %s (retry in %ss)", key, path, seconds)
        return JSONResponse(
            status_code=429,
            content={
                "error": "Too Many Requests",
                # Said in the app's own voice: this is shown to a person if it
                # ever reaches one, and "quota exceeded" explains nothing.
                "detail": (
                    "You are loading stocks faster than we can fetch them. "
                    f"Try again in about {seconds} seconds."
                ),
            },
            headers={"Retry-After": str(seconds)},
        )

    return await call_next(request)


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
            # Two facts per source, kept apart: whether credentials are set,
            # and what the source actually did the last time anything asked
            # it. Reporting only the first was wrong in both directions —
            # twitter:true while every request 401'd, and reddit:false while
            # Reddit was working fine over its keyless RSS path. `working` is
            # null until something has actually tried. Never echo a key.
            "sentiment": {
                "groq_model": settings.GROQ_MODEL if settings.GROQ_API_KEY else None,
                "groq": source_health.describe("groq", bool(settings.GROQ_API_KEY)),
                "yahoo_finance": source_health.describe("yahoo_finance", True),
                "marketaux": source_health.describe(
                    "marketaux", bool(settings.MARKETAUX_API_KEY)
                ),
                "reddit": source_health.describe(
                    "reddit",
                    bool(settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET),
                ),
                "twitter": source_health.describe("twitter", bool(settings.TWITTER_API_KEY)),
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
