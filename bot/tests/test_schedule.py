from datetime import datetime, timezone

import schedule


def utc(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def iso(y, m, d, hh, mm=0):
    return utc(y, m, d, hh, mm).isoformat()


# The session used throughout: 2026-09-17, which closes at 20:00 UTC (16:00 ET).
CLOSED = iso(2026, 9, 17, 20, 13)   # the 20:13 scan — first one after the close
INTRADAY = iso(2026, 9, 17, 19, 13)  # the last scan before it


class TestSessionHasClosed:
    def test_before_the_close_is_not_closed(self):
        assert schedule.session_has_closed("2026-09-17", now=utc(2026, 9, 17, 18)) is False

    def test_after_the_close_is_closed(self):
        assert schedule.session_has_closed("2026-09-17", now=utc(2026, 9, 17, 20, 30)) is True

    def test_a_malformed_date_is_not_closed(self):
        assert schedule.session_has_closed("not-a-date", now=utc(2026, 9, 17, 22)) is False


class TestScanRanAfterClose:
    def test_the_2013_scan_counts(self):
        assert schedule.scan_ran_after_close("2026-09-17", CLOSED) is True

    def test_the_1913_scan_does_not(self):
        # The crux: at 20:00 UTC the session is over but this is still the
        # newest published scan, and its prices are intraday.
        assert schedule.scan_ran_after_close("2026-09-17", INTRADAY) is False

    def test_a_naive_timestamp_is_read_as_utc(self):
        naive = utc(2026, 9, 17, 20, 13).replace(tzinfo=None).isoformat()
        assert schedule.scan_ran_after_close("2026-09-17", naive) is True

    def test_missing_or_unparseable_does_not_count(self):
        assert schedule.scan_ran_after_close("2026-09-17", None) is False
        assert schedule.scan_ran_after_close("2026-09-17", "this evening") is False


class TestShouldPost:
    def test_posts_once_a_post_close_scan_exists(self):
        assert schedule.should_post("2026-09-17", CLOSED, None, now=utc(2026, 9, 17, 20, 30)) is True

    def test_does_not_post_the_moment_the_bell_rings(self):
        # The session has closed, but only the 19:13 scan is published. Posting
        # here would put pre-close prices under the session's date.
        assert schedule.should_post("2026-09-17", INTRADAY, None, now=utc(2026, 9, 17, 20, 1)) is False

    def test_does_not_post_twice_for_one_session(self):
        assert schedule.should_post(
            "2026-09-17", CLOSED, "2026-09-17", now=utc(2026, 9, 17, 22)
        ) is False

    def test_does_not_post_while_the_market_is_open(self):
        assert schedule.should_post(
            "2026-09-17", iso(2026, 9, 17, 17, 13), None, now=utc(2026, 9, 17, 17, 30)
        ) is False

    def test_a_missed_slot_self_heals(self):
        assert schedule.should_post("2026-09-17", CLOSED, None, now=utc(2026, 9, 18, 2)) is True

    def test_but_not_a_day_later(self):
        assert schedule.should_post("2026-09-17", CLOSED, None, now=utc(2026, 9, 19, 2)) is False

    def test_a_new_session_posts_even_though_the_last_one_did(self):
        assert schedule.should_post(
            "2026-09-18", iso(2026, 9, 18, 20, 13), "2026-09-17", now=utc(2026, 9, 18, 22)
        ) is True

    def test_no_session_means_no_post(self):
        assert schedule.should_post(None, CLOSED, None, now=utc(2026, 9, 17, 22)) is False


class TestScanExpected:
    """Scans run weekdays 14:13-21:43 UTC; nothing is due outside that."""

    def test_mid_window_on_a_weekday(self):
        assert schedule.scan_expected(utc(2026, 9, 17, 18)) is True

    def test_before_the_window_opens(self):
        assert schedule.scan_expected(utc(2026, 9, 17, 12)) is False

    def test_the_late_railway_run_is_still_inside_the_window(self):
        # ~23:4x every weekday, from a Railway trigger that is in no cron here.
        assert schedule.scan_expected(utc(2026, 9, 17, 23, 30)) is True

    def test_after_midnight_is_outside(self):
        assert schedule.scan_expected(utc(2026, 9, 18, 0, 30)) is False

    def test_overnight(self):
        assert schedule.scan_expected(utc(2026, 9, 18, 8)) is False

    def test_saturday_and_sunday_even_mid_window(self):
        assert schedule.scan_expected(utc(2026, 9, 19, 18)) is False
        assert schedule.scan_expected(utc(2026, 9, 20, 18)) is False

    def test_the_window_opens_after_the_first_scan_has_landed(self):
        # The first scan is at 14:1x. Opening on the hour would mean warning
        # against the previous night's run for twenty minutes every morning.
        assert schedule.scan_expected(utc(2026, 9, 17, 14, 0)) is False
        assert schedule.scan_expected(utc(2026, 9, 17, 14, 44)) is False
        assert schedule.scan_expected(utc(2026, 9, 17, 14, 45)) is True

    def test_the_closing_boundary(self):
        assert schedule.scan_expected(utc(2026, 9, 17, 23, 58)) is True
        assert schedule.scan_expected(utc(2026, 9, 17, 23, 59)) is False
