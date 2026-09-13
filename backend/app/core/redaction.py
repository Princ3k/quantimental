"""
Scrubbing secrets out of text that is about to leave the process.

This exists because it already went wrong once. MarketAux takes its key as a
query parameter rather than a header, so any exception quoting the request URL
carries a live credential in its message — and those messages were being
published on the public `sentiment_analysis.sources` field.

Every route out of the process needs the same scrub: the API response, the logs,
and anything reported to an error tracker. One implementation, because two would
drift and the one that drifted would be the one that leaked.
"""

from __future__ import annotations

import re

# A credential passed as a query parameter, which is the MarketAux shape.
SECRET_PARAM_RE = re.compile(
    r"\b(api_token|api_key|apikey|access_token|token|key)=([^&\s\"\']+)",
    re.IGNORECASE,
)

# A credential recognisable by its own prefix, wherever it turns up — a bearer
# header quoted in a stack trace, a key pasted into a log line.
SECRET_PREFIX_RE = re.compile(r"\b(gsk_|sk-|ghp_|github_pat_|Bearer\s+)\S+", re.IGNORECASE)

REDACTED = "***"


def redact(text: str) -> str:
    """The same string with anything credential-shaped replaced."""
    if not text:
        return text
    scrubbed = SECRET_PARAM_RE.sub(rf"\1={REDACTED}", text)
    return SECRET_PREFIX_RE.sub(rf"\1{REDACTED}", scrubbed)


def safe_detail(exc: Exception, limit: int = 200) -> str:
    """
    Describe a failure without quoting anything secret.

    Truncated as well: a provider's stack trace is not an explanation, and the
    longer the string the more chance it swept up something it should not have.
    """
    return redact(f"{type(exc).__name__}: {exc}"[:limit])
