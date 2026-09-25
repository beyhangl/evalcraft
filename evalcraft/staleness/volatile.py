"""Volatile values baked into a recording.

A cassette is a snapshot of what the agent sent. If that included something
generated fresh on every run (a UUID, the current timestamp, a temporary path),
the recording is brittle: prompt-keyed mocks built from it (``evalcraft mock``)
miss on the next run because the prompt no longer matches byte for byte, and
re-recording churns the diff with values nobody changed on purpose.

Only what the agent *generated and sent* is scanned: LLM request inputs and
tool-call arguments. Content that was only passed along is skipped, namely
tool results and earlier assistant turns fed back into a prompt, and any value
that also appears in a recorded output. An order id a tool returned, which the
model then passes to the next tool, is replayed data, not a leak.

The patterns are heuristics tuned for precision. A bare date or a 10-digit
number is never flagged, since those are usually real content.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from evalcraft.core.models import Cassette, SpanKind

VOLATILE_PATTERNS: dict[str, re.Pattern[str]] = {
    "uuid": re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
    # A date alone is often real content ("arrives 2026-09-26"), so require a time.
    "timestamp": re.compile(
        r"\b\d{4}-\d{2}-\d{2}"
        r"(?:T\d{2}:\d{2}(?::\d{2})?|[ ]\d{2}:\d{2}:\d{2})"
        r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
    ),
    "temp_path": re.compile(
        r"(?<![\w./])(?:/private)?/var/folders/[^\s\"']+"
        r"|(?<![\w./])(?:/private)?/tmp/[^\s\"']+"
        r"|pytest-of-[\w.-]+/pytest-\d+[^\s\"']*"
        r"|(?i:\b[a-z]:(?:\\+)users(?:\\+)[^\\\s\"']+(?:\\+)appdata(?:\\+)local(?:\\+)temp)"
        r"[^\s\"']*"
        r"|(?i:\b[a-z]:(?:\\+)a(?:\\+)_temp)[^\s\"']*"
    ),
}

_PASSED_ALONG_ROLES = ("tool", "function", "assistant")
_ROLE_LINE = re.compile(r"^(system|developer|user|assistant|tool|function|unknown): ", re.M)
_PASSED_ALONG_TYPES = ("tool_result", "function_call_output")


@dataclass(frozen=True)
class VolatileValue:
    """One volatile value found in a recording."""

    kind: str
    value: str
    where: str  # e.g. "llm input #2" or "tool args: search"

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "value": self.value, "where": self.where}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _split_input(value: Any) -> tuple[str, str]:
    """Split an LLM input into (generated, passed_along) text."""
    if isinstance(value, list):
        sent: list[str] = []
        passed: list[str] = []
        for item in value:
            is_passed = isinstance(item, dict) and (
                item.get("role") in _PASSED_ALONG_ROLES
                or item.get("type") in _PASSED_ALONG_TYPES
            )
            (passed if is_passed else sent).append(_text(item))
        return "\n".join(sent), "\n".join(passed)
    text = _text(value)
    matches = list(_ROLE_LINE.finditer(text))
    if not matches:
        return text, ""
    sent, passed = [text[: matches[0].start()]], []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        (passed if m.group(1) in _PASSED_ALONG_ROLES else sent).append(text[m.start():end])
    return "\n".join(sent), "\n".join(passed)


def find_volatile_values(cassette: Cassette) -> list[VolatileValue]:
    """Return volatile values the agent generated and sent in ``cassette``.

    Each distinct (kind, value) is reported once, at its first location.
    """
    scanned: list[tuple[str, str]] = []
    known: list[str] = []
    llm_index = 0
    for span in cassette.spans:
        if span.kind in (SpanKind.LLM_REQUEST, SpanKind.LLM_RESPONSE):
            llm_index += 1
            sent, passed = _split_input(span.input)
            scanned.append((sent, f"llm input #{llm_index}"))
            known.extend([passed, _text(span.output)])
        elif span.kind == SpanKind.TOOL_CALL:
            scanned.append((_text(span.tool_args), f"tool args: {span.tool_name}"))
            known.extend([_text(span.tool_result), _text(span.output)])
        else:
            known.extend([_text(span.output), _text(span.tool_result)])
    known_text = "\n".join(known)

    found: list[VolatileValue] = []
    seen: set[tuple[str, str]] = set()
    for text, where in scanned:
        for kind, pattern in VOLATILE_PATTERNS.items():
            for match in pattern.finditer(text):
                value = match.group(0).rstrip(".,;:)]}\\")
                key = (kind, value)
                if key in seen or value in known_text:
                    continue
                seen.add(key)
                found.append(VolatileValue(kind, value, where))
    return found
