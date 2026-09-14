"""
Tests for the workflow trigger.

This exists because GitHub's own scheduler never fired for this repository, so
it is now the thing that keeps the site current. Its failure mode is silence —
nobody watches a cron that works — so the tests are about it being loud when it
cannot do its job, and quiet when there is nothing to do.
"""

from __future__ import annotations

import httpx
import pytest

from scripts import trigger_workflow as tw


class _Response:
    def __init__(self, status_code=204, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


class _Client:
    def __init__(self, runs=None, post_status=204):
        self._runs = runs if runs is not None else []
        self._post_status = post_status
        self.posted = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url):
        return _Response(payload={"workflow_runs": self._runs})

    def post(self, url, json):
        self.posted.append((url, json))
        return _Response(status_code=self._post_status, text="nope")


@pytest.fixture
def client(monkeypatch):
    def install(**kwargs):
        c = _Client(**kwargs)
        monkeypatch.setattr(tw.httpx, "Client", lambda **_: c)
        return c
    return install


class TestDispatch:
    def test_a_successful_dispatch_returns_zero(self, client):
        c = client()
        assert tw.dispatch("o/r", "scan.yml", "main", "tok") == 0
        assert c.posted[0][1] == {"ref": "main"}

    def test_it_does_not_stack_a_second_run_on_a_running_one(self, client):
        # The workflow's concurrency group stops them overlapping, but a queued
        # duplicate still spends a full Yahoo sweep republishing the same
        # numbers.
        c = client(runs=[{"status": "in_progress", "created_at": "2026-09-14T18:00:00Z"}])
        assert tw.dispatch("o/r", "scan.yml", "main", "tok") == 0
        assert c.posted == []

    def test_a_finished_run_does_not_block_the_next_one(self, client):
        c = client(runs=[{"status": "completed", "created_at": "2026-09-14T18:00:00Z"}])
        assert tw.dispatch("o/r", "scan.yml", "main", "tok") == 0
        assert len(c.posted) == 1

    def test_a_failed_check_still_dispatches(self, monkeypatch, client):
        # Not being able to tell is not a reason to skip: a duplicate run is
        # cheap, a silently skipped one leaves the site stale.
        c = client()
        monkeypatch.setattr(c, "get", lambda url: (_ for _ in ()).throw(RuntimeError("down")))
        assert tw.dispatch("o/r", "scan.yml", "main", "tok") == 0
        assert len(c.posted) == 1

    def test_a_rejected_dispatch_is_a_failure(self, client):
        client(post_status=422)
        assert tw.dispatch("o/r", "scan.yml", "main", "tok") == 1

    def test_a_404_is_reported_as_a_scope_problem(self, client, caplog):
        # A fine-grained PAT without Actions: write gets 404, not 403, which is
        # a confusing way to be told the scope is wrong.
        client(post_status=404)
        with caplog.at_level("ERROR"):
            assert tw.dispatch("o/r", "scan.yml", "main", "tok") == 1
        assert "Actions: write" in caplog.text


class TestToken:
    def test_no_token_fails_loudly_rather_than_doing_nothing(self, monkeypatch, capsys):
        monkeypatch.delenv("GITHUB_DISPATCH_TOKEN", raising=False)
        monkeypatch.setattr("sys.argv", ["trigger_workflow.py", "scan.yml"])
        assert tw.main() == 1

    def test_a_blank_token_is_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv("GITHUB_DISPATCH_TOKEN", "   ")
        monkeypatch.setattr("sys.argv", ["trigger_workflow.py", "scan.yml"])
        assert tw.main() == 1
