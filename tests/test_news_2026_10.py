"""0.11: pricing for current models, the retirement calendar, pass^k, cache hit rate."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from evalcraft import (
    assert_cache_hit_rate_at_least,
    assert_cost_under,
    assert_pass_hat_k,
    assert_tool_called,
    consistency,
    register_price,
)
from evalcraft.adapters.anthropic_adapter import _estimate_cost as anthropic_cost
from evalcraft.adapters.gemini_adapter import _estimate_cost as gemini_cost
from evalcraft.adapters.openai_adapter import _estimate_cost as openai_cost
from evalcraft.adapters.pydantic_ai_adapter import _estimate_cost as pydantic_cost
from evalcraft.cli.main import cli
from evalcraft.config import ConfigError, load_config
from evalcraft.core.models import Cassette, Provenance, Span, SpanKind, TokenUsage
from evalcraft.core.pricing import clear_registered_prices, looks_paid, match_model, price_for
from evalcraft.regression.detector import Severity
from evalcraft.staleness import StalenessChecker, find_retirement

REPO_ROOT = Path(__file__).resolve().parent.parent
M = 1_000_000


@pytest.fixture(autouse=True)
def _clean_prices():
    clear_registered_prices()
    yield
    clear_registered_prices()


def _llm(model, prompt=0, completion=0, cache_read=0, cache_write=0, cost=None):
    return Span(
        kind=SpanKind.LLM_RESPONSE, model=model, cost_usd=cost,
        token_usage=TokenUsage(prompt_tokens=prompt, completion_tokens=completion,
                               total_tokens=prompt + completion,
                               cache_read_tokens=cache_read, cache_write_tokens=cache_write),
    )


def _cassette(*spans, name="c"):
    c = Cassette(name=name)
    for s in spans:
        c.add_span(s)
    return c


# ── lookup ───────────────────────────────────────────────────────────────────

class TestLookup:
    def test_snapshot_gets_its_own_model_not_the_bigger_sibling(self):
        assert openai_cost("gpt-4o-mini-2024-07-18", M, 0) == pytest.approx(0.15)
        assert openai_cost("gpt-4.1-mini-2025-04-14", M, 0) == pytest.approx(0.40)
        assert openai_cost("o3-mini-2025-01-31", M, 0) == pytest.approx(1.10)

    def test_shared_prefix_is_not_a_match(self):
        assert match_model({"gpt-5": 1}, "gpt-5.5") is None
        assert match_model({"gpt-5": 1}, "gpt-5-2025-08-07") == 1
        assert match_model({"a": 1, "a-b": 2}, "a-b-20250101") == 2
        assert match_model({"o3": 1}, "o3-pro") is None
        assert match_model({"m": 1}, "m@20250929") == 1
        assert match_model({"m": 1}, "m-latest") == 1

    @pytest.mark.parametrize("model,inp,out", [
        ("claude-opus-4-6", 5.0, 25.0),
        ("claude-haiku-4-5", 1.0, 5.0),
        ("claude-haiku-4-5-20251001", 1.0, 5.0),
        ("claude-sonnet-5-5", 2.0, 10.0),
        ("claude-opus-5-5", 4.0, 20.0),
        ("claude-fable-5-1", 10.0, 50.0),
    ])
    def test_anthropic_prices(self, model, inp, out):
        assert anthropic_cost(model, M, M) == pytest.approx(inp + out)

    @pytest.mark.parametrize("model,inp,out", [
        ("gpt-6.1-sol", 2.0, 10.0), ("gpt-6-astra", 10.0, 50.0), ("gpt-6-luna", 0.10, 0.50),
        ("gpt-5.5", 5.0, 30.0), ("gpt-5.6-terra", 2.0, 12.0), ("gpt-4.1-mini", 0.40, 1.60),
        ("o4-mini", 1.10, 4.40),
    ])
    def test_openai_prices(self, model, inp, out):
        assert openai_cost(model, M, M) == pytest.approx(inp + out)

    def test_per_model_cache_discounts(self):
        # Opus 5.5 reads cache at 0.05x of $4; gpt-6.1-sol at 0.05x of $2.
        assert anthropic_cost("claude-opus-5-5", 0, 0, cache_read_tokens=M) == pytest.approx(0.20)
        assert openai_cost("gpt-6.1-sol", 0, 0, cache_read_tokens=M) == pytest.approx(0.10)
        assert openai_cost("gpt-5.4", 0, 0, cache_read_tokens=M) == pytest.approx(0.25)

    @pytest.mark.parametrize("model", [
        "claude-opus-4-8", "claude-opus-4-7", "claude-fable-5", "claude-mythos-5-1",
        "claude-sonnet-5", "claude-opus-5", "claude-sonnet-4-6", "o3-pro", "gpt-5-pro",
    ])
    def test_current_models_have_a_price(self, model):
        assert price_for(model) is not None

    def test_variants_do_not_borrow_the_base_price(self):
        assert price_for("o3-deep-research") is None
        assert price_for("gpt-5.1-codex-max") is None
        assert openai_cost("o3-pro-2025-06-10", M, 0) == pytest.approx(20.0)

    def test_pydantic_ai_uses_shared_tables(self):
        assert pydantic_cost("gpt-5.4-mini", M, 0) == openai_cost("gpt-5.4-mini", M, 0)
        assert pydantic_cost("openai:claude-sonnet-5-5", M, 0) == pytest.approx(2.0)
        assert pydantic_cost("llama-3.1-8b-instant", M, 0) == pytest.approx(0.05)

    def test_price_for_strips_prefixes(self):
        assert price_for("anthropic:claude-haiku-4-5") is not None
        assert price_for("models/gemini-2.5-flash") is not None
        assert price_for("no-such-model") is None and price_for(None) is None

    def test_looks_paid(self):
        assert looks_paid("gpt-7") and looks_paid("claude-next") and looks_paid("o5-mini")
        assert looks_paid("openai:gpt-7") and looks_paid("ft:gpt-4o-mini:org::x")
        assert not looks_paid("mock-llm") and not looks_paid("example-model")
        # Local / open-weight models are free to run.
        for model in ("gpt-oss:20b", "ollama:gpt-oss:20b", "deepseek-r1:7b", "gpt-oss-120b",
                      "mistral-nemo", "o200k"):
            assert not looks_paid(model), model


class TestRegisterPrice:
    def test_registered_price_is_used_and_wins(self):
        register_price("my-finetune", input_usd_per_mtok=3, output_usd_per_mtok=12,
                       cached_input_usd_per_mtok=0.3)
        assert openai_cost("my-finetune-2026-10-01", M, M) == pytest.approx(15.0)
        assert openai_cost("my-finetune", 0, 0, cache_read_tokens=M) == pytest.approx(0.3)
        register_price("gpt-4o", input_usd_per_mtok=1, output_usd_per_mtok=1)
        assert openai_cost("gpt-4o", M, 0) == pytest.approx(1.0)
        assert gemini_cost("my-finetune", M, 0) == pytest.approx(3.0)

    def test_registered_price_does_not_leak_to_other_models(self):
        register_price("gpt-4o", input_usd_per_mtok=99, output_usd_per_mtok=99)
        assert openai_cost("gpt-4o-mini", M, 0) == pytest.approx(0.15)
        assert price_for("gpt-4o-mini").input_usd_per_mtok == pytest.approx(0.15)
        assert openai_cost("gpt-4o-2024-08-06", M, 0) == pytest.approx(99.0)

    def test_fine_tune_ids_can_be_registered(self):
        ft = "ft:gpt-4o-mini-2024-07-18:org::abc"
        assert price_for(ft) is None
        register_price(ft, input_usd_per_mtok=0.3, output_usd_per_mtok=1.2)
        assert price_for(ft).input_usd_per_mtok == pytest.approx(0.3)
        assert openai_cost(ft, M, 0) == pytest.approx(0.3)

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            register_price("x", input_usd_per_mtok=-1, output_usd_per_mtok=1)


# ── assert_cost_under ────────────────────────────────────────────────────────

class TestCostUnder:
    def test_unknown_paid_model_fails_instead_of_counting_zero(self):
        c = _cassette(_llm("gpt-7-preview", prompt=1000, completion=1000))
        result = assert_cost_under(c, max_usd=100)
        assert not result.passed
        assert "gpt-7-preview" in result.message and "register_price" in result.message
        assert assert_cost_under(c, max_usd=100, on_unknown_price="ignore").passed

    def test_unpriced_span_is_priced_from_todays_tables(self):
        # Recorded before evalcraft knew Sonnet 5.5: cost None, tokens present.
        c = _cassette(_llm("claude-sonnet-5-5", prompt=M, completion=0))
        assert assert_cost_under(c, max_usd=2.5).passed
        result = assert_cost_under(c, max_usd=1.0)
        assert not result.passed and result.actual == pytest.approx(2.0)

    def test_registered_price_rescues_unknown_model(self):
        c = _cassette(_llm("gpt-7-preview", prompt=M))
        register_price("gpt-7-preview", input_usd_per_mtok=1, output_usd_per_mtok=1)
        assert assert_cost_under(c, max_usd=1.5).passed

    def test_mock_and_recorded_costs_unchanged(self):
        c = _cassette(_llm("mock-llm", prompt=10, completion=20), _llm("gpt-4o", cost=0.5))
        result = assert_cost_under(c, max_usd=0.6)
        assert result.passed and result.actual == pytest.approx(0.5)

    def test_bad_mode(self):
        with pytest.raises(ValueError):
            assert_cost_under(_cassette(), 1, on_unknown_price="maybe")


class TestConfigPrices:
    def test_parse(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.evalcraft.prices]\n"ft" = { input = 3, output = 12, cached_input = 0.3 }\n')
        cfg = load_config(tmp_path)
        assert cfg.prices == {"ft": {"input_usd_per_mtok": 3.0, "output_usd_per_mtok": 12.0,
                                     "cached_input_usd_per_mtok": 0.3}}

    @pytest.mark.parametrize("body", [
        '"ft" = { input = 3 }',
        '"ft" = { input = 3, output = -1 }',
        '"ft" = { input = 3, output = 1, cached = 1 }',
        '"ft" = 3',
    ])
    def test_bad_entries(self, tmp_path, body):
        (tmp_path / "pyproject.toml").write_text(f"[tool.evalcraft.prices]\n{body}\n")
        with pytest.raises(ConfigError):
            load_config(tmp_path)

    def test_cli_eval_uses_config_prices(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.evalcraft.prices]\n"gpt-7-preview" = { input = 1, output = 1 }\n')
        _cassette(_llm("gpt-7-preview", prompt=M)).save(tmp_path / "c.json")
        assert CliRunner().invoke(cli, ["eval", "c.json", "--max-cost", "2"]).exit_code == 0
        assert CliRunner().invoke(cli, ["eval", "c.json", "--max-cost", "0.5"]).exit_code == 1

    def test_pytest_plugin_registers_config_prices(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.evalcraft.prices]\n"gpt-7-preview" = { input = 1, output = 1 }\n')
        (tmp_path / "test_it.py").write_text(
            "from evalcraft import assert_cost_under\n"
            "from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage\n"
            "def test_budget():\n"
            "    c = Cassette(name='c')\n"
            "    c.add_span(Span(kind=SpanKind.LLM_RESPONSE, model='gpt-7-preview',\n"
            "        token_usage=TokenUsage(prompt_tokens=1000000)))\n"
            "    r = assert_cost_under(c, max_usd=2)\n"
            "    assert r.passed, r.message\n"
        )
        env = {k: v for k, v in os.environ.items() if k != "CI"}
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr


# ── retirement calendar ──────────────────────────────────────────────────────

class TestRetirementCalendar:
    def test_matching(self):
        assert find_retirement("o1-2024-12-17").model == "o1"
        assert find_retirement("o1-mini").model == "o1-mini"
        assert find_retirement("gpt-4o") is None
        assert find_retirement("gpt-5") is None
        assert find_retirement("gpt-5.1-codex").model == "gpt-5.1-codex"
        assert find_retirement("claude-sonnet-4-5-20250929").replacement == "claude-sonnet-5-5"
        assert find_retirement("claude-sonnet-4-5@20250929").model == "claude-sonnet-4-5-20250929"
        assert find_retirement("anthropic:claude-3-5-sonnet-20241022") is not None
        assert find_retirement("openai:o1").model == "o1"
        assert str(find_retirement("claude-3-haiku-20240307").retires_on) == "2026-04-20"

    def _check(self, model, today, **kw):
        return StalenessChecker(today=today, **kw).check(_cassette(_llm(model)))

    def test_shut_down_is_critical(self):
        report = self._check("o3-mini-2025-01-31", date(2026, 10, 24))
        f = next(f for f in report.findings if f.category == "model_shut_down")
        assert f.severity == Severity.CRITICAL and report.has_critical

    def test_retiring_soon_is_a_warning(self):
        report = self._check("claude-sonnet-4-5-20250929", date(2026, 10, 5))
        f = next(f for f in report.findings if f.category == "model_retiring")
        assert f.severity == Severity.WARNING and f.metadata["days_left"] == 56
        assert "claude-sonnet-5-5" in f.message
        assert not report.has_critical

    def test_window_and_off_switch(self):
        cats = lambda r: [f.category for f in r.findings]  # noqa: E731
        far = self._check("gpt-5.1", date(2026, 10, 5))
        assert "model_retiring" not in cats(far)
        near = self._check("gpt-5.1", date(2026, 10, 5), retiring_within_days=200)
        assert "model_retiring" in cats(near)
        off = self._check("o3-mini", date(2027, 1, 1), retirement_calendar=False)
        assert not off.has_critical

    def test_uses_provenance_models_too(self):
        c = Cassette(name="p")
        c.provenance = Provenance(recorded_at=1.0, models=["o1-2024-12-17"])
        report = StalenessChecker(today=date(2026, 11, 1)).check(c)
        assert "model_shut_down" in [f.category for f in report.findings]

    def test_cli(self, tmp_path):
        _cassette(_llm("o1-mini")).save(tmp_path / "c.json")
        result = CliRunner().invoke(cli, ["check-stale", str(tmp_path / "c.json")])
        assert result.exit_code == 1 and "model_shut_down" in result.output
        result = CliRunner().invoke(
            cli, ["check-stale", str(tmp_path / "c.json"), "--no-retirement-calendar"])
        assert result.exit_code == 0, result.output


# ── pass^k ───────────────────────────────────────────────────────────────────

def _run(called: bool):
    c = Cassette(name="r")
    if called:
        c.add_span(Span(kind=SpanKind.TOOL_CALL, tool_name="lookup"))
    return c


CHECK = lambda r: assert_tool_called(r, "lookup")  # noqa: E731


class TestConsistency:
    def test_metrics(self):
        result = consistency({
            "a": [_run(True)] * 5,
            "b": [_run(True)] * 4 + [_run(False)],
            "c": [_run(False)] * 5,
        }, CHECK)
        assert result.k == 5 and result.tasks == 3
        assert result.mean_at_k == pytest.approx(9 / 15)
        assert result.pass_at_k == pytest.approx(2 / 3)
        assert result.pass_hat_k == pytest.approx(1 / 3)
        assert result.consistency_gap == pytest.approx(9 / 15 - 1 / 3)
        assert result.per_task["b"] == [True, True, True, True, False]
        assert result.failures["b"][0].startswith("run 5:")

    def test_single_task_list(self):
        assert consistency([_run(True), _run(True)], CHECK).pass_hat_k == 1.0

    def test_assertion(self):
        runs = {"a": [_run(True)] * 3, "b": [_run(True), _run(False), _run(True)]}
        result = assert_pass_hat_k(runs, CHECK)
        assert not result.passed and "['b']" in result.message and "pass^3 = 50%" in result.message
        assert assert_pass_hat_k(runs, CHECK, at_least=0.5).passed

    def test_generators_and_bad_inputs(self):
        result = consistency({"a": (r for r in [_run(True), _run(True)])}, CHECK)
        assert result.k == 2 and result.pass_hat_k == 1.0
        with pytest.raises(TypeError):
            consistency("runs", CHECK)
        with pytest.raises(TypeError):
            consistency(_run(True), CHECK)

    def test_validation(self):
        with pytest.raises(ValueError):
            consistency({"a": [_run(True)], "b": [_run(True)] * 2}, CHECK)
        with pytest.raises(ValueError):
            consistency([_run(True)])
        with pytest.raises(ValueError):
            consistency([], CHECK)


# ── cache hit rate ───────────────────────────────────────────────────────────

class TestCacheHitRate:
    def test_rate(self):
        c = _cassette(_llm("m", prompt=1000, cache_write=1000),
                      _llm("m", prompt=200, cache_read=1800))
        result = assert_cache_hit_rate_at_least(c, 0.4)
        assert result.passed and result.actual == pytest.approx(1800 / 4000)
        assert not assert_cache_hit_rate_at_least(c, 0.5).passed

    def test_no_input_fails(self):
        assert not assert_cache_hit_rate_at_least(_cassette(), 0.1).passed

    def test_bad_threshold(self):
        with pytest.raises(ValueError):
            assert_cache_hit_rate_at_least(_cassette(), 1.5)
