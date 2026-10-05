"""Provider retirement calendar.

Providers announce when a model stops answering. A recording made against a
model that has been shut down can't be re-recorded or compared with a live run,
and one that retires soon needs migrating. ``check-stale`` checks every
recorded model against this calendar, so it can say so without being told the
current model set.

Dates are copied from the providers' deprecation pages and the calendar is only
as current as the evalcraft release that ships it (see ``CALENDAR_DATE``). They
are the providers' own platforms' dates: Amazon Bedrock, Google Cloud and Azure
set their own schedules for the models they host.
Matching is exact, or the listed id followed by a date suffix, so an entry for
``o1`` covers ``o1-2024-12-17`` but never ``o1-mini``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

ANTHROPIC_SOURCE = "https://platform.claude.com/docs/en/about-claude/model-deprecations"
OPENAI_SOURCE = "https://developers.openai.com/api/docs/deprecations"

#: When the calendar below was last checked against the providers' pages.
CALENDAR_DATE = date(2026, 10, 5)


@dataclass(frozen=True)
class Retirement:
    model: str
    retires_on: date
    source: str
    replacement: str | None = None


def _entries(models: str, retires_on: str, source: str, replacement: str | None = None):
    day = date.fromisoformat(retires_on)
    return tuple(Retirement(m, day, source, replacement) for m in models.split())


RETIREMENTS: tuple[Retirement, ...] = (
    # Anthropic
    *_entries("claude-sonnet-4-5 claude-sonnet-4-5-20250929", "2026-11-30",
              ANTHROPIC_SOURCE, "claude-sonnet-5-5"),
    *_entries("claude-opus-4-1 claude-opus-4-1-20250805", "2026-08-05",
              ANTHROPIC_SOURCE, "claude-opus-4-8"),
    *_entries("claude-opus-4-0 claude-opus-4-20250514", "2026-06-15",
              ANTHROPIC_SOURCE, "claude-opus-4-8"),
    *_entries("claude-sonnet-4-0 claude-sonnet-4-20250514", "2026-06-15",
              ANTHROPIC_SOURCE, "claude-sonnet-4-6"),
    *_entries("claude-3-haiku-20240307", "2026-04-20", ANTHROPIC_SOURCE, "claude-haiku-4-5"),
    *_entries("claude-3-7-sonnet-20250219", "2026-02-19", ANTHROPIC_SOURCE, "claude-sonnet-4-6"),
    *_entries("claude-3-5-haiku-20241022", "2026-02-19", ANTHROPIC_SOURCE, "claude-haiku-4-5"),
    *_entries("claude-3-opus-20240229", "2026-01-05", ANTHROPIC_SOURCE, "claude-opus-4-8"),
    *_entries("claude-3-5-sonnet-20240620 claude-3-5-sonnet-20241022", "2025-10-28",
              ANTHROPIC_SOURCE, "claude-sonnet-4-6"),
    *_entries("claude-2.0 claude-2.1 claude-3-sonnet-20240229", "2025-07-21", ANTHROPIC_SOURCE),
    *_entries("claude-1.0 claude-1.1 claude-1.2 claude-1.3 claude-instant-1.0 "
              "claude-instant-1.1 claude-instant-1.2", "2024-11-06", ANTHROPIC_SOURCE),
    # OpenAI
    *_entries("gpt-5.3-codex gpt-5.1 gpt-5.4-nano", "2027-04-01", OPENAI_SOURCE),
    *_entries("gpt-5-2025-08-07 gpt-5-mini-2025-08-07 gpt-5-nano-2025-08-07 "
              "gpt-5-pro-2025-10-06 o3-2025-04-16 o3-pro-2025-06-10",
              "2026-12-11", OPENAI_SOURCE),
    *_entries("gpt-3.5-turbo-0125 gpt-4-0613 gpt-4-1106-preview gpt-4-turbo-2024-04-09 "
              "gpt-4.1-nano gpt-4o-2024-05-13 o1 o1-pro o3-mini o4-mini",
              "2026-10-23", OPENAI_SOURCE),
    *_entries("gpt-5.4-cyber", "2026-10-01", OPENAI_SOURCE),
    *_entries("gpt-3.5-turbo-instruct gpt-3.5-turbo-1106 babbage-002 davinci-002",
              "2026-09-28", OPENAI_SOURCE),
    *_entries("gpt-5.2-chat-latest gpt-5.3-chat-latest", "2026-08-10", OPENAI_SOURCE),
    *_entries("gpt-5-chat-latest gpt-5-codex gpt-5.1-codex gpt-5.1-codex-max "
              "gpt-5.1-codex-mini gpt-5.1-chat-latest gpt-5.2-codex computer-use-preview "
              "o3-deep-research o4-mini-deep-research", "2026-07-23", OPENAI_SOURCE),
    *_entries("gpt-4-0314 gpt-4-0125-preview", "2026-03-26", OPENAI_SOURCE),
    *_entries("chatgpt-4o-latest", "2026-02-17", OPENAI_SOURCE),
    *_entries("o1-mini", "2025-10-27", OPENAI_SOURCE),
)

_BY_MODEL = {r.model: r for r in RETIREMENTS}
_DATE_SUFFIX = re.compile(r"[-@](?:\d{8}|\d{4}-\d{2}-\d{2})$")


def find_retirement(model: str | None) -> Retirement | None:
    """The scheduled retirement of ``model`` (or the id it is a snapshot of).

    A framework provider prefix (``anthropic:``) is ignored, and a Vertex-style
    ``@20250929`` counts as a date suffix.
    """
    if not model:
        return None
    from evalcraft.core.pricing import strip_provider

    name = strip_provider(model)
    if name in _BY_MODEL:
        return _BY_MODEL[name]
    if "@" in name:
        dashed = name.replace("@", "-", 1)
        if dashed in _BY_MODEL:
            return _BY_MODEL[dashed]
    base = _DATE_SUFFIX.sub("", name)
    return _BY_MODEL.get(base) if base != name else None
