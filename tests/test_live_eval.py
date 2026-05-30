"""Tests for live-eval mode (issue #20).

Uses fake runners (no real model calls) to exercise the scoring, comparison,
serialization, and CLI-gating logic deterministically.
"""

from click.testing import CliRunner

from evalcraft import assert_output_contains
from evalcraft.cli.main import cli
from evalcraft.core.models import AgentRun, Cassette
from evalcraft.eval.live import (
    LiveCaseResult,
    LiveEvalCase,
    LiveEvalResult,
    compare_to_baseline,
    run_live_eval,
)


def _result(scores: dict) -> LiveEvalResult:
    return LiveEvalResult(
        cases=[LiveCaseResult(name=n, passed=s >= 1.0, score=s) for n, s in scores.items()]
    )


# ── run_live_eval ────────────────────────────────────────────────────────────

class TestRunLiveEval:
    def test_scores_cases(self):
        cases = [
            LiveEvalCase(
                name="a", input="q-a",
                scorers=[lambda c: assert_output_contains(c, "Paris")],
            ),
            LiveEvalCase(
                name="b", input="q-b",
                scorers=[lambda c: assert_output_contains(c, "London")],
            ),
        ]
        outputs = {"a": "It is sunny in Paris", "b": "It is rainy in Berlin"}  # b fails
        result = run_live_eval(cases, lambda case: outputs[case.name])
        assert result.n == 2
        assert result.scores() == {"a": 1.0, "b": 0.0}
        assert result.pass_rate == 0.5
        assert result.passed is False

    def test_partial_scorers_give_fractional_score(self):
        case = LiveEvalCase(
            name="x", input="q",
            scorers=[
                lambda c: assert_output_contains(c, "alpha"),
                lambda c: assert_output_contains(c, "omega"),
            ],
        )
        result = run_live_eval([case], lambda case: "alpha only")
        assert result.cases[0].score == 0.5
        assert result.cases[0].passed is False

    def test_runner_exception_fails_case(self):
        case = LiveEvalCase(name="x", input="q", scorers=[lambda c: assert_output_contains(c, "z")])

        def boom(case):
            raise RuntimeError("model down")

        result = run_live_eval([case], boom)
        assert result.cases[0].score == 0.0
        assert result.cases[0].passed is False
        assert "model down" in (result.cases[0].error or "")

    def test_scorer_exception_handled(self):
        def bad_scorer(c):
            raise ValueError("oops")

        case = LiveEvalCase(name="x", input="q", scorers=[bad_scorer])
        result = run_live_eval([case], lambda case: "out")
        assert result.cases[0].passed is False
        assert any("scorer error" in a.message for a in result.cases[0].assertions)

    def test_runner_can_return_cassette_or_agentrun(self):
        cassette = Cassette(name="r")
        cassette.output_text = "hello Paris"
        cases = [
            LiveEvalCase(
                name="cass", input="q",
                scorers=[lambda c: assert_output_contains(c, "Paris")],
            ),
            LiveEvalCase(
                name="run", input="q",
                scorers=[lambda c: assert_output_contains(c, "Paris")],
            ),
        ]

        def runner(case):
            return cassette if case.name == "cass" else AgentRun(cassette=cassette)

        assert run_live_eval(cases, runner).passed is True

    def test_no_scorers_counts_as_pass(self):
        result = run_live_eval([LiveEvalCase(name="x", input="q")], lambda case: "anything")
        assert result.cases[0].passed is True
        assert result.cases[0].score == 1.0


# ── compare_to_baseline ──────────────────────────────────────────────────────

class TestCompareToBaseline:
    def test_detects_regression(self):
        comparison = compare_to_baseline(
            _result({"a": 1.0, "b": 0.0}), _result({"a": 1.0, "b": 1.0})
        )
        assert comparison.passed is False
        assert [d.name for d in comparison.regressions] == ["b"]

    def test_max_drop_tolerance(self):
        base, cur = _result({"a": 1.0}), _result({"a": 0.9})
        assert compare_to_baseline(cur, base, max_score_drop=0.2).passed is True
        assert compare_to_baseline(cur, base, max_score_drop=0.0).passed is False

    def test_improvement_new_and_removed(self):
        comparison = compare_to_baseline(
            _result({"a": 1.0, "new": 1.0}), _result({"a": 0.5, "removed": 1.0})
        )
        assert [d.name for d in comparison.improvements] == ["a"]
        assert comparison.new_cases == ["new"]
        assert comparison.removed_cases == ["removed"]
        assert comparison.passed is True  # a new case is never a regression

    def test_accepts_dict_baseline(self):
        assert compare_to_baseline(_result({"a": 0.0}), {"a": 1.0}).passed is False


# ── serialization ────────────────────────────────────────────────────────────

def test_result_roundtrip(tmp_path):
    r = _result({"a": 1.0, "b": 0.0})
    assert LiveEvalResult.from_dict(r.to_dict()).scores() == {"a": 1.0, "b": 0.0}
    path = tmp_path / "r.json"
    r.save(path)
    assert LiveEvalResult.load(path).scores() == {"a": 1.0, "b": 0.0}


# ── CLI gate ─────────────────────────────────────────────────────────────────

def test_cli_live_eval_gates(tmp_path):
    base_path = tmp_path / "base.json"
    good_path = tmp_path / "good.json"
    bad_path = tmp_path / "bad.json"
    _result({"a": 1.0, "b": 1.0}).save(base_path)
    _result({"a": 1.0, "b": 1.0}).save(good_path)
    _result({"a": 1.0, "b": 0.0}).save(bad_path)

    runner = CliRunner()
    ok = runner.invoke(cli, ["live-eval", str(good_path), "--baseline", str(base_path)])
    assert ok.exit_code == 0, ok.output

    fail = runner.invoke(cli, ["live-eval", str(bad_path), "--baseline", str(base_path)])
    assert fail.exit_code == 1
    assert "regress" in fail.output.lower()
