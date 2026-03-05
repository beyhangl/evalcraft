"""tests/test_code_review_agent.py — Tests for the Claude-powered code review agent.

Covers:
- Correct tool sequence (fetch diff → lint → coverage check → synthesize)
- Security findings are surfaced in the review
- Approvals vs. change requests are appropriate
- Cost and token budgets
- Multi-turn behavior validation
- Mock-based unit tests

Run:
    pytest tests/ -v
"""

from __future__ import annotations

from pathlib import Path
import pytest
from evalcraft import (
    replay,
    assert_tool_called,
    assert_tool_order,
    assert_output_contains,
    assert_output_matches,
    assert_cost_under,
    assert_token_count_under,
)
from evalcraft.eval.scorers import Evaluator

_HERE = Path(__file__).parent

CASSETTES = {
    "auth": str(_HERE / "cassettes" / "auth_middleware_review.json"),
    "db_pool": str(_HERE / "cassettes" / "db_pool_refactor_review.json"),
}


# ---------------------------------------------------------------------------
# Tool sequence validation
# ---------------------------------------------------------------------------

class TestToolSequence:
    """The agent must always fetch the diff before running other checks."""

    def test_auth_pr_fetches_diff_first(self):
        run = replay(CASSETTES["auth"])
        result = assert_tool_called(run, "fetch_pr_diff", before="run_lint_check")
        assert result.passed, result.message

    def test_auth_pr_runs_lint_check(self):
        run = replay(CASSETTES["auth"])
        result = assert_tool_called(run, "run_lint_check")
        assert result.passed, result.message

    def test_auth_pr_checks_test_coverage(self):
        run = replay(CASSETTES["auth"])
        result = assert_tool_called(run, "check_test_coverage")
        assert result.passed, result.message

    def test_auth_pr_full_sequence(self):
        run = replay(CASSETTES["auth"])
        result = assert_tool_order(
            run,
            ["fetch_pr_diff", "run_lint_check", "check_test_coverage"],
            strict=False,
        )
        assert result.passed, result.message

    def test_db_pool_fetches_diff(self):
        run = replay(CASSETTES["db_pool"])
        result = assert_tool_called(run, "fetch_pr_diff", with_args={"pr_number": 102})
        assert result.passed, result.message

    def test_db_pool_full_sequence(self):
        run = replay(CASSETTES["db_pool"])
        result = assert_tool_order(
            run,
            ["fetch_pr_diff", "run_lint_check", "check_test_coverage"],
        )
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# Security review quality
# ---------------------------------------------------------------------------

class TestSecurityReview:
    """Auth middleware review must flag the hardcoded secret as critical."""

    def test_flags_hardcoded_secret(self):
        run = replay(CASSETTES["auth"])
        output = run.cassette.output_text.lower()
        assert "hardcoded" in output or "secret" in output, (
            f"Review did not mention hardcoded secret.\nGot: {run.cassette.output_text[:300]}"
        )

    def test_recommends_change(self):
        """Must recommend changes, not approve."""
        run = replay(CASSETTES["auth"])
        output = run.cassette.output_text.upper()
        assert "REQUEST CHANGES" in output or "CHANGES" in output, (
            "Review should request changes for the security-critical PR."
        )

    def test_mentions_line_number_or_code(self):
        run = replay(CASSETTES["auth"])
        # Match "Line 6", "line 6", backtick-quoted code, or rule IDs
        result = assert_output_matches(run, r"(?i)line \d+|`SECRET_KEY`|S2068|hardcoded")
        assert result.passed, (
            "Review should reference the specific issue location."
        )

    def test_mentions_missing_tests(self):
        run = replay(CASSETTES["auth"])
        output = run.cassette.output_text.lower()
        assert "test" in output, (
            "Review should mention missing tests for security-critical code."
        )


# ---------------------------------------------------------------------------
# Clean code review
# ---------------------------------------------------------------------------

class TestCleanRefactorReview:
    """The DB pool refactor has no critical issues — agent should approve."""

    def test_approves_clean_pr(self):
        run = replay(CASSETTES["db_pool"])
        result = assert_output_contains(run, "APPROVE", case_sensitive=False)
        assert result.passed, result.message

    def test_does_not_raise_critical_findings(self):
        """For a clean PR the review must not raise any critical severity findings.

        The phrase 'No critical ... issues detected' is fine (it's a negative statement).
        What we want to ensure is that no '**CRITICAL:**' finding header is present.
        """
        run = replay(CASSETTES["db_pool"])
        output = run.cassette.output_text
        import re
        # A raised CRITICAL finding looks like "**CRITICAL:" or "CRITICAL: <issue>"
        critical_finding = re.search(r"\*\*CRITICAL:", output, re.IGNORECASE)
        assert critical_finding is None, (
            "Clean refactor should not raise any CRITICAL findings.\n"
            f"Found: {critical_finding.group() if critical_finding else ''}\n"
            f"Output: {output[:300]}"
        )

    def test_mentions_env_vars(self):
        run = replay(CASSETTES["db_pool"])
        result = assert_output_contains(run, "environment variable", case_sensitive=False)
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# Budget assertions
# ---------------------------------------------------------------------------

class TestBudgets:

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_cost_under_budget(self, scenario, cassette):
        run = replay(cassette)
        result = assert_cost_under(run, max_usd=0.05)
        assert result.passed, f"[{scenario}] {result.message}"

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_token_count_reasonable(self, scenario, cassette):
        run = replay(cassette)
        result = assert_token_count_under(run, max_tokens=5000)
        assert result.passed, f"[{scenario}] {result.message}"

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_multiple_llm_turns(self, scenario, cassette):
        """Code review agent should use at least 2 LLM turns (tool call + synthesis)."""
        run = replay(cassette)
        assert run.cassette.llm_call_count >= 2, (
            f"[{scenario}] Expected multi-turn review (>=2 LLM calls), "
            f"got {run.cassette.llm_call_count}"
        )


# ---------------------------------------------------------------------------
# Composite evaluator
# ---------------------------------------------------------------------------

def test_auth_review_composite_eval():
    run = replay(CASSETTES["auth"])

    result = (
        Evaluator()
        .add(assert_tool_called, run, "fetch_pr_diff")
        .add(assert_tool_called, run, "run_lint_check")
        .add(assert_tool_called, run, "check_test_coverage")
        .add(assert_cost_under, run, max_usd=0.05)
        .run()
    )

    assert result.passed, (
        f"Composite eval failed (score={result.score:.0%}):\n"
        + "\n".join(
            f"  FAIL: {a.name} — {a.message}"
            for a in result.assertions
            if not a.passed
        )
    )


# ---------------------------------------------------------------------------
# Mock-based multi-turn test
# ---------------------------------------------------------------------------

def test_multi_turn_with_mocks():
    """Test multi-turn agent logic without any Anthropic API calls."""
    from evalcraft import CaptureContext, MockLLM, MockTool

    # Mock the tools
    diff_tool = MockTool("fetch_pr_diff")
    diff_tool.returns({
        "title": "Fix SQL injection vulnerability",
        "files_changed": 1,
        "additions": 5,
        "deletions": 3,
        "diff": '-query = f"SELECT * FROM users WHERE id = {user_id}"\n+query = "SELECT * FROM users WHERE id = ?"\n+cursor.execute(query, (user_id,))',
    })

    lint_tool = MockTool("run_lint_check")
    lint_tool.returns({
        "language": "python",
        "issues": [],
        "issue_count": 0,
        "passed": True,
    })

    coverage_tool = MockTool("check_test_coverage")
    coverage_tool.returns({
        "has_tests": True,
        "test_files_changed": 1,
        "coverage_delta": 3.5,
        "warning": None,
    })

    # First LLM turn: decides to call tools
    # Second LLM turn: writes review based on tool results
    llm = MockLLM(model="claude-3-5-haiku-20241022")
    llm.add_sequential_responses(
        "*",
        [
            "I'll fetch the PR diff and run checks.",  # turn 1 — tool planning
            "## Code Review: Fix SQL Injection\n\n### Verdict\n**APPROVE** — "
            "Excellent fix. The parameterized query correctly prevents SQL injection.",  # turn 2 — final review
        ],
    )

    with CaptureContext(
        name="mock_multi_turn_review",
        agent_name="code_review_agent",
        framework="anthropic",
    ) as ctx:
        ctx.record_input("Review PR #999 — Fix SQL injection")

        # Simulate turn 1: LLM decides to call tools
        turn1 = llm.complete("Review PR #999 in myorg/backend")

        # Execute tools
        diff = diff_tool.call(repo="myorg/backend", pr_number=999)
        lint = lint_tool.call(code_snippet=diff.get("diff", ""))
        coverage = coverage_tool.call(repo="myorg/backend", pr_number=999)

        # Simulate turn 2: LLM synthesizes
        context = f"Diff: {diff}\nLint: {lint}\nCoverage: {coverage}"
        turn2 = llm.complete(context)

        ctx.record_output(turn2.content)

    # Verify tool calls
    diff_tool.assert_called(times=1)
    lint_tool.assert_called(times=1)
    coverage_tool.assert_called(times=1)
    llm.assert_called(times=2)

    # Verify cassette
    cassette = ctx.cassette
    assert cassette.tool_call_count == 3
    assert cassette.llm_call_count == 2
    assert "APPROVE" in cassette.output_text
    assert "SQL" in cassette.output_text
