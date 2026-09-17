from datetime import datetime, timedelta, timezone

import pytest

from client import Batch, Explanation, MAX_PER_CALL, QuantimentalClient, _normalise, staleness_hours


class TestNormalise:
    def test_upper_cases_and_deduplicates_preserving_order(self):
        assert _normalise([" aapl ", "NVDA", "aapl", "", None or ""]) == ["AAPL", "NVDA"]


class TestStaleness:
    def test_measures_age_in_hours(self):
        then = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        assert 2.9 < staleness_hours(then) < 3.1

    def test_naive_timestamps_are_read_as_utc(self):
        then = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)
        assert 1.9 < staleness_hours(then.isoformat()) < 2.1

    def test_missing_or_unparseable_is_none(self):
        assert staleness_hours(None) is None
        assert staleness_hours("yesterday") is None


class TestExplanationParsing:
    def test_missing_disclosure_is_not_invented(self):
        # Never defaulted to a constant here: if the API stops disclosing, that
        # must be visible rather than papered over with our own stale copy.
        assert Explanation.from_payload({"ticker": "AAPL"}).disclosure == ""

    def test_nested_objects_default_to_empty_not_none(self):
        e = Explanation.from_payload({"ticker": "AAPL"})
        assert e.movement == {} and e.attribution == {} and e.coverage == {}


class TestBatch:
    def test_indexes_by_upper_cased_ticker(self):
        batch = Batch(None, None, [Explanation.from_payload({"ticker": "aapl"})], [])
        assert "AAPL" in batch.by_ticker()


class TestGuards:
    @pytest.mark.asyncio
    async def test_an_empty_request_makes_no_call(self):
        # Guards the scheduled loop: no watched tickers must not become a
        # request for the empty string.
        assert (await QuantimentalClient().explain([])).explanations == []

    @pytest.mark.asyncio
    async def test_over_the_cap_is_refused_before_it_is_sent(self):
        with pytest.raises(ValueError, match=str(MAX_PER_CALL)):
            await QuantimentalClient().explain([f"AA{chr(65 + i % 26)}{i}" for i in range(MAX_PER_CALL + 1)])


class TestClientSurface:
    def test_the_methods_are_on_the_class_not_nested_in_a_helper(self):
        # They were appended to the end of the module once, which put them
        # inside _normalise's body: valid Python, and the client silently had
        # no unusual() at all.
        for name in ("explain", "unusual", "desk"):
            assert callable(getattr(QuantimentalClient, name, None)), name
