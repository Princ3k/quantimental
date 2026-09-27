"""
What to say when a command fails.

A slash command defers first and answers later. If it raises in between, Discord
keeps showing "thinking" until the interaction expires fifteen minutes on, and
nothing in the channel ever says otherwise — so the bot looks hung rather than
broken, and the person who ran it has no reason to report it.

That is not hypothetical. `/stock` sat on "thinking" in a partner's server while
answering instantly elsewhere, and the only record of why was a traceback in a
deploy log nobody was reading. Every command failure has to produce a message.
This module decides which one.
"""

from __future__ import annotations

import discord

# Deliberately not a traceback. This lands in somebody else's channel, where a
# Python exception is noise to everyone who can read it. The traceback goes to
# the deploy log, which is where the person who can act on it is looking.
GENERIC = "That did not work. It has been logged — try again in a moment."

# The one failure a reader can fix themselves, so it is the one worth naming.
# Both permissions are listed because an embed needs the second one and the
# error does not distinguish them.
FORBIDDEN = (
    "I am not allowed to post that in this channel. A server admin can fix it by "
    "giving my role **Send Messages** and **Embed Links** here."
)

REFUSED = "Discord refused that message. It has been logged."


def unwrap(error: BaseException) -> BaseException:
    """
    The exception that actually failed.

    discord.py wraps whatever a command raises in CommandInvokeError, so the
    interesting type sits one level down. A log that only ever says
    CommandInvokeError is a log that never tells you what broke.
    """
    original = getattr(error, "original", None)
    return original if original is not None else error


def message_for(error: BaseException) -> str:
    """The line to send back, chosen by what the reader could act on."""
    error = unwrap(error)
    # Forbidden subclasses HTTPException, so it has to be asked about first.
    if isinstance(error, discord.Forbidden):
        return FORBIDDEN
    if isinstance(error, discord.HTTPException):
        return REFUSED
    return GENERIC
