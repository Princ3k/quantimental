"""
An HTTP client for EDGAR, shaped by the SEC's access policy.

Two requirements come from them rather than from us. Every request must carry a
User-Agent naming a real contact, or the request is refused; and the ceiling is
ten requests a second across everything you do. Both are in their published
policy, and ignoring either gets the source blocked — which matters more here
than elsewhere, because filings are the one input in this project that is
public domain and free of the licensing question hanging over the price feed.

Pacing is enforced here rather than left to callers, because the limit is per
client rather than per call site and a caller counting its own requests cannot
see the others.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Their documented ceiling is 10/s. Sitting at 8 leaves room for the retry that
# a burst would otherwise turn into a violation.
REQUESTS_PER_SECOND = 8.0
_MIN_SPACING = 1.0 / REQUESTS_PER_SECOND

TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0

# Not a fallback so much as a last resort: an anonymous-looking agent is what
# gets blocked, so this at least names the project.
DEFAULT_CONTACT = "Quantimental (https://github.com/Princ3k/quantimental)"


class EdgarBlocked(RuntimeError):
    """EDGAR refused us, and retrying the same way will not help."""


class _Pace:
    """One shared gate, so the whole process stays under the ceiling."""

    def __init__(self, spacing: float) -> None:
        self._spacing = spacing
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self._spacing


_pace = _Pace(_MIN_SPACING)


def user_agent() -> str:
    """
    What we tell the SEC we are.

    They ask for a contact address so they can reach whoever is generating the
    traffic. `SEC_CONTACT_EMAIL` supplies it; without one the requests still go
    out, named but unreachable, which is worse than it sounds — an unreachable
    agent is the kind they throttle first.
    """
    contact = (get_settings().SEC_CONTACT_EMAIL or "").strip()
    if not contact:
        logger.warning(
            "SEC_CONTACT_EMAIL is not set. EDGAR asks for a contact address and "
            "throttles traffic it cannot trace; set one before relying on this."
        )
        return DEFAULT_CONTACT
    return f"Quantimental {contact}"


def get_json(url: str, client: Optional[httpx.Client] = None) -> Any:
    """
    One GET, paced and retried, decoded as JSON.

    A 403 is the shape a blocked agent takes, so it is raised rather than
    retried: three more identical requests would only confirm the block.
    """
    owned = client is None
    session = client or httpx.Client(
        headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"},
        timeout=TIMEOUT_SECONDS,
    )
    try:
        last: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            _pace.wait()
            try:
                response = session.get(url)
                if response.status_code == 403:
                    raise EdgarBlocked(
                        f"EDGAR refused {url}. Usually the User-Agent: it must "
                        "name a real contact address."
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.json()
            except EdgarBlocked:
                raise
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))

        raise RuntimeError(f"EDGAR request failed after {MAX_RETRIES} attempts: {last}")
    finally:
        if owned:
            session.close()


def get_text(url: str, client: Optional[httpx.Client] = None) -> str:
    """The same, for the daily index, which is fixed-width text and not JSON."""
    owned = client is None
    session = client or httpx.Client(
        headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"},
        timeout=TIMEOUT_SECONDS,
    )
    try:
        _pace.wait()
        response = session.get(url)
        if response.status_code == 403:
            raise EdgarBlocked(f"EDGAR refused {url}.")
        response.raise_for_status()
        return response.text
    finally:
        if owned:
            session.close()


def new_client() -> httpx.Client:
    """A client callers can hold open across a sweep, so connections are reused."""
    return httpx.Client(
        headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"},
        timeout=TIMEOUT_SECONDS,
    )
