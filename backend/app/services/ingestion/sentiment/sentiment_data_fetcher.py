"""
Sentiment Data Fetcher

Fetches sentiment-related data from news and social sources.

Sources, in order of how much we rely on them:

- Yahoo Finance news (via yfinance) — no credentials, works for every market
  yfinance already covers, including non-US listings like RACE.MI or SHOP.TO.
  This is the source that makes the feature work out of the box.
- Reddit (r/stocks, r/investing, r/wallstreetbets) — no credentials, via the
  public RSS feeds. See ``_fetch_reddit`` for why RSS and not ``.json``.
- MarketAux — optional, needs ``MARKETAUX_API_KEY``. Adds publisher-scored
  sentiment per entity.
- Twitter/X via ScrapeBadger — optional, needs ``TWITTER_API_KEY``.

Design philosophy:
- Async everything (non-blocking I/O)
- Framework-agnostic (no FastAPI dependencies)
- Light normalization only (no analysis)
- A source that fails says so. Returning ``[]`` for "the API rejected our key"
  and for "this company genuinely has no news" made a broken deployment look
  like a quiet news day, which cost us a lot of time.
"""

import asyncio
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Awaitable

import httpx
import trafilatura

from app.core.config import get_settings
from app.core.source_health import source_health
from app.utils.ttl_cache import TTLCache as _TTLCache

logger = logging.getLogger(__name__)

# Reddit's RSS feeds, which unlike the JSON API still serve unauthenticated
# clients. See ``_fetch_reddit``.
REDDIT_BASE_URL = "https://www.reddit.com"
REDDIT_USER_AGENT = "python:quantimental-sentiment:v1.0.0 (by /u/quantimental)"
REDDIT_TARGET_SUBREDDITS = ["stocks", "investing", "wallstreetbets"]
# Reddit accepts several subreddits in one path, which turns three requests
# into one. Each entry carries a <category label="r/stocks"> saying where it
# came from, so nothing is lost by combining them.
REDDIT_MULTI = "+".join(REDDIT_TARGET_SUBREDDITS)
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

MARKETAUX_BASE_URL = "https://api.marketaux.com/v1/news/all"
# Two providers resell Twitter/X search, and this project has referred to both:
# the code called ScrapeBadger while env.example told you to sign up at
# twitterapi.io. A key from one is rejected by the other, which presents as a
# flat 401 with nothing to suggest the provider is the problem — so both are
# supported and `TWITTER_API_PROVIDER` picks one.
#
# They differ in host, header casing, the query-type parameter name, and the
# key the tweet list arrives under. All four are captured here rather than
# branching through the fetch.
TWITTER_PROVIDERS: dict[str, dict[str, str]] = {
    "scrapebadger": {
        "host": "scrapebadger.com",
        "url": "https://scrapebadger.com/api/v1/twitter/tweets/advanced_search",
        "header": "x-api-key",
        "query_type_param": "query_type",
        "results_key": "data",
    },
    "twitterapi.io": {
        "host": "api.twitterapi.io",
        "url": "https://api.twitterapi.io/twitter/tweet/advanced_search",
        "header": "X-API-Key",
        "query_type_param": "queryType",
        "results_key": "tweets",
    },
}
DEFAULT_TWITTER_PROVIDER = "twitterapi.io"

# Kept for callers that imported it directly.
TWITTER_BASE_URL = TWITTER_PROVIDERS[DEFAULT_TWITTER_PROVIDER]["url"]

# HTTP configuration
DEFAULT_TIMEOUT = 30.0
REDDIT_TIMEOUT = 8.0
MAX_RETRIES = 2

# Reddit throttles unauthenticated clients hard — roughly ten requests a minute
# per IP. One combined request per ticker plus a shared gate keeps us under it,
# and the cache means a dashboard refresh does not re-spend the budget.
REDDIT_REQUEST_SPACING = 3.0
REDDIT_CACHE_TTL = 1800.0

# Measured, not guessed: after a 90-second cooldown a single anonymous request
# succeeds and every request for the next minute is refused. Once Reddit says
# 429 there is nothing to gain by asking again soon, so we stop asking at all
# for a while. Configured credentials bypass this entirely — see _reddit_token.
REDDIT_COOLDOWN_AFTER_429 = 300.0
REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_OAUTH_URL = "https://oauth.reddit.com"

# Yahoo is generous by comparison, but there is no reason to re-fetch the same
# headlines for every visitor within the same few minutes.
YAHOO_CACHE_TTL = 300.0

# Content Fetching configuration
MAX_ARTICLE_LENGTH = 5000  # Truncate articles longer than this

# Yahoo news is scoped to a ticker by Yahoo, but the tail of the list drifts
# into general market stories. If at least this many articles actually name the
# company we keep only those; below it we keep the lot, on the grounds that a
# loose story about the sector still beats no sentiment at all.
MIN_DIRECT_MATCHES = 3

_TAG_RE = re.compile(r"<[^>]+>")


class _RequestGate:
    """
    Spaces out calls to one host across all concurrent requests.

    An asyncio.Lock held across the sleep is what makes this work: two tickers
    analysed at once would otherwise each see "enough time has passed" and fire
    simultaneously, which is exactly the burst Reddit rejects.
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._min_interval - (time.monotonic() - self._last)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


_reddit_cache = _TTLCache(REDDIT_CACHE_TTL)
_reddit_gate = _RequestGate(REDDIT_REQUEST_SPACING)
_yahoo_cache = _TTLCache(YAHOO_CACHE_TTL)

# When the anonymous feed rate-limits us, every ticker backs off, not just the
# one that happened to hit it. The limit is per IP, so it is shared state.
_reddit_blocked_until = 0.0

# OAuth tokens last an hour; ask for a new one a minute early.
_reddit_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}
_reddit_token_lock = asyncio.Lock()


@dataclass
class SourceOutcome:
    """
    What one source returned, and why it returned that.

    ``status`` is one of:
      ok        — items were returned
      empty     — the source answered, and had nothing for this ticker
      disabled  — no credentials configured, so we never asked
      error     — the source was asked and failed; ``detail`` says how
    """

    items: list[dict] = field(default_factory=list)
    status: str = "empty"
    detail: Optional[str] = None

    @property
    def count(self) -> int:
        return len(self.items)


# Query parameters whose values are credentials. MarketAux takes its key as
# `api_token` in the URL, and httpx puts the full URL in some exception
# messages — which would otherwise travel into `source_status.detail` and out
# through the public API response.
_SECRET_PARAM_RE = re.compile(
    r"\b(api_token|api_key|apikey|access_token|token|key)=([^&\s\"\']+)",
    re.IGNORECASE,
)
_SECRET_PREFIX_RE = re.compile(r"\b(gsk_|sk-|Bearer\s+)\S+", re.IGNORECASE)


def _safe_detail(exc: Exception) -> str:
    """
    Describe a failure without quoting anything secret.

    Source details are published on every analyse response, so an exception
    message that happens to contain the request URL would put a live API key
    into a public payload. Truncated as well: a provider stack trace is not
    something to broadcast either.
    """
    detail = f"{type(exc).__name__}: {exc}"[:200]
    detail = _SECRET_PARAM_RE.sub(r"\1=***", detail)
    return _SECRET_PREFIX_RE.sub(r"\1***", detail)


def _strip_html(raw: str) -> str:
    """
    Reduce a fragment of feed HTML to readable text.

    Unescape, then strip, then unescape again. Reddit escapes the post body and
    Atom escapes it a second time, so how much decoding has already happened by
    the time we get here depends on the parser. Stripping tags first would miss
    markup that is still sitting in its escaped form, and leave it in the text.
    """
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", html.unescape(raw))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _iso_to_epoch(value: str) -> float:
    """Best-effort ISO-8601 to POSIX seconds; 0.0 when unparseable."""
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------

async def _reddit_token() -> Optional[str]:
    """
    An app-only OAuth token, or None when no credentials are configured.

    Reddit's free "script" app allows about 100 requests a minute, against
    roughly one a minute for anonymous clients, so this is the difference
    between the source working and the source being decorative. Tokens last an
    hour and are shared across requests.
    """
    settings = get_settings()
    client_id = settings.REDDIT_CLIENT_ID
    client_secret = settings.REDDIT_CLIENT_SECRET
    if not (client_id and client_secret):
        return None

    async with _reddit_token_lock:
        if _reddit_token_cache["token"] and time.monotonic() < _reddit_token_cache["expires_at"]:
            return _reddit_token_cache["token"]

        try:
            async with httpx.AsyncClient(timeout=REDDIT_TIMEOUT) as client:
                response = await client.post(
                    REDDIT_TOKEN_URL,
                    auth=(client_id, client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={"User-Agent": REDDIT_USER_AGENT},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            # Fall back to the anonymous feed rather than failing the source.
            logger.warning("Reddit OAuth token request failed: %s", exc)
            return None

        token = payload.get("access_token")
        if not token:
            return None

        _reddit_token_cache["token"] = token
        _reddit_token_cache["expires_at"] = time.monotonic() + float(payload.get("expires_in", 3600)) - 60
        logger.info("Reddit OAuth token acquired")
        return token


def _posts_from_listing(data: dict) -> list[dict]:
    """Normalise Reddit's JSON listing shape (the authenticated response)."""
    posts = []
    for wrapper in data.get("data", {}).get("children", []):
        post = wrapper.get("data", {})
        posts.append({
            "source": "reddit",
            "subreddit": post.get("subreddit", ""),
            "post_id": post.get("id", ""),
            "created_utc": post.get("created_utc", 0),
            "author": post.get("author", "[deleted]"),
            "title": post.get("title", ""),
            "text": post.get("selftext", ""),
            "url": f"https://reddit.com{post.get('permalink', '')}",
            # Unlike RSS, the authenticated API does return scores.
            "score": post.get("score", 0),
        })
    return posts


async def _reddit_authenticated(ticker: str, limit: int, token: str) -> SourceOutcome:
    """Search via the OAuth API, which returns scores and a usable rate limit."""
    url = f"{REDDIT_OAUTH_URL}/r/{REDDIT_MULTI}/search"
    params = {
        "q": ticker,
        "restrict_sr": "1",
        "sort": "new",
        "t": "week",
        "limit": limit,
    }
    headers = {"Authorization": f"bearer {token}", "User-Agent": REDDIT_USER_AGENT}

    try:
        async with httpx.AsyncClient(timeout=REDDIT_TIMEOUT) as client:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 401:
                # Token expired early or was revoked; drop it so the next call
                # fetches a fresh one rather than failing forever.
                _reddit_token_cache["expires_at"] = 0.0
                return SourceOutcome([], "error", "HTTP 401 — Reddit token rejected")
            response.raise_for_status()
            posts = _posts_from_listing(response.json())
    except httpx.HTTPStatusError as exc:
        return SourceOutcome([], "error", f"HTTP {exc.response.status_code}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reddit OAuth search failed for %s: %s", ticker, exc)
        return SourceOutcome([], "error", _safe_detail(exc))

    if not posts:
        return SourceOutcome([], "empty", "no posts in the last week")

    logger.info("Reddit (authenticated): %d posts for %s", len(posts), ticker)
    return SourceOutcome(posts, "ok")


async def _fetch_reddit(ticker: str, limit: int = 25) -> SourceOutcome:
    """
    Fetch recent Reddit posts about a ticker from the public RSS feeds.

    Two things about this are deliberate.

    **RSS, not JSON.** Reddit's ``/search.json`` endpoint now answers
    unauthenticated clients with HTTP 403 no matter what User-Agent is sent,
    and ``old.reddit.com`` redirects those requests to an interstitial. The
    ``.rss`` feeds are still open. The cost is that RSS carries no score, so
    every post comes back with ``score: 0``; nothing downstream weights by
    score, and a post we can read unauthenticated beats an upvote count we
    cannot.

    **One request, not three.** ``/r/a+b+c/search.rss`` searches all three
    subreddits at once and labels each entry with its origin. Fetching them
    separately tripled our request count against a limiter that allows roughly
    ten a minute, and reliably earned HTTP 429.
    """
    ticker = ticker.upper().strip()

    cached = _reddit_cache.get(ticker)
    if cached is not None:
        return cached

    token = await _reddit_token()
    if token:
        outcome = await _reddit_authenticated(ticker, limit, token)
    else:
        outcome = await _reddit_anonymous(ticker, limit)

    # Cache failures too: hammering a source that just rate-limited us is how a
    # slow hour becomes a blocked one.
    _reddit_cache.set(ticker, outcome)
    return outcome


async def _reddit_anonymous(ticker: str, limit: int) -> SourceOutcome:
    """
    The keyless RSS path, used when no Reddit credentials are configured.

    Best-effort by nature: Reddit allows anonymous clients roughly one request
    a minute, so under any real traffic most calls here will be refused. It is
    kept because it costs nothing and does work for low-volume use; configuring
    REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET is what makes the source dependable.
    """
    global _reddit_blocked_until

    if time.monotonic() < _reddit_blocked_until:
        remaining = int(_reddit_blocked_until - time.monotonic())
        return SourceOutcome(
            [], "error",
            f"rate limited by Reddit; backing off for another {remaining}s "
            "(set REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET to avoid this)",
        )

    await _reddit_gate.wait()

    url = f"{REDDIT_BASE_URL}/r/{REDDIT_MULTI}/search.rss"
    params = {
        "q": ticker,
        "restrict_sr": "1",
        "sort": "new",
        "t": "week",
        "limit": limit,
    }
    headers = {"User-Agent": REDDIT_USER_AGENT}

    try:
        async with httpx.AsyncClient(timeout=REDDIT_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            root = ET.fromstring(response.content)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = f"HTTP {status}"
        if status == 429:
            detail += (
                " — rate limited by Reddit; anonymous access allows roughly one "
                "request a minute. Set REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET."
            )
            _reddit_blocked_until = time.monotonic() + REDDIT_COOLDOWN_AFTER_429
        elif status == 403:
            detail += " — Reddit refused an unauthenticated request"
        logger.warning("Reddit failed for %s: %s", ticker, detail)
        return SourceOutcome([], "error", detail)
    except httpx.TimeoutException:
        return SourceOutcome([], "error", "request timed out")
    except ET.ParseError as exc:
        return SourceOutcome([], "error", f"unparseable feed ({exc})")
    except Exception as exc:  # noqa: BLE001 - a bad source must not break the request
        logger.warning("Reddit failed for %s: %s", ticker, exc)
        return SourceOutcome([], "error", _safe_detail(exc))

    posts: list[dict] = []
    for entry in root.findall("a:entry", ATOM_NS):
        title = (entry.findtext("a:title", default="", namespaces=ATOM_NS) or "").strip()
        content = entry.findtext("a:content", default="", namespaces=ATOM_NS) or ""
        author = entry.findtext("a:author/a:name", default="", namespaces=ATOM_NS) or ""
        updated = entry.findtext("a:updated", default="", namespaces=ATOM_NS) or ""
        link_el = entry.find("a:link", ATOM_NS)
        entry_id = entry.findtext("a:id", default="", namespaces=ATOM_NS) or ""

        category = entry.find("a:category", ATOM_NS)
        subreddit = (category.get("label", "") if category is not None else "").removeprefix("r/")

        posts.append({
            "source": "reddit",
            "subreddit": subreddit,
            "post_id": entry_id.rsplit("_", 1)[-1] if entry_id else "",
            "created_utc": _iso_to_epoch(updated),
            "author": author.removeprefix("/u/") or "[deleted]",
            "title": title,
            "text": _strip_html(content),
            "url": link_el.get("href", "") if link_el is not None else "",
            # RSS carries no score. See the docstring.
            "score": 0,
        })

    if not posts:
        return SourceOutcome([], "empty", "no posts in the last week")

    logger.info("Reddit: %d posts for %s", len(posts), ticker)
    return SourceOutcome(posts, "ok")


async def fetch_reddit_posts_for_ticker(ticker: str, limit: int = 25) -> list[dict]:
    """Backwards-compatible wrapper returning only the posts."""
    return (await _fetch_reddit(ticker, limit)).items


# ---------------------------------------------------------------------------
# Yahoo Finance news
# ---------------------------------------------------------------------------

def _yahoo_news_blocking(ticker: str) -> list[dict]:
    """yfinance is synchronous; callers run this in a thread."""
    import yfinance as yf

    return yf.Ticker(ticker).news or []


def _normalise_yahoo_article(raw: dict) -> Optional[dict]:
    """Flatten one yfinance news entry, or None if it carries no usable text."""
    content = raw.get("content") or raw
    title = (content.get("title") or "").strip()
    if not title:
        return None

    summary = (content.get("summary") or content.get("description") or "").strip()
    url = ""
    for key in ("canonicalUrl", "clickThroughUrl"):
        candidate = content.get(key) or {}
        if isinstance(candidate, dict) and candidate.get("url"):
            url = candidate["url"]
            break

    provider = content.get("provider") or {}
    published = content.get("pubDate") or content.get("displayTime") or ""

    return {
        "source": "yahoo_finance",
        "news_source": provider.get("displayName", "") if isinstance(provider, dict) else "",
        "title": title,
        "description": summary,
        "full_text": "",
        "url": url,
        "published_at": published,
        # Yahoo does not score sentiment. The ML models read the text instead;
        # a fabricated 0 here would be averaged into the simple-analysis path
        # as "neutral", so downstream must treat None as "unscored".
        "sentiment_score": None,
        "relevance_score": 0,
        "keywords": [],
        "is_cached": False,
        "entities": [],
    }


def _filter_relevant(articles: list[dict], ticker: str, company_name: Optional[str]) -> list[dict]:
    """
    Prefer articles that actually name the company.

    Yahoo scopes its feed to the ticker, but the tail drifts into general market
    stories, so a feed for AAPL can carry a piece about SiriusXM. Dropping every
    unmatched article would be too aggressive for thinly covered listings, so we
    only tighten when there is enough direct coverage to tighten with.
    """
    # RACE.MI and SHOP.TO should still match on "RACE" and "SHOP".
    base = ticker.split(".")[0].upper()
    needles = {base.lower()}
    if company_name:
        # "Apple Inc." -> "apple"; the legal suffix rarely appears in headlines.
        head = re.split(r"[ ,]", company_name.strip())[0].lower()
        if len(head) > 2:
            needles.add(head)

    direct = [
        a for a in articles
        if any(n in f"{a['title']} {a['description']}".lower() for n in needles)
    ]
    return direct if len(direct) >= MIN_DIRECT_MATCHES else articles


async def _fetch_yahoo_news(
    ticker: str,
    company_name: Optional[str] = None,
    limit: int = 15,
) -> SourceOutcome:
    """Fetch ticker news from Yahoo Finance. No credentials required."""
    ticker = ticker.upper().strip()

    cache_key = f"{ticker}|{company_name or ''}|{limit}"
    cached = _yahoo_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, _yahoo_news_blocking, ticker)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Yahoo news failed for %s: %s", ticker, exc)
        return SourceOutcome([], "error", _safe_detail(exc))

    articles = [a for a in (_normalise_yahoo_article(r) for r in raw) if a]
    if not articles:
        return SourceOutcome([], "empty", "Yahoo listed no stories for this ticker")

    articles = _filter_relevant(articles, ticker, company_name)[:limit]
    logger.info("Yahoo news: %d articles for %s", len(articles), ticker)

    outcome = SourceOutcome(articles, "ok")
    _yahoo_cache.set(cache_key, outcome)
    return outcome


# ---------------------------------------------------------------------------
# Article full text
# ---------------------------------------------------------------------------

async def fetch_article_content(url: str, timeout: float = 3.0) -> str:
    """
    Fetch and extract the main text of an article.

    Uses trafilatura to strip ads, navigation and boilerplate, and truncates to
    MAX_ARTICLE_LENGTH so the result stays cheap to feed to a model.
    """
    if not url:
        return ""

    try:
        loop = asyncio.get_event_loop()

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, follow_redirects=True)
            downloaded = response.text

        if not downloaded:
            return ""

        text = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=True,
                ),
            ),
            timeout=3.0,
        )

        if not text:
            return ""

        if len(text) > MAX_ARTICLE_LENGTH:
            text = text[:MAX_ARTICLE_LENGTH] + "... [TRUNCATED]"

        return text

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching content from %s (>%ss)", url, timeout)
        return ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to extract content from %s: %s", url, exc)
        return ""


# ---------------------------------------------------------------------------
# MarketAux
# ---------------------------------------------------------------------------

async def _fetch_marketaux(
    ticker: str,
    limit: int = 10,
    url_filter_func: Optional[Callable[[str], Awaitable[bool]]] = None,
    skip_full_text: bool = False,
) -> SourceOutcome:
    """
    Fetch financial news from MarketAux, which scores sentiment per entity.

    The key is read from Settings rather than ``os.getenv`` at import time, so
    that this agrees with the /health readout. They disagreed before: health
    reported the key as present while this module had captured an empty string.
    """
    ticker = ticker.upper().strip()
    api_key = get_settings().MARKETAUX_API_KEY

    if not api_key:
        return SourceOutcome([], "disabled", "MARKETAUX_API_KEY is not set")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            params = {
                "api_token": api_key,
                "symbols": ticker,
                "limit": limit,
                "filter_entities": "true",
                "language": "en",
                "sort": "published_desc",
            }

            response = await client.get(MARKETAUX_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # MarketAux can answer 200 with an error envelope rather than data.
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                detail = f"{err.get('code', 'error')}: {err.get('message', '')}".strip()
                logger.warning("MarketAux rejected the request for %s: %s", ticker, detail)
                return SourceOutcome([], "error", detail)

            articles = data.get("data", [])

            async def process_article(article: dict) -> dict:
                url = article.get("url", "")
                full_text = ""
                is_cached = False

                if url_filter_func and url and not skip_full_text:
                    try:
                        if await url_filter_func(url):
                            is_cached = True
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Error in url_filter_func: %s", exc)

                if url and not is_cached and not skip_full_text:
                    full_text = await fetch_article_content(url)

                ticker_sentiment = 0
                ticker_relevance = 0
                for entity in article.get("entities", []):
                    if entity.get("symbol", "").upper() == ticker:
                        ticker_sentiment = entity.get("sentiment_score", 0)
                        ticker_relevance = entity.get("match_score", 0)
                        break

                return {
                    "source": "marketaux",
                    "news_source": article.get("source", ""),
                    "title": article.get("title", ""),
                    "description": article.get("description", "") or article.get("snippet", ""),
                    "full_text": full_text,
                    "url": url,
                    "published_at": article.get("published_at", ""),
                    "sentiment_score": ticker_sentiment,
                    "relevance_score": ticker_relevance,
                    "keywords": article.get("keywords", "").split(",") if article.get("keywords") else [],
                    "is_cached": is_cached,
                    "entities": [
                        {
                            "symbol": e.get("symbol"),
                            "name": e.get("name"),
                            "sentiment": e.get("sentiment_score", 0),
                        }
                        for e in article.get("entities", [])[:5]
                    ],
                }

            news_articles = list(await asyncio.gather(*[process_article(a) for a in articles]))
            if not news_articles:
                return SourceOutcome([], "empty", "MarketAux had no articles for this symbol")

            logger.info("MarketAux: %d articles for %s", len(news_articles), ticker)
            return SourceOutcome(news_articles, "ok")

        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            # These are the ones worth telling a human apart.
            known = {
                401: "invalid or missing API token",
                402: "plan limit reached — MarketAux wants an upgrade",
                429: "rate limit exceeded (free tier is 100 requests/day)",
            }
            detail = f"HTTP {code}"
            if code in known:
                detail += f" — {known[code]}"
            logger.warning("MarketAux failed for %s: %s", ticker, detail)
            return SourceOutcome([], "error", detail)
        except httpx.TimeoutException:
            return SourceOutcome([], "error", "request timed out")
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected MarketAux error for %s: %s", ticker, exc)
            return SourceOutcome([], "error", _safe_detail(exc))


async def fetch_marketaux_news(
    ticker: str,
    limit: int = 10,
    url_filter_func: Optional[Callable[[str], Awaitable[bool]]] = None,
    skip_full_text: bool = False,
) -> list[dict]:
    """Backwards-compatible wrapper returning only the articles."""
    outcome = await _fetch_marketaux(ticker, limit, url_filter_func, skip_full_text)
    return outcome.items


# ---------------------------------------------------------------------------
# Twitter / X
# ---------------------------------------------------------------------------

def _twitter_provider() -> dict[str, str]:
    """The configured provider, falling back to the documented default."""
    name = (get_settings().TWITTER_API_PROVIDER or DEFAULT_TWITTER_PROVIDER).strip().lower()
    provider = TWITTER_PROVIDERS.get(name)
    if provider is None:
        logger.warning(
            "Unknown TWITTER_API_PROVIDER %r; using %s. Valid: %s",
            name, DEFAULT_TWITTER_PROVIDER, ", ".join(TWITTER_PROVIDERS),
        )
        return TWITTER_PROVIDERS[DEFAULT_TWITTER_PROVIDER]
    return provider


def _normalise_tweet(tweet: dict) -> dict:
    """
    Flatten one tweet from either provider.

    The two disagree on field names, so both spellings are tried. Reading a
    missing field as 0 is fine here — engagement counts are used for weighting,
    not reported as facts.
    """
    username = tweet.get("username") or (tweet.get("author") or {}).get("userName", "")
    tweet_id = str(tweet.get("id") or tweet.get("id_str") or "")

    return {
        "source": "twitter",
        "tweet_id": tweet_id,
        "text": tweet.get("full_text") or tweet.get("text", ""),
        "created_at": tweet.get("created_at") or tweet.get("createdAt", ""),
        "author": username,
        "followers": 0,  # Not provided in search results by either provider.
        "likes": tweet.get("favorite_count") or tweet.get("likeCount", 0),
        "retweets": tweet.get("retweet_count") or tweet.get("retweetCount", 0),
        "replies": tweet.get("reply_count") or tweet.get("replyCount", 0),
        "views": tweet.get("view_count") or tweet.get("viewCount", 0),
        "url": f"https://twitter.com/{username or 'i'}/status/{tweet_id}",
    }


async def _fetch_twitter(ticker: str, limit: int = 20) -> SourceOutcome:
    """Fetch recent tweets about a ticker from the configured provider."""
    ticker = ticker.upper().strip()
    cashtag = f"${ticker}"
    api_key = get_settings().TWITTER_API_KEY

    if not api_key:
        return SourceOutcome([], "disabled", "TWITTER_API_KEY is not set")

    provider = _twitter_provider()
    url = provider["url"]
    params = {"query": f"{cashtag} lang:en", provider["query_type_param"]: "Latest"}
    headers = {provider["header"]: api_key}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(url, params=params, headers=headers)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 15))
                logger.warning("Twitter 429 for %s — waiting %ss then retrying", ticker, retry_after)
                await asyncio.sleep(retry_after)
                response = await client.get(url, params=params, headers=headers)

            response.raise_for_status()
            data = response.json()

            tweets = data.get(provider["results_key"]) or []
            normalized: list[dict] = []

            for tweet in tweets:
                if tweet.get("is_retweet") or tweet.get("isRetweet"):
                    continue
                normalized.append(_normalise_tweet(tweet))
                if len(normalized) >= limit:
                    break

            if not normalized:
                return SourceOutcome([], "empty", "no matching tweets")

            logger.info("Twitter: %d tweets for %s via %s", len(normalized), ticker, provider["host"])
            return SourceOutcome(normalized, "ok")

        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            detail = f"HTTP {code}"
            if code in (401, 403):
                # Naming the host is the whole point: a key bought from the
                # other provider produces this exact error, and without the
                # host there is nothing to suggest that is what happened.
                others = [n for n in TWITTER_PROVIDERS if n != _provider_name()]
                detail += (
                    f" — {provider['host']} rejected this key. If you signed up with "
                    f"{' or '.join(others)}, set TWITTER_API_PROVIDER to it."
                )
            elif code == 429:
                detail += f" — rate limited by {provider['host']}"
            logger.warning("Twitter failed for %s: %s", ticker, detail)
            return SourceOutcome([], "error", detail)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching tweets for %s: %s", ticker, exc)
            return SourceOutcome([], "error", _safe_detail(exc))


def _provider_name() -> str:
    name = (get_settings().TWITTER_API_PROVIDER or DEFAULT_TWITTER_PROVIDER).strip().lower()
    return name if name in TWITTER_PROVIDERS else DEFAULT_TWITTER_PROVIDER


async def fetch_twitter_posts(ticker: str, limit: int = 20, min_followers: int = 50) -> list[dict]:
    """Backwards-compatible wrapper returning only the tweets."""
    return (await _fetch_twitter(ticker, limit)).items


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

async def fetch_all_sentiment_sources(
    ticker: str,
    url_filter_func: Optional[Callable[[str], Awaitable[bool]]] = None,
    skip_full_text: bool = False,
    company_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    Fetch sentiment data from every available source, in parallel.

    Returns a dict with:
        ticker          — the symbol queried
        reddit_posts    — list of Reddit post dicts
        news_articles   — Yahoo Finance plus MarketAux, newest first
        marketaux_news  — alias of ``news_articles`` (kept for older callers)
        twitter_posts   — list of tweet dicts
        source_status   — per-source {status, count, detail}, so a caller can
                          tell "no coverage" apart from "credentials rejected"
    """
    ticker = ticker.upper().strip()

    results = await asyncio.gather(
        _fetch_reddit(ticker),
        _fetch_yahoo_news(ticker, company_name=company_name),
        _fetch_marketaux(ticker, url_filter_func=url_filter_func, skip_full_text=skip_full_text),
        _fetch_twitter(ticker),
        return_exceptions=True,
    )

    names = ("reddit", "yahoo_finance", "marketaux", "twitter")
    outcomes: dict[str, SourceOutcome] = {}
    for name, result in zip(names, results):
        if isinstance(result, BaseException):
            logger.error("%s fetch raised for %s: %s", name, ticker, result)
            outcomes[name] = SourceOutcome(
                [], "error", _safe_detail(result if isinstance(result, Exception) else Exception(str(result)))
            )
        else:
            outcomes[name] = result

    # Yahoo and MarketAux both produce articles in the same shape, so the
    # analysers treat them as one pool. Newest first, and deduplicated by URL
    # because the two providers do syndicate the same stories.
    news: list[dict] = []
    seen_urls: set[str] = set()
    for article in outcomes["yahoo_finance"].items + outcomes["marketaux"].items:
        key = (article.get("url") or article.get("title", "")).strip().lower()
        if key and key in seen_urls:
            continue
        if key:
            seen_urls.add(key)
        news.append(article)
    news.sort(key=lambda a: a.get("published_at") or "", reverse=True)

    source_status = {
        name: {
            "status": outcome.status,
            "count": outcome.count,
            "detail": outcome.detail,
        }
        for name, outcome in outcomes.items()
    }

    # Remember what actually happened, so /health can report observed reality
    # rather than inferring it from which keys are set.
    source_health.record_all(source_status)

    result = {
        "ticker": ticker,
        "reddit_posts": outcomes["reddit"].items,
        "news_articles": news,
        "marketaux_news": news,
        "twitter_posts": outcomes["twitter"].items,
        "source_status": source_status,
    }

    logger.info(
        "Sentiment fetch for %s: %d reddit, %d news (%d yahoo + %d marketaux), %d tweets",
        ticker,
        len(result["reddit_posts"]),
        len(news),
        outcomes["yahoo_finance"].count,
        outcomes["marketaux"].count,
        len(result["twitter_posts"]),
    )

    return result


async def main() -> None:
    """Manual smoke test: python -m app.services.ingestion.sentiment.sentiment_data_fetcher"""
    import json
    import sys

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    data = await fetch_all_sentiment_sources(ticker, skip_full_text=True)

    print(f"\n=== {ticker} ===")
    for name, status in data["source_status"].items():
        mark = {"ok": "✅", "empty": "—", "disabled": "○", "error": "❌"}.get(status["status"], "?")
        line = f"{mark} {name:<14} {status['status']:<9} {status['count']:>3}"
        if status["detail"]:
            line += f"  ({status['detail']})"
        print(line)

    print("\nSample news:")
    for article in data["news_articles"][:5]:
        print(f"  [{article['source']}] {article['published_at'][:10]} {article['title'][:70]}")

    print("\nSample Reddit:")
    for post in data["reddit_posts"][:5]:
        print(f"  r/{post['subreddit']}: {post['title'][:70]}")


if __name__ == "__main__":
    asyncio.run(main())
