"""Tests for evalcraft.sanitize — CassetteRedactor and CLI sanitize command."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from evalcraft.capture.recorder import CaptureContext, capture, get_active_context
from evalcraft.cli.main import cli
from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage
from evalcraft.sanitize import BUILTIN_PATTERNS, CassetteRedactor, RedactMode
from evalcraft.sanitize.redactor import BUILTIN_PATTERNS as _BP


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_cassette(**kwargs) -> Cassette:
    """Build a minimal cassette, accepting override kwargs for the spans' input/output."""
    c = Cassette(name="test", agent_name="agent")
    input_text = kwargs.get("input_text", "Hello")
    output_text = kwargs.get("output_text", "World")
    c.add_span(Span(
        kind=SpanKind.USER_INPUT,
        name="user_input",
        input=input_text,
    ))
    c.add_span(Span(
        kind=SpanKind.LLM_RESPONSE,
        name="llm:gpt-4",
        model="gpt-4",
        input=input_text,
        output=output_text,
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    ))
    c.add_span(Span(
        kind=SpanKind.AGENT_OUTPUT,
        name="agent_output",
        output=output_text,
    ))
    c.input_text = input_text
    c.output_text = output_text
    return c


def _cassette_with_pii() -> Cassette:
    """A cassette whose text fields contain one of every PII category."""
    text = (
        "User key: sk-abcDEFGHIJKLMNOPQRSTUVWXYZ1234  "
        "auth header: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig  "
        "contact: alice@example.com  "
        "phone: (415) 555-1234  "
        "ssn: 123-45-6789  "
        "card: 4111111111111111  "
        "server: 192.168.1.100"
    )
    return _make_cassette(input_text=text, output_text=text)


# ──────────────────────────────────────────────────────────────────────────────
# 1. RedactMode enum
# ──────────────────────────────────────────────────────────────────────────────

class TestRedactMode:
    def test_mask_value(self):
        assert RedactMode.MASK == "mask"

    def test_hash_value(self):
        assert RedactMode.HASH == "hash"

    def test_remove_value(self):
        assert RedactMode.REMOVE == "remove"

    def test_construct_from_string(self):
        assert RedactMode("mask") is RedactMode.MASK

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            RedactMode("invalid")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Built-in patterns — individual smoke tests
# ──────────────────────────────────────────────────────────────────────────────

class TestBuiltinPatterns:
    @pytest.mark.parametrize("text,expected_match", [
        ("sk-abc123DEF456GHI789JKL000MNO", True),   # openai key
        ("sk-proj-abcDEFGHIJKLMNOPQRSTUV", True),  # openai project key
        ("not-a-key", False),
    ])
    def test_openai_api_key(self, text, expected_match):
        pat = _BP["api_key_openai"]
        assert bool(pat.search(text)) == expected_match

    @pytest.mark.parametrize("text,expected_match", [
        ("ec_abcDEFGHIJKLMNOPQ", True),   # evalcraft key (18+ chars after ec_)
        ("ec_short", False),              # too short
    ])
    def test_evalcraft_api_key(self, text, expected_match):
        pat = _BP["api_key_evalcraft"]
        assert bool(pat.search(text)) == expected_match

    @pytest.mark.parametrize("text,expected_match", [
        ("Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", True),
        ("bearer token123", True),   # case-insensitive
        ("NotBearer token", False),
    ])
    def test_bearer_token(self, text, expected_match):
        pat = _BP["bearer_token"]
        assert bool(pat.search(text)) == expected_match

    @pytest.mark.parametrize("text,expected_match", [
        ("alice@example.com", True),
        ("user.name+tag@sub.domain.co.uk", True),
        ("not-an-email", False),
    ])
    def test_email(self, text, expected_match):
        pat = _BP["email"]
        assert bool(pat.search(text)) == expected_match

    @pytest.mark.parametrize("text,expected_match", [
        ("(415) 555-1234", True),
        ("415-555-1234", True),
        ("+1 415 555 1234", True),
        ("hello world", False),
    ])
    def test_phone(self, text, expected_match):
        pat = _BP["phone"]
        assert bool(pat.search(text)) == expected_match

    @pytest.mark.parametrize("text,expected_match", [
        ("123-45-6789", True),
        ("000-12-3456", False),   # all-zero area
        ("666-12-3456", False),   # 666 area
        ("123-00-6789", False),   # zero group
        ("123-45-0000", False),   # zero serial
    ])
    def test_ssn(self, text, expected_match):
        pat = _BP["ssn"]
        assert bool(pat.search(text)) == expected_match

    @pytest.mark.parametrize("text,expected_match", [
        ("4111111111111111", True),    # Visa 16-digit
        ("4111111111111", True),       # Visa 13-digit
        ("5500005555555559", True),    # Mastercard
        ("378282246310005", True),     # Amex
        ("6011111111111117", True),    # Discover
        ("1234567890123456", False),   # not a valid prefix
    ])
    def test_credit_card(self, text, expected_match):
        pat = _BP["credit_card"]
        assert bool(pat.search(text)) == expected_match

    @pytest.mark.parametrize("text,expected_match", [
        ("192.168.1.100", True),
        ("0.0.0.0", True),
        ("255.255.255.255", True),
        ("999.999.999.999", False),
        ("hello", False),
    ])
    def test_ip_address(self, text, expected_match):
        pat = _BP["ip_address"]
        assert bool(pat.search(text)) == expected_match


# ──────────────────────────────────────────────────────────────────────────────
# 3. CassetteRedactor — construction
# ──────────────────────────────────────────────────────────────────────────────

class TestCassetteRedactorInit:
    def test_default_mode_is_mask(self):
        r = CassetteRedactor()
        assert r.mode is RedactMode.MASK

    def test_builtin_patterns_loaded_by_default(self):
        r = CassetteRedactor()
        for name in BUILTIN_PATTERNS:
            assert name in r._patterns

    def test_no_builtin_flag(self):
        r = CassetteRedactor(use_builtin=False)
        assert len(r._patterns) == 0

    def test_custom_patterns_merged_with_builtin(self):
        custom = {"mytoken": re.compile(r"TOKEN_\w+")}
        r = CassetteRedactor(patterns=custom)
        assert "mytoken" in r._patterns
        assert "email" in r._patterns   # built-in still present

    def test_custom_mask_char(self):
        r = CassetteRedactor(mask_char="[REDACTED]")
        assert r.mask_char == "[REDACTED]"

    def test_mode_from_string(self):
        r = CassetteRedactor(mode="hash")
        assert r.mode is RedactMode.HASH


# ──────────────────────────────────────────────────────────────────────────────
# 4. add_pattern / remove_pattern
# ──────────────────────────────────────────────────────────────────────────────

class TestPatternManagement:
    def test_add_compiled_pattern(self):
        r = CassetteRedactor(use_builtin=False)
        r.add_pattern("tok", re.compile(r"TOKEN_\w+"))
        assert "tok" in r._patterns

    def test_add_string_pattern_compiles(self):
        r = CassetteRedactor(use_builtin=False)
        r.add_pattern("tok", r"TOKEN_\w+")
        assert isinstance(r._patterns["tok"], re.Pattern)

    def test_remove_pattern(self):
        r = CassetteRedactor()
        r.remove_pattern("email")
        assert "email" not in r._patterns

    def test_remove_unknown_pattern_silent(self):
        r = CassetteRedactor()
        r.remove_pattern("does_not_exist")  # must not raise


# ──────────────────────────────────────────────────────────────────────────────
# 5. Redaction modes — MASK, HASH, REMOVE
# ──────────────────────────────────────────────────────────────────────────────

class TestRedactionModes:
    def test_mask_mode_replaces_with_stars(self):
        r = CassetteRedactor(mode=RedactMode.MASK, use_builtin=False)
        r.add_pattern("email", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"))
        c = _make_cassette(input_text="contact: alice@example.com", output_text="ok")
        clean = r.redact(c)
        assert "alice@example.com" not in clean.input_text
        assert "***" in clean.input_text

    def test_mask_mode_custom_char(self):
        r = CassetteRedactor(mode=RedactMode.MASK, use_builtin=False, mask_char="[HIDDEN]")
        r.add_pattern("email", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"))
        c = _make_cassette(input_text="alice@example.com", output_text="ok")
        clean = r.redact(c)
        assert "[HIDDEN]" in clean.input_text

    def test_hash_mode_replaces_with_hex_prefix(self):
        r = CassetteRedactor(mode=RedactMode.HASH, use_builtin=False)
        r.add_pattern("email", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"))
        c = _make_cassette(input_text="alice@example.com", output_text="ok")
        clean = r.redact(c)
        assert "alice@example.com" not in clean.input_text
        assert "[redacted:" in clean.input_text
        # hash prefix is 8 hex chars
        m = re.search(r"\[redacted:([0-9a-f]{8})\]", clean.input_text)
        assert m is not None

    def test_hash_mode_is_deterministic(self):
        r = CassetteRedactor(mode=RedactMode.HASH, use_builtin=False)
        r.add_pattern("email", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"))
        c = _make_cassette(input_text="alice@example.com", output_text="ok")
        clean1 = r.redact(c)
        clean2 = r.redact(c)
        assert clean1.input_text == clean2.input_text

    def test_remove_mode_deletes_value(self):
        r = CassetteRedactor(mode=RedactMode.REMOVE, use_builtin=False)
        r.add_pattern("email", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"))
        c = _make_cassette(input_text="contact: alice@example.com end", output_text="ok")
        clean = r.redact(c)
        assert "alice@example.com" not in clean.input_text
        assert "contact:  end" in clean.input_text


# ──────────────────────────────────────────────────────────────────────────────
# 6. redact() — cassette is not mutated; returns new instance
# ──────────────────────────────────────────────────────────────────────────────

class TestRedactReturnsCopy:
    def test_original_not_mutated(self):
        r = CassetteRedactor()
        c = _cassette_with_pii()
        original_input = c.input_text
        _ = r.redact(c)
        assert c.input_text == original_input

    def test_returns_different_object(self):
        r = CassetteRedactor()
        c = _cassette_with_pii()
        clean = r.redact(c)
        assert clean is not c

    def test_cassette_id_preserved(self):
        r = CassetteRedactor()
        c = _cassette_with_pii()
        clean = r.redact(c)
        assert clean.id == c.id

    def test_cassette_name_preserved(self):
        r = CassetteRedactor()
        c = _cassette_with_pii()
        clean = r.redact(c)
        assert clean.name == c.name


# ──────────────────────────────────────────────────────────────────────────────
# 7. All built-in patterns fired on PII cassette
# ──────────────────────────────────────────────────────────────────────────────

class TestAllBuiltinPatternsRedacted:
    def setup_method(self):
        self.r = CassetteRedactor(mode=RedactMode.MASK)
        self.c = _cassette_with_pii()
        self.clean = self.r.redact(self.c)

    def test_openai_key_removed(self):
        assert "sk-abcDEFGHIJKLMNOPQRSTUVWXYZ1234" not in self.clean.input_text

    def test_bearer_token_removed(self):
        assert "eyJhbGciOiJIUzI1NiJ9.payload.sig" not in self.clean.input_text

    def test_email_removed(self):
        assert "alice@example.com" not in self.clean.input_text

    def test_phone_removed(self):
        assert "415) 555-1234" not in self.clean.input_text

    def test_ssn_removed(self):
        assert "123-45-6789" not in self.clean.input_text

    def test_credit_card_removed(self):
        assert "4111111111111111" not in self.clean.input_text

    def test_ip_address_removed(self):
        assert "192.168.1.100" not in self.clean.input_text

    def test_spans_also_redacted(self):
        # The redacted cassette's spans should not contain the original PII
        span_text = json.dumps([s.to_dict() for s in self.clean.spans])
        assert "alice@example.com" not in span_text
        assert "4111111111111111" not in span_text


# ──────────────────────────────────────────────────────────────────────────────
# 8. scan() — returns findings without modifying cassette
# ──────────────────────────────────────────────────────────────────────────────

class TestScan:
    def test_scan_does_not_modify_cassette(self):
        r = CassetteRedactor()
        c = _cassette_with_pii()
        original_input = c.input_text
        r.scan(c)
        assert c.input_text == original_input

    def test_scan_returns_dict(self):
        r = CassetteRedactor()
        c = _cassette_with_pii()
        findings = r.scan(c)
        assert isinstance(findings, dict)

    def test_scan_finds_email(self):
        r = CassetteRedactor()
        c = _cassette_with_pii()
        findings = r.scan(c)
        assert "email" in findings
        assert any("alice@example.com" in m for m in findings["email"])

    def test_scan_empty_cassette_returns_empty(self):
        r = CassetteRedactor()
        c = _make_cassette(input_text="hello world", output_text="nothing here")
        findings = r.scan(c)
        assert findings == {}

    def test_scan_deduplicates_matches(self):
        r = CassetteRedactor()
        # Same email appears twice in the text
        text = "alice@example.com and alice@example.com again"
        c = _make_cassette(input_text=text, output_text=text)
        findings = r.scan(c)
        assert findings["email"].count("alice@example.com") == 1


# ──────────────────────────────────────────────────────────────────────────────
# 9. redact_file()
# ──────────────────────────────────────────────────────────────────────────────

class TestRedactFile:
    def test_redact_file_creates_output(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        dst = tmp_path / "clean.cassette.json"
        _cassette_with_pii().save(src)
        r = CassetteRedactor()
        result = r.redact_file(src, dst)
        assert result == dst
        assert dst.exists()

    def test_redact_file_overwrites_source_when_no_output(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        _cassette_with_pii().save(src)
        r = CassetteRedactor()
        r.redact_file(src)
        clean = Cassette.load(src)
        assert "alice@example.com" not in clean.input_text

    def test_redact_file_content_is_valid_json(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        dst = tmp_path / "clean.cassette.json"
        _cassette_with_pii().save(src)
        CassetteRedactor().redact_file(src, dst)
        with open(dst) as f:
            data = json.load(f)
        assert "cassette" in data

    def test_redact_file_returns_path(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        dst = tmp_path / "clean.cassette.json"
        _cassette_with_pii().save(src)
        returned = CassetteRedactor().redact_file(src, dst)
        assert isinstance(returned, Path)


# ──────────────────────────────────────────────────────────────────────────────
# 10. CaptureContext redact= parameter
# ──────────────────────────────────────────────────────────────────────────────

class TestCaptureContextRedact:
    def test_redact_false_does_not_redact(self):
        with CaptureContext(name="test", redact=False) as ctx:
            ctx.record_input("contact: alice@example.com")
            ctx.record_output("phone: (415) 555-1234")
        assert "alice@example.com" in ctx.cassette.input_text

    def test_redact_true_masks_pii(self):
        with CaptureContext(name="test", redact=True) as ctx:
            ctx.record_input("key: sk-abcDEFGHIJKLMNOPQRSTUVWXYZ1234")
            ctx.record_output("email: alice@example.com")
        assert "sk-abcDEFGHIJKLMNOPQRSTUVWXYZ1234" not in ctx.cassette.output_text
        assert "alice@example.com" not in ctx.cassette.output_text

    def test_redact_with_custom_redactor(self):
        custom_redactor = CassetteRedactor(mode=RedactMode.HASH)
        with CaptureContext(name="test", redact=custom_redactor) as ctx:
            ctx.record_input("email: alice@example.com")
        assert "alice@example.com" not in ctx.cassette.input_text
        assert "[redacted:" in ctx.cassette.input_text

    def test_redact_true_saves_clean_cassette(self, tmp_path):
        path = tmp_path / "clean.json"
        with CaptureContext(name="test", redact=True, save_path=path) as ctx:
            ctx.record_input("ssn: 123-45-6789")
        data = json.loads(path.read_text())
        raw_text = json.dumps(data)
        assert "123-45-6789" not in raw_text

    def test_capture_decorator_redact_param(self):
        @capture(name="test_fn", redact=True)
        def my_fn():
            ctx = get_active_context()
            ctx.record_input("key: sk-abcDEFGHIJKLMNOPQRSTUVWXYZ1234")

        my_fn()
        # After decorator exits, cassette is finalized and redacted.
        # We can't access it from outside (no save_path), but no exception = pass.


# ──────────────────────────────────────────────────────────────────────────────
# 11. CLI — evalcraft sanitize
# ──────────────────────────────────────────────────────────────────────────────

class TestCLISanitize:
    def _invoke(self, args, cassette_path: str | None = None):
        runner = CliRunner()
        return runner.invoke(cli, args)

    def test_sanitize_writes_clean_file(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        dst = tmp_path / "clean.cassette.json"
        _cassette_with_pii().save(src)
        runner = CliRunner()
        result = runner.invoke(cli, ["sanitize", str(src), "--output", str(dst)])
        assert result.exit_code == 0, result.output
        assert dst.exists()
        clean_data = json.loads(dst.read_text())
        raw = json.dumps(clean_data)
        assert "alice@example.com" not in raw

    def test_sanitize_overwrites_source_by_default(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        _cassette_with_pii().save(src)
        runner = CliRunner()
        result = runner.invoke(cli, ["sanitize", str(src)])
        assert result.exit_code == 0, result.output
        raw = src.read_text()
        assert "alice@example.com" not in raw

    def test_sanitize_hash_mode(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        dst = tmp_path / "clean.cassette.json"
        _cassette_with_pii().save(src)
        runner = CliRunner()
        result = runner.invoke(cli, ["sanitize", str(src), "--output", str(dst), "--mode", "hash"])
        assert result.exit_code == 0, result.output
        raw = dst.read_text()
        assert "[redacted:" in raw

    def test_sanitize_remove_mode(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        dst = tmp_path / "clean.cassette.json"
        c = _make_cassette(input_text="email: alice@example.com end", output_text="ok")
        c.save(src)
        runner = CliRunner()
        result = runner.invoke(cli, ["sanitize", str(src), "--output", str(dst), "--mode", "remove"])
        assert result.exit_code == 0, result.output
        raw = dst.read_text()
        assert "alice@example.com" not in raw
        assert "***" not in raw

    def test_sanitize_scan_only(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        _cassette_with_pii().save(src)
        runner = CliRunner()
        result = runner.invoke(cli, ["sanitize", str(src), "--scan-only"])
        assert result.exit_code == 0, result.output
        assert "match" in result.output.lower()
        # File should NOT be modified
        raw = json.loads(src.read_text())
        assert "alice@example.com" in json.dumps(raw)

    def test_sanitize_scan_only_json(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        _cassette_with_pii().save(src)
        runner = CliRunner()
        result = runner.invoke(cli, ["sanitize", str(src), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "findings" in data
        assert "total" in data

    def test_sanitize_no_builtin_with_custom_pattern(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        c = _make_cassette(input_text="SECRET_abc123 hello", output_text="ok")
        c.save(src)
        dst = tmp_path / "clean.cassette.json"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "sanitize", str(src), "--output", str(dst),
            "--no-builtin", "--pattern", "mysecret=SECRET_\\w+",
        ])
        assert result.exit_code == 0, result.output
        raw = dst.read_text()
        assert "SECRET_abc123" not in raw

    def test_sanitize_invalid_pattern_exits_1(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        _make_cassette().save(src)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "sanitize", str(src), "--no-builtin", "--pattern", "bad=[unclosed"
        ])
        assert result.exit_code == 1

    def test_sanitize_output_contains_mode_info(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        _make_cassette().save(src)
        runner = CliRunner()
        result = runner.invoke(cli, ["sanitize", str(src), "--mode", "hash"])
        assert "hash" in result.output

    def test_sanitize_no_pii_scan_reports_clean(self, tmp_path):
        src = tmp_path / "run.cassette.json"
        _make_cassette(input_text="hello world", output_text="all good").save(src)
        runner = CliRunner()
        result = runner.invoke(cli, ["sanitize", str(src), "--scan-only"])
        assert result.exit_code == 0
        assert "no PII" in result.output
