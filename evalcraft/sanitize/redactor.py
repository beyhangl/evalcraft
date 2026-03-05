"""Cassette sanitization — redact PII and secrets from recorded cassettes.

Supports three redaction modes:

    MASK   — replace matched text with ``***`` (default)
    HASH   — replace matched text with the first 8 hex chars of its SHA-256
    REMOVE — replace matched text with an empty string

Built-in pattern categories
----------------------------
- ``api_key``      : OpenAI ``sk-*``, Evalcraft ``ec_*``
- ``bearer_token`` : ``Authorization: Bearer <token>`` headers
- ``email``        : RFC-5321 email addresses
- ``phone``        : US-style phone numbers (with optional country code)
- ``ssn``          : US Social Security Numbers  (NNN-NN-NNNN)
- ``credit_card``  : 13–16 digit card numbers (Visa, MC, Amex, Discover)
- ``ip_address``   : IPv4 addresses

Usage
-----
    from evalcraft.sanitize.redactor import CassetteRedactor, RedactMode

    redactor = CassetteRedactor(mode=RedactMode.MASK)
    clean = redactor.redact(cassette)          # returns a new Cassette
    redactor.redact_file("run.cassette.json")  # redact in place
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from evalcraft.core.models import Cassette


# ─── redaction modes ─────────────────────────────────────────────────────────

class RedactMode(str, Enum):
    """How to replace a matched sensitive value."""
    MASK = "mask"     # replace with ***
    HASH = "hash"     # replace with sha256[:8]
    REMOVE = "remove" # replace with ""


# ─── built-in patterns ───────────────────────────────────────────────────────

#: Compiled regex patterns shipped with the library.
#: Each key is a human-readable category name.
BUILTIN_PATTERNS: dict[str, re.Pattern[str]] = {
    # OpenAI-style API keys (sk-proj-... or sk-...)
    "api_key_openai": re.compile(
        r"sk-[A-Za-z0-9_\-]{20,}",
        re.ASCII,
    ),
    # Evalcraft API keys
    "api_key_evalcraft": re.compile(
        r"ec_[A-Za-z0-9]{16,}",
        re.ASCII,
    ),
    # Bearer tokens in Authorization headers
    "bearer_token": re.compile(
        r"(?i)\bBearer\s+([A-Za-z0-9\-._~+/]+=*)",
    ),
    # Email addresses
    "email": re.compile(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    ),
    # US phone numbers: (555) 123-4567 / 555-123-4567 / +1-555-123-4567
    # Requires separator (dash/dot/space) between groups to avoid UUID false positives
    "phone": re.compile(
        r"(?<![0-9a-fA-F\-])"          # not preceded by hex/digit/dash (avoids UUIDs)
        r"(?:\+?1[\s\-.]?)?"           # optional country code
        r"\(?\d{3}\)?[\s\-.]"          # area code + required separator
        r"\d{3}[\s\-.]\d{4}"           # exchange + subscriber with separator
        r"(?![0-9a-fA-F])",            # not followed by hex digit
        re.ASCII,
    ),
    # US Social Security Numbers: 123-45-6789
    "ssn": re.compile(
        r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b",
        re.ASCII,
    ),
    # Credit card numbers: 13–16 digits, optionally separated by spaces or dashes
    "credit_card": re.compile(
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|"         # Visa
        r"5[1-5][0-9]{14}|"                        # Mastercard
        r"3[47][0-9]{13}|"                         # Amex
        r"6(?:011|5[0-9]{2})[0-9]{12})"            # Discover
        r"\b",
        re.ASCII,
    ),
    # IPv4 addresses
    "ip_address": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        re.ASCII,
    ),
}


# ─── redactor ────────────────────────────────────────────────────────────────

class CassetteRedactor:
    """Scan and redact PII / secrets from a :class:`~evalcraft.core.models.Cassette`.

    Args:
        mode: Replacement strategy (MASK / HASH / REMOVE).
        patterns: Extra ``{name: compiled_regex}`` patterns to apply in
            addition to the built-in set.  Pass ``{}`` *and* set
            ``use_builtin=False`` to run only custom patterns.
        use_builtin: Whether to include the built-in pattern set.
            Defaults to ``True``.
        mask_char: The replacement string used in MASK mode.
            Defaults to ``"***"``.
    """

    def __init__(
        self,
        mode: RedactMode | str = RedactMode.MASK,
        patterns: dict[str, re.Pattern[str]] | None = None,
        use_builtin: bool = True,
        mask_char: str = "***",
    ) -> None:
        self.mode = RedactMode(mode)
        self.mask_char = mask_char

        self._patterns: dict[str, re.Pattern[str]] = {}
        if use_builtin:
            self._patterns.update(BUILTIN_PATTERNS)
        if patterns:
            self._patterns.update(patterns)

    # ── public API ────────────────────────────────────────────────────────────

    def add_pattern(self, name: str, pattern: str | re.Pattern[str]) -> None:
        """Register a custom redaction pattern.

        Args:
            name: Human-readable label shown in scan reports.
            pattern: A compiled ``re.Pattern`` or a regex string.
        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        self._patterns[name] = pattern

    def remove_pattern(self, name: str) -> None:
        """Unregister a pattern by name (built-in or custom).

        Silently ignores unknown names.
        """
        self._patterns.pop(name, None)

    def scan(self, cassette: Cassette) -> dict[str, list[str]]:
        """Return all matched values found in the cassette without modifying it.

        Returns:
            A ``{pattern_name: [matched_string, ...]}`` dict.  Matches are
            de-duplicated per pattern; ordering is preserved.
        """
        findings: dict[str, list[str]] = {name: [] for name in self._patterns}
        self._walk(cassette.to_dict(), findings, redacting=False)
        # Remove empty entries
        return {k: v for k, v in findings.items() if v}

    def redact(self, cassette: Cassette) -> Cassette:
        """Return a *new* ``Cassette`` with all matched values replaced.

        The original cassette is never mutated.
        """
        data = copy.deepcopy(cassette.to_dict())
        self._walk(data, findings=None, redacting=True)
        return Cassette.from_dict(data)

    def redact_file(
        self,
        path: str | Path,
        output: str | Path | None = None,
    ) -> Path:
        """Load a cassette JSON, redact it, and write the result.

        Args:
            path: Source cassette path.
            output: Destination path.  If ``None``, overwrites the source.

        Returns:
            The path that was written.
        """
        src = Path(path)
        dst = Path(output) if output else src
        cassette = Cassette.load(src)
        clean = self.redact(cassette)
        clean.save(dst)
        return dst

    # ── internal helpers ─────────────────────────────────────────────────────

    def _replace(self, match: re.Match[str]) -> str:
        """Compute the replacement string for a single regex match."""
        value = match.group(0)
        if self.mode == RedactMode.MASK:
            return self.mask_char
        if self.mode == RedactMode.HASH:
            digest = hashlib.sha256(value.encode()).hexdigest()[:8]
            return f"[redacted:{digest}]"
        # REMOVE
        return ""

    def _redact_string(self, text: str) -> str:
        """Apply all patterns to a string and return the redacted version."""
        for pattern in self._patterns.values():
            text = pattern.sub(self._replace, text)
        return text

    def _collect_matches(self, text: str, findings: dict[str, list[str]]) -> None:
        """Collect unique matches per pattern into *findings* (no replacement)."""
        for name, pattern in self._patterns.items():
            for m in pattern.finditer(text):
                value = m.group(0)
                if value not in findings[name]:
                    findings[name].append(value)

    def _walk(
        self,
        obj: Any,
        findings: dict[str, list[str]] | None,
        redacting: bool,
    ) -> Any:
        """Recursively traverse *obj*, redacting strings in-place (dict/list)
        or collecting matches into *findings*.

        Returns the (possibly mutated) object for convenience in list branches.
        """
        if isinstance(obj, str):
            if redacting:
                return self._redact_string(obj)
            else:
                assert findings is not None
                self._collect_matches(obj, findings)
                return obj

        if isinstance(obj, dict):
            for key, value in obj.items():
                result = self._walk(value, findings, redacting)
                if redacting:
                    obj[key] = result
            return obj

        if isinstance(obj, list):
            for i, item in enumerate(obj):
                result = self._walk(item, findings, redacting)
                if redacting:
                    obj[i] = result
            return obj

        # int, float, bool, None — nothing to redact
        return obj
