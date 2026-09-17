from datetime import datetime, timezone

import schedule


def utc(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


class TestSessionHasClosed:
    def test_before_the_close_is_not_closed(self):
        # 2026-09-17 18:00 UTC is 14:00 ET — still trading.
        assert schedule.session_has_closed("2026-09-17", now=utc(2026, 9, 17, 18)) is False

    def test_after_the_close_is_closed(self):
        # 20:30 UTC is 16:30 ET.
        assert schedule.session_has_closed("2026-09-17", now=utc(2026, 9, 17, 20, 30)) is True

    def test_a_malformed_date_is_not_closed(self):
        assert schedule.session_has_closed("not-a-date", now=utc(2026, 9, 17, 22)) is False


class TestShouldPost:
    def test_posts_once_the_session_has_closed(self):
        assert schedule.should_post("2026-09-17", None, now=utc(2026, 9, 17, 22)) is True

    def test_does_not_post_twice_for_one_session(self):
        assert schedule.should_post(
            "2026-09-17", "2026-09-17", now=utc(2026, 9, 17, 22)
        ) is False

    def test_does_not_post_while_the_market_is_open(self):
        # The whole reason this is by session and not by clock: an intraday
        # scan publishes as_of for a session that has not finished.
        assert schedule.should_post("2026-09-17", None, now=utc(2026, 9, 17, 17)) is False

    def test_a_missed_slot_self_heals(self):
        # Bot was down at the close; it comes back four hours later and still
        # owes the digest.
        assert schedule.should_post("2026-09-17", None, now=utc(2026, 9, 18, 2)) is True

    def test_but_not_a_day_later(self):
        # Past the abandon window, posting it as today's news is worse than
        # posting nothing.
        assert schedule.should_post("2026-09-17", None, now=utc(2026, 9, 19, 2)) is False

    def test_a_new_session_posts_even_though_the_last_one_did(self):
        assert schedule.should_post(
            "2026-09-18", "2026-09-17", now=utc(2026, 9, 18, 22)
        ) is True

    def test_no_session_means_no_post(self):
        assert schedule.should_post(None, None, now=utc(2026, 9, 17, 22)) is False
