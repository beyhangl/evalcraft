"""The path a new user takes on day one must stay green.

`pip install` → `evalcraft init` → `pytest` is the first thing anyone runs, and
it had silently broken: the scaffolded suite failed on its first run because
``Cassette.add_span`` did not update the metrics its docstring promised, and
``init`` aborted outright when no terminal was attached (CI, coding agents).
These tests run the real scaffold end to end so that cannot regress unnoticed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from evalcraft.cli.main import cli
from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage

REPO_ROOT = Path(__file__).resolve().parent.parent
FRAMEWORKS = ["generic", "openai", "anthropic", "langgraph", "crewai"]


def _run_scaffold(tmp_path: Path, *init_args: str, stdin: str | None = None, ci: bool = False):
    """Run `evalcraft init` then pytest on what it generated, with no API keys."""
    result = CliRunner().invoke(cli, ["init", *init_args], input=stdin, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "CI")}
    if ci:
        env["CI"] = "true"
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestScaffoldIsGreen:
    @pytest.mark.parametrize("ci", [False, True], ids=["local", "ci"])
    @pytest.mark.parametrize("framework", FRAMEWORKS)
    def test_fresh_scaffold_is_fully_green(self, in_tmp, framework, ci):
        # Green with no API keys, including in CI where missing cassettes fail,
        # and with nothing skipped: the sample recording makes replay run too.
        proc = _run_scaffold(in_tmp, "--framework", framework, ci=ci)
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
        summary = proc.stdout.splitlines()[-1]
        assert "failed" not in summary and "error" not in summary, summary
        assert "skipped" not in summary, summary

    def test_plain_run_does_not_modify_the_sample(self, in_tmp):
        _run_scaffold(in_tmp, "--framework", "generic")
        sample = in_tmp / "tests" / "cassettes" / "my_run.json"
        before = sample.read_text()
        env = {k: v for k, v in os.environ.items() if k != "CI"}
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                       cwd=in_tmp, env=env, capture_output=True, text=True, timeout=120)
        assert sample.read_text() == before
        assert sorted(p.name for p in sample.parent.iterdir()) == [".gitkeep", "my_run.json"]

    def test_init_without_a_terminal_uses_the_default(self, in_tmp):
        # CliRunner with no input == stdin at EOF, as in CI or a coding agent.
        result = CliRunner().invoke(cli, ["init"], input="")
        assert result.exit_code == 0, result.output
        assert "generic" in result.output
        assert (in_tmp / "tests" / "test_agent.py").exists()

    def test_piped_answer_is_still_honoured(self, in_tmp):
        result = CliRunner().invoke(cli, ["init"], input="anthropic\n")
        assert result.exit_code == 0, result.output
        assert "anthropic" in result.output.lower()


class TestMetricsAreLiveDuringCapture:
    """add_span promised to update metrics; now it does."""

    def test_counters_update_as_spans_are_added(self):
        c = Cassette(name="live")
        c.add_span(Span(kind=SpanKind.LLM_RESPONSE, model="m", cost_usd=0.01,
                        token_usage=TokenUsage(total_tokens=30), duration_ms=5.0))
        c.add_span(Span(kind=SpanKind.TOOL_CALL, tool_name="t", duration_ms=2.0))
        assert c.llm_call_count == 1
        assert c.tool_call_count == 1
        assert c.total_tokens == 30
        assert c.total_cost_usd == pytest.approx(0.01)
        assert c.total_duration_ms == pytest.approx(7.0)

    def test_incremental_matches_full_recompute(self):
        c = Cassette(name="agree")
        for i in range(5):
            c.add_span(Span(kind=SpanKind.LLM_RESPONSE, model="m", cost_usd=0.001 * i,
                            token_usage=TokenUsage(total_tokens=10 + i), duration_ms=1.0))
            c.add_span(Span(kind=SpanKind.TOOL_CALL, tool_name="t"))
        live = (c.llm_call_count, c.tool_call_count, c.total_tokens, c.total_cost_usd)
        c.compute_metrics()
        assert (c.llm_call_count, c.tool_call_count, c.total_tokens,
                c.total_cost_usd) == pytest.approx(live)

    def test_recompute_is_idempotent(self):
        c = Cassette(name="idem")
        c.add_span(Span(kind=SpanKind.TOOL_CALL, tool_name="t"))
        c.compute_metrics()
        c.compute_metrics()
        assert c.tool_call_count == 1  # never double-counted
