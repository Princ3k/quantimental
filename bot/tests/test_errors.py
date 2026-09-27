"""
Tests for what the bot says when a command fails.

The bug these come from: /stock deferred, raised somewhere after the API call,
and left Discord showing "thinking" for fifteen minutes. It answered instantly in
one server and hung in another, and the difference was invisible from inside
Discord because a hung interaction says nothing at all.

So the property is about being audible rather than correct: every failure
produces a line, the line names a fix when there is one to name, and the log
carries the type that actually broke rather than the wrapper around it.
"""

from __future__ import annotations

import discord
import pytest

import errors


def _http_error(status: int, cls=discord.HTTPException):
    """A real discord.py HTTP exception, built the way the library builds one."""

    class _Response:
        def __init__(self) -> None:
            self.status = status
            self.reason = "because"

    return cls(_Response(), {"message": "nope", "code": 50013})


class _Wrapper(Exception):
    """Stands in for app_commands.CommandInvokeError, which wraps in `original`."""

    def __init__(self, original: BaseException) -> None:
        super().__init__(str(original))
        self.original = original


class TestUnwrapping:
    def test_a_wrapped_error_reports_the_one_underneath(self):
        # A log that only ever says CommandInvokeError never says what broke.
        inner = ValueError("the real problem")

        assert errors.unwrap(_Wrapper(inner)) is inner

    def test_an_unwrapped_error_is_left_alone(self):
        plain = ValueError("boom")

        assert errors.unwrap(plain) is plain


class TestTheMessage:
    def test_a_permission_failure_names_the_permissions(self):
        # The leading suspect for the original bug, and the only failure a server
        # admin can fix without us — so it is the one that must not read as a
        # generic error.
        message = errors.message_for(_http_error(403, discord.Forbidden))

        assert message == errors.FORBIDDEN
        assert "Send Messages" in message
        assert "Embed Links" in message

    def test_a_permission_failure_is_recognised_through_the_wrapper(self):
        # How it will actually arrive: raised inside a command, wrapped by
        # discord.py. Matching only the bare exception would miss every real one.
        wrapped = _Wrapper(_http_error(403, discord.Forbidden))

        assert errors.message_for(wrapped) == errors.FORBIDDEN

    def test_another_discord_rejection_is_not_reported_as_permissions(self):
        # Forbidden subclasses HTTPException, so the order of the checks is
        # load-bearing: asked the other way round, every rejection would tell a
        # server admin to go change permissions that were never the problem.
        assert errors.message_for(_http_error(400)) == errors.REFUSED

    @pytest.mark.parametrize(
        "error",
        [ValueError("bad row"), KeyError("v"), RuntimeError("event loop"), TimeoutError()],
    )
    def test_anything_else_still_gets_an_answer(self, error):
        # The whole point. Whatever broke, the channel hears something.
        assert errors.message_for(error) == errors.GENERIC

    def test_no_message_leaks_a_traceback(self):
        # These land in someone else's server. Internals are noise to everyone
        # who can read the channel; the traceback belongs in the deploy log.
        secret = "File \"/app/main.py\", line 181"
        for message in (errors.GENERIC, errors.FORBIDDEN, errors.REFUSED):
            assert secret not in message
            assert "Traceback" not in message
