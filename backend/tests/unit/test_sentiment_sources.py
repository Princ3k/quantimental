"""
Tests for the sentiment source fetchers.

The thing being pinned down here is not really the parsing — it is that a
source which *fails* reports failure. Every one of these sources used to
swallow its errors into an empty list, which made "MarketAux rejected our key"
and "this company had a quiet week" produce identical output.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.ingestion.sentiment import sentiment_data_fetcher as fetcher
from app.services.ingestion.sentiment.sentiment_data_fetcher import (
    SourceOutcome,
    _filter_relevant,
    _normalise_yahoo_article,
    _strip_html,
)
from app.services.signals.live_signal_service import _broken_sources, _source_status


@pytest.fixture(autouse=True)
def _clear_source_caches():
    """
    The fetchers cache per ticker, including failures.

    Without this, a test that fetches AAPL successfully hands its result to the
    next test that asks for AAPL — which is the caching working correctly, and
    the tests lying to us.
    """
    fetcher._reddit_cache.clear()
    fetcher._yahoo_cache.clear()
    # The rate-limit breaker and the OAuth token are module-level, so a real
    # network call from an earlier test file (tests/api runs first) can leave
    # this module backing off before these tests even start.
    fetcher._reddit_blocked_until = 0.0
    fetcher._reddit_token_cache["token"] = None
    fetcher._reddit_token_cache["expires_at"] = 0.0
    # The gate spaces real requests ~1.1s apart; mocked transports need no
    # protection, and three tests paying that toll each is a slow suite.
    fetcher._reddit_gate._last = 0.0
    fetcher._reddit_gate._min_interval = 0.0
    yield
    fetcher._reddit_gate._min_interval = fetcher.REDDIT_REQUEST_SPACING


REDDIT_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <category term="stocks" label="r/stocks"/>
    <author><name>/u/someone</name></author>
    <content type="html">&lt;div&gt;Thinking about &amp;quot;AAPL&amp;quot; calls&lt;/div&gt;</content>
    <id>t3_abc123</id>
    <link href="https://www.reddit.com/r/stocks/comments/abc123/x/"/>
    <updated>2026-09-11T09:30:07+00:00</updated>
    <title>Is it too late to buy AAPL?</title>
  </entry>
</feed>
"""


class TestStripHtml:
    def test_unescapes_doubly_escaped_feed_content(self):
        # Reddit escapes once, Atom escapes again, so a single unescape leaves
        # &quot; visible in the post body.
        assert _strip_html("&lt;p&gt;&amp;quot;hi&amp;quot;&lt;/p&gt;") == '"hi"'

    def test_empty_input(self):
        assert _strip_html("") == ""


class TestRedditRss:
    @pytest.mark.asyncio
    async def test_parses_posts_from_the_rss_feed(self, monkeypatch):
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request.url.path)
            return httpx.Response(200, content=REDDIT_FEED.encode())

        _patch_httpx(monkeypatch, handler)

        outcome = await fetcher._fetch_reddit("AAPL")

        assert outcome.status == "ok"
        # One combined request covering every subreddit, not one request each.
        assert outcome.count == 1
        assert requests == [f"/r/{fetcher.REDDIT_MULTI}/search.rss"]

        post = outcome.items[0]
        assert post["subreddit"] == "stocks"  # taken from the category label
        assert post["title"] == "Is it too late to buy AAPL?"
        assert post["author"] == "someone"  # the /u/ prefix is stripped
        assert post["post_id"] == "abc123"
        assert '"AAPL"' in post["text"]
        assert post["created_utc"] > 0

    @pytest.mark.asyncio
    async def test_403_is_reported_as_an_error_not_as_no_posts(self, monkeypatch):
        # This is the regression that started all of this: Reddit began
        # rejecting unauthenticated JSON requests, and the app reported it as
        # "no recent posts about this stock".
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, content=b"blocked")

        _patch_httpx(monkeypatch, handler)

        outcome = await fetcher._fetch_reddit("AAPL")

        assert outcome.status == "error"
        assert outcome.count == 0
        assert "403" in outcome.detail

    @pytest.mark.asyncio
    async def test_a_repeat_lookup_is_served_from_cache(self, monkeypatch):
        # Reddit allows roughly ten requests a minute. A dashboard refreshing
        # six tickers must not spend six of them every time.
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(200, content=REDDIT_FEED.encode())

        _patch_httpx(monkeypatch, handler)

        first = await fetcher._fetch_reddit("AAPL")
        second = await fetcher._fetch_reddit("AAPL")

        assert len(calls) == 1
        assert second is first

    @pytest.mark.asyncio
    async def test_rate_limit_failures_are_cached_too(self, monkeypatch):
        # Retrying into a limiter that just refused us is how a slow minute
        # becomes a blocked hour.
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(429, content=b"slow down")

        _patch_httpx(monkeypatch, handler)

        first = await fetcher._fetch_reddit("AAPL")
        await fetcher._fetch_reddit("AAPL")

        assert len(calls) == 1
        assert first.status == "error"
        assert "rate limited" in first.detail


class TestRedditOAuth:
    """
    Credentials switch Reddit from best-effort to dependable.

    Anonymous access allows roughly one request a minute; a free Reddit app
    allows about a hundred. The point of these tests is that configuring
    credentials actually changes which code path runs.
    """

    @pytest.mark.asyncio
    async def test_uses_the_oauth_api_when_credentials_are_set(self, monkeypatch):
        _patch_settings(monkeypatch, reddit=("id", "secret"))

        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            if request.url.path.endswith("/access_token"):
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
            return httpx.Response(200, json={
                "data": {"children": [{"data": {
                    "id": "abc",
                    "subreddit": "stocks",
                    "title": "AAPL thoughts",
                    "selftext": "body",
                    "author": "someone",
                    "score": 42,
                    "created_utc": 1_760_000_000,
                    "permalink": "/r/stocks/comments/abc/x/",
                }}]}
            })

        _patch_httpx(monkeypatch, handler)

        outcome = await fetcher._fetch_reddit("AAPL")

        assert outcome.status == "ok"
        assert any("oauth.reddit.com" in url for url in seen)
        # The authenticated API returns scores; RSS does not.
        assert outcome.items[0]["score"] == 42
        assert outcome.items[0]["subreddit"] == "stocks"

    @pytest.mark.asyncio
    async def test_falls_back_to_rss_when_the_token_request_fails(self, monkeypatch):
        _patch_settings(monkeypatch, reddit=("id", "secret"))

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/access_token"):
                return httpx.Response(500, text="nope")
            return httpx.Response(200, content=REDDIT_FEED.encode())

        _patch_httpx(monkeypatch, handler)

        outcome = await fetcher._fetch_reddit("AAPL")

        # A broken token endpoint should degrade to the keyless path, not kill
        # the source outright.
        assert outcome.status == "ok"
        assert outcome.items[0]["title"] == "Is it too late to buy AAPL?"

    @pytest.mark.asyncio
    async def test_a_rejected_token_is_discarded_so_the_next_call_refreshes(self, monkeypatch):
        _patch_settings(monkeypatch, reddit=("id", "secret"))

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/access_token"):
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
            return httpx.Response(401, json={"message": "Unauthorized"})

        _patch_httpx(monkeypatch, handler)

        outcome = await fetcher._fetch_reddit("AAPL")

        assert outcome.status == "error"
        assert "401" in outcome.detail
        # Holding a token the server rejects would fail every later call too.
        assert fetcher._reddit_token_cache["expires_at"] == 0.0


class TestRedditBackoff:
    @pytest.mark.asyncio
    async def test_a_429_stops_us_asking_again_for_other_tickers(self, monkeypatch):
        # The limit is per IP, so one ticker hitting it means every ticker is
        # blocked. Asking anyway extends the block.
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(429, content=b"slow down")

        _patch_httpx(monkeypatch, handler)

        await fetcher._fetch_reddit("AAPL")
        second = await fetcher._fetch_reddit("TSLA")

        assert len(calls) == 1  # TSLA never left the building
        assert second.status == "error"
        assert "backing off" in second.detail
        assert "REDDIT_CLIENT_ID" in second.detail


class TestTwitterProviders:
    """
    Two resellers, non-interchangeable keys, and a bare 401 either way.

    The code called scrapebadger.com while env.example told you to sign up at
    twitterapi.io, so a key obtained by following the documentation was
    guaranteed to be rejected — and the error said only "HTTP 401".
    """

    @pytest.mark.asyncio
    async def test_each_provider_is_called_at_its_own_host(self, monkeypatch):
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.host)
            return httpx.Response(200, json={"data": [], "tweets": []})

        _patch_httpx(monkeypatch, handler)

        for provider, host in [
            ("twitterapi.io", "api.twitterapi.io"),
            ("scrapebadger", "scrapebadger.com"),
        ]:
            seen.clear()
            _patch_settings(monkeypatch, twitter="k", twitter_provider=provider)
            await fetcher._fetch_twitter("AAPL")
            assert seen == [host]

    @pytest.mark.asyncio
    async def test_each_provider_gets_its_own_header_and_param_spelling(self, monkeypatch):
        captured: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["r"] = request
            return httpx.Response(200, json={"data": [], "tweets": []})

        _patch_httpx(monkeypatch, handler)

        _patch_settings(monkeypatch, twitter="k", twitter_provider="twitterapi.io")
        await fetcher._fetch_twitter("AAPL")
        assert captured["r"].headers.get("x-api-key") == "k"
        assert "queryType" in str(captured["r"].url)

        _patch_settings(monkeypatch, twitter="k", twitter_provider="scrapebadger")
        await fetcher._fetch_twitter("AAPL")
        assert "query_type" in str(captured["r"].url)

    @pytest.mark.asyncio
    async def test_a_401_names_the_host_and_the_alternative(self, monkeypatch):
        # The fix for the original bug: the error has to make the provider
        # mismatch visible, since that is the likeliest cause.
        _patch_settings(monkeypatch, twitter="k", twitter_provider="scrapebadger")
        _patch_httpx(monkeypatch, lambda r: httpx.Response(401, json={"detail": "nope"}))

        outcome = await fetcher._fetch_twitter("AAPL")

        assert outcome.status == "error"
        assert "scrapebadger.com rejected this key" in outcome.detail
        assert "twitterapi.io" in outcome.detail
        assert "TWITTER_API_PROVIDER" in outcome.detail

    @pytest.mark.asyncio
    async def test_an_unknown_provider_falls_back_rather_than_crashing(self, monkeypatch):
        _patch_settings(monkeypatch, twitter="k", twitter_provider="not-a-provider")
        _patch_httpx(monkeypatch, lambda r: httpx.Response(200, json={"tweets": []}))

        outcome = await fetcher._fetch_twitter("AAPL")
        assert outcome.status == "empty"

    @pytest.mark.asyncio
    async def test_tweets_normalise_from_either_field_spelling(self, monkeypatch):
        _patch_settings(monkeypatch, twitter="k", twitter_provider="twitterapi.io")
        _patch_httpx(monkeypatch, lambda r: httpx.Response(200, json={
            "tweets": [{
                "id": "123",
                "text": "AAPL looks interesting",
                "createdAt": "2026-09-12",
                "author": {"userName": "someone"},
                "likeCount": 5,
            }]
        }))

        outcome = await fetcher._fetch_twitter("AAPL")

        assert outcome.status == "ok"
        tweet = outcome.items[0]
        assert tweet["author"] == "someone"
        assert tweet["likes"] == 5
        assert tweet["url"] == "https://twitter.com/someone/status/123"

    @pytest.mark.asyncio
    async def test_retweets_are_skipped_under_either_spelling(self, monkeypatch):
        _patch_settings(monkeypatch, twitter="k", twitter_provider="twitterapi.io")
        _patch_httpx(monkeypatch, lambda r: httpx.Response(200, json={
            "tweets": [
                {"id": "1", "text": "rt", "isRetweet": True},
                {"id": "2", "text": "rt", "is_retweet": True},
            ]
        }))

        assert (await fetcher._fetch_twitter("AAPL")).status == "empty"


class TestMarketaux:
    @pytest.mark.asyncio
    async def test_missing_key_is_disabled_not_error(self, monkeypatch):
        _patch_settings(monkeypatch, marketaux=None)
        outcome = await fetcher._fetch_marketaux("AAPL")
        assert outcome.status == "disabled"
        assert "MARKETAUX_API_KEY" in outcome.detail

    @pytest.mark.asyncio
    async def test_401_explains_that_the_token_was_rejected(self, monkeypatch):
        _patch_settings(monkeypatch, marketaux="key")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={"error": {"code": "invalid_api_token", "message": "bad token"}},
            )

        _patch_httpx(monkeypatch, handler)

        outcome = await fetcher._fetch_marketaux("AAPL")

        assert outcome.status == "error"
        assert "401" in outcome.detail
        assert "token" in outcome.detail.lower()

    @pytest.mark.asyncio
    async def test_error_envelope_returned_with_http_200(self, monkeypatch):
        # MarketAux does not always use the status code to say no.
        _patch_settings(monkeypatch, marketaux="key")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"error": {"code": "usage_limit_reached", "message": "no quota"}},
            )

        _patch_httpx(monkeypatch, handler)

        outcome = await fetcher._fetch_marketaux("AAPL")

        assert outcome.status == "error"
        assert "usage_limit_reached" in outcome.detail


class TestYahooNews:
    def test_normalises_a_nested_article(self):
        article = _normalise_yahoo_article({
            "content": {
                "title": "Apple beats expectations",
                "summary": "Revenue up.",
                "pubDate": "2026-09-12T10:00:00Z",
                "provider": {"displayName": "Reuters"},
                "canonicalUrl": {"url": "https://example.com/a"},
            }
        })

        assert article["source"] == "yahoo_finance"
        assert article["news_source"] == "Reuters"
        assert article["url"] == "https://example.com/a"
        # Yahoo does not score sentiment, and inventing a 0 would read as a
        # genuine "neutral" vote downstream.
        assert article["sentiment_score"] is None

    def test_untitled_articles_are_dropped(self):
        assert _normalise_yahoo_article({"content": {"title": "   "}}) is None

    def test_keeps_only_direct_matches_when_there_are_enough(self):
        articles = [
            _make_article("Apple launches a phone"),
            _make_article("Apple and its suppliers"),
            _make_article("Apple stock climbs"),
            _make_article("Sirius XM announces a deal"),
        ]

        kept = _filter_relevant(articles, "AAPL", "Apple Inc.")

        titles = [a["title"] for a in kept]
        assert "Sirius XM announces a deal" not in titles
        assert len(kept) == 3

    def test_keeps_everything_when_direct_coverage_is_thin(self):
        # A thinly covered listing should not end up with zero news just
        # because headlines name the company differently.
        articles = [_make_article("Sector rallies"), _make_article("Rates fall")]
        assert _filter_relevant(articles, "AAPL", "Apple Inc.") == articles

    def test_matches_on_the_root_of_an_international_symbol(self):
        articles = [
            _make_article("RACE posts record deliveries"),
            _make_article("RACE upgraded"),
            _make_article("RACE margin outlook"),
            _make_article("Unrelated market wrap"),
        ]

        kept = _filter_relevant(articles, "RACE.MI", None)

        assert len(kept) == 3
        assert all("RACE" in a["title"] for a in kept)


class TestNewsDeduplication:
    @pytest.mark.asyncio
    async def test_a_syndicated_story_is_not_listed_twice(self, monkeypatch):
        """
        The same piece reaches us from both providers at different URLs — one
        credited "Insider Monkey", the other "insidermonkey.com" — so a
        URL-only key let it through and the card stacked the identical
        headline on itself.
        """
        title = "Nvidia's 2 GW Australia AI Push Could Deepen Its Advantage"

        async def yahoo(*args, **kwargs):
            return SourceOutcome(
                [{"title": title, "url": "https://finance.yahoo.com/a", "source": "yahoo_finance"}],
                "ok",
            )

        async def marketaux(*args, **kwargs):
            return SourceOutcome(
                [{"title": title, "url": "https://insidermonkey.com/b", "source": "marketaux"}],
                "ok",
            )

        async def empty(*args, **kwargs):
            return SourceOutcome([], "empty")

        monkeypatch.setattr(fetcher, "_fetch_yahoo_news", yahoo)
        monkeypatch.setattr(fetcher, "_fetch_marketaux", marketaux)
        monkeypatch.setattr(fetcher, "_fetch_reddit", empty)
        monkeypatch.setattr(fetcher, "_fetch_twitter", empty)

        result = await fetcher.fetch_all_sentiment_sources("NVDA")

        assert len(result["news_articles"]) == 1

    def test_titles_match_across_publisher_punctuation(self):
        # Syndicators reformat quotes and dashes; the story is the same.
        assert fetcher._title_key("Nvidia’s “Big” Push — Explained") == fetcher._title_key(
            "Nvidia's \"Big\" Push - Explained"
        )

    def test_distinct_headlines_are_kept(self):
        assert fetcher._title_key("Apple rises") != fetcher._title_key("Apple falls")


class TestSourceStatusReporting:
    def test_prefers_the_detailed_status_when_present(self):
        data = {"source_status": {"reddit": {"status": "error", "count": 0, "detail": "HTTP 403"}}}
        assert _source_status(data)["reddit"]["detail"] == "HTTP 403"

    def test_falls_back_to_counts_from_the_breakdown(self):
        data = {"breakdown": {"reddit": {"mentions": 4}, "news": {"mentions": 0}}}
        status = _source_status(data)
        assert status["reddit"] == {"status": "ok", "count": 4, "detail": None}
        assert status["news"]["status"] == "empty"

    def test_broken_sources_lists_only_failures(self):
        status = {
            "reddit": {"status": "error", "count": 0, "detail": "HTTP 403"},
            "twitter": {"status": "disabled", "count": 0, "detail": "no key"},
            "yahoo_finance": {"status": "ok", "count": 8, "detail": None},
            "marketaux": {"status": "error", "count": 0, "detail": "HTTP 401"},
        }
        # A source we never configured is not "broken" — nothing is wrong with
        # choosing not to run Twitter.
        assert _broken_sources(status) == ["marketaux", "reddit"]


class TestUnscoredArticles:
    def test_yahoo_articles_count_as_mentions_but_not_as_neutral_votes(self):
        from app.services.data.real_time_sentiment_service import RealTimeSentimentService

        service = RealTimeSentimentService.__new__(RealTimeSentimentService)

        articles = [
            {"sentiment_score": None},   # Yahoo: unscored
            {"sentiment_score": None},
            {"sentiment_score": 0.8},    # MarketAux: genuinely bullish
        ]

        result = service._simple_news_analysis(articles)

        assert result["mentions"] == 3
        # Averaging the two None values in as 0.0 would have pulled this to 63.
        assert result["score"] == 90

    def test_all_unscored_is_neutral_without_pretending_to_know(self):
        from app.services.data.real_time_sentiment_service import RealTimeSentimentService

        service = RealTimeSentimentService.__new__(RealTimeSentimentService)
        result = service._simple_news_analysis([{"sentiment_score": None}] * 4)

        assert result["mentions"] == 4
        assert result["score"] == 50


def _make_article(title: str) -> dict:
    return {"title": title, "description": "", "source": "yahoo_finance"}


def _patch_httpx(monkeypatch, handler) -> None:
    """Route every AsyncClient request in the fetcher through `handler`."""
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(fetcher.httpx, "AsyncClient", factory)


def _patch_settings(
    monkeypatch, *, marketaux=None, twitter=None, reddit=(None, None), twitter_provider=None
) -> None:
    class _Stub:
        MARKETAUX_API_KEY = marketaux
        TWITTER_API_KEY = twitter
        TWITTER_API_PROVIDER = twitter_provider
        REDDIT_CLIENT_ID = reddit[0]
        REDDIT_CLIENT_SECRET = reddit[1]

    monkeypatch.setattr(fetcher, "get_settings", lambda: _Stub())
