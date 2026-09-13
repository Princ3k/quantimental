"""
Error reporting.

The API now has an endpoint whose whole purpose is to be called by somebody
else's code. A 500 there is different from a 500 on a page — nobody is looking
at it, and the first sign of trouble would be a licensee mentioning it. This
closes that gap and nothing more: errors, not tracing, not profiling.

Scrubbing is the part that needed care. Sentry's default capture includes the
request, and this project has already published a live credential once because
MarketAux passes its key as a query parameter. Every event is put through the
same redaction the public API response uses, and `send_default_pii` stays off,
so what leaves the process is an error rather than an error and a key.

No DSN means no initialisation at all. Local runs and the test suite must never
report anywhere, and the way to guarantee that is for the SDK not to start.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import get_settings
from app.core.redaction import redact

logger = logging.getLogger(__name__)

# Errors are the point. Tracing on every request would spend the free tier on
# performance data nobody is reading yet; turn it up when there is a reason.
DEFAULT_TRACES_SAMPLE_RATE = 0.0

# Noise that says nothing about our code. A client disconnecting mid-response
# is the internet, not a bug, and rate-limit rejections are the limiter working.
IGNORED_ERRORS = (
    "ClientDisconnect",
    "ConnectionResetError",
)


def _scrub(value: Any) -> Any:
    """Walk an event and redact every string in it."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item) for item in value)
    return value


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Last gate before an event leaves the process.

    Scrubs the whole event rather than the fields that seem likely to carry a
    secret. A credential turns up wherever the string that held it went — a
    breadcrumb, a local variable in a frame, the exception message — and
    guessing which of those matters is how the first leak happened.
    """
    for values in (event.get("exception", {}).get("values") or []):
        if values.get("type") in IGNORED_ERRORS:
            return None

    try:
        return _scrub(event)
    except Exception:  # noqa: BLE001
        # A scrubber that throws must drop the event, never pass it through
        # unscrubbed. Losing one report is cheaper than publishing a key.
        logger.warning("Could not scrub an error report; dropping it.")
        return None


def init_sentry() -> bool:
    """
    Start error reporting, if it is configured. Returns whether it did.

    Never raises. Observability failing to start is not a reason for the API
    not to.
    """
    settings = get_settings()
    dsn = (settings.SENTRY_DSN or "").strip()
    if not dsn:
        logger.info("SENTRY_DSN is not set; error reporting is off.")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed.")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=settings.SENTRY_ENVIRONMENT,
            release=settings.VERSION,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            # Off deliberately. We do not want IP addresses or headers, and the
            # rate limiter already keys on a client address we do not store.
            send_default_pii=False,
            max_request_body_size="never",
            before_send=before_send,
            integrations=[
                StarletteIntegration(failed_request_status_codes={500, 502, 503, 504}),
                FastApiIntegration(failed_request_status_codes={500, 502, 503, 504}),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not start error reporting: %s", exc)
        return False

    logger.info("Error reporting on (%s)", settings.SENTRY_ENVIRONMENT)
    return True
