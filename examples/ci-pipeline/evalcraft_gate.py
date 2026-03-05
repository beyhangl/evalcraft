"""evalcraft_gate.py — A standalone CI gate script for agent quality.

This script runs a complete evaluation suite against pre-recorded cassettes
and exits with a non-zero code if any checks fail. Use it as a drop-in step
in any CI system (GitHub Actions, GitLab CI, CircleCI, Jenkins, etc.).

Usage:
    python evalcraft_gate.py                          # run all checks
    python evalcraft_gate.py --only cost              # run cost checks only
    python evalcraft_gate.py --cassettes path/to/     # custom cassette dir
    python evalcraft_gate.py --json-output results.json

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
    2 — configuration/import error
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Check result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    cassette: str
    passed: bool
    message: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class GateReport:
    passed: bool
    total: int
    passed_count: int
    failed_count: int
    duration_s: float
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.passed_count / self.total if self.total > 0 else 1.0


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def check_tool_sequence(cassette, expected_tools: list[str]) -> tuple[bool, str]:
    """Verify the agent called the expected tools in the expected order."""
    from evalcraft import assert_tool_order
    result = assert_tool_order(cassette, expected_tools, strict=False)
    return result.passed, result.message


def check_cost(cassette, max_usd: float) -> tuple[bool, str]:
    """Verify the run stayed within cost budget."""
    from evalcraft import assert_cost_under
    result = assert_cost_under(cassette, max_usd=max_usd)
    return result.passed, result.message


def check_tokens(cassette, max_tokens: int) -> tuple[bool, str]:
    """Verify the run stayed within token budget."""
    from evalcraft import assert_token_count_under
    result = assert_token_count_under(cassette, max_tokens=max_tokens)
    return result.passed, result.message


def check_output_keyword(cassette, keyword: str) -> tuple[bool, str]:
    """Verify the output contains an expected keyword."""
    from evalcraft import assert_output_contains
    result = assert_output_contains(cassette, keyword, case_sensitive=False)
    return result.passed, result.message


def check_tool_called(cassette, tool_name: str) -> tuple[bool, str]:
    """Verify a specific tool was called."""
    from evalcraft import assert_tool_called
    result = assert_tool_called(cassette, tool_name)
    return result.passed, result.message


# ---------------------------------------------------------------------------
# Check suite definition
# ---------------------------------------------------------------------------

# Each entry: (check_function, kwargs, cassette_path, human_readable_name)
# Customize this to match your agent's requirements.
CHECKS: list[tuple] = [
    # --- Support agent: order tracking ---
    (
        check_tool_called,
        {"tool_name": "lookup_order"},
        "../openai-agent/tests/cassettes/order_tracking.json",
        "support_agent:order_tracking:calls_lookup_order",
    ),
    (
        check_tool_called,
        {"tool_name": "search_knowledge_base"},
        "../openai-agent/tests/cassettes/order_tracking.json",
        "support_agent:order_tracking:calls_knowledge_base",
    ),
    (
        check_cost,
        {"max_usd": 0.01},
        "../openai-agent/tests/cassettes/order_tracking.json",
        "support_agent:order_tracking:cost_budget",
    ),
    (
        check_tokens,
        {"max_tokens": 1500},
        "../openai-agent/tests/cassettes/order_tracking.json",
        "support_agent:order_tracking:token_budget",
    ),
    (
        check_output_keyword,
        {"keyword": "UPS"},
        "../openai-agent/tests/cassettes/order_tracking.json",
        "support_agent:order_tracking:output_has_carrier",
    ),

    # --- Support agent: return request ---
    (
        check_tool_called,
        {"tool_name": "lookup_order"},
        "../openai-agent/tests/cassettes/return_request.json",
        "support_agent:return_request:calls_lookup_order",
    ),
    (
        check_cost,
        {"max_usd": 0.01},
        "../openai-agent/tests/cassettes/return_request.json",
        "support_agent:return_request:cost_budget",
    ),

    # --- Code review agent: auth middleware ---
    (
        check_tool_sequence,
        {"expected_tools": ["fetch_pr_diff", "run_lint_check"]},
        "../anthropic-agent/tests/cassettes/auth_middleware_review.json",
        "code_review:auth:tool_sequence",
    ),
    (
        check_output_keyword,
        {"keyword": "hardcoded"},
        "../anthropic-agent/tests/cassettes/auth_middleware_review.json",
        "code_review:auth:flags_hardcoded_secret",
    ),
    (
        check_cost,
        {"max_usd": 0.05},
        "../anthropic-agent/tests/cassettes/auth_middleware_review.json",
        "code_review:auth:cost_budget",
    ),

    # --- Code review agent: DB pool ---
    (
        check_output_keyword,
        {"keyword": "approve"},
        "../anthropic-agent/tests/cassettes/db_pool_refactor_review.json",
        "code_review:db_pool:approves_clean_pr",
    ),
    (
        check_cost,
        {"max_usd": 0.05},
        "../anthropic-agent/tests/cassettes/db_pool_refactor_review.json",
        "code_review:db_pool:cost_budget",
    ),

    # --- LangGraph RAG pipeline ---
    (
        check_output_keyword,
        {"keyword": "3 days"},
        "../langgraph-workflow/tests/cassettes/remote_work_policy.json",
        "rag:remote_work:answer_accuracy",
    ),
    (
        check_output_keyword,
        {"keyword": "800"},
        "../langgraph-workflow/tests/cassettes/equipment_stipend.json",
        "rag:equipment:answer_accuracy",
    ),
    (
        check_cost,
        {"max_usd": 0.05},
        "../langgraph-workflow/tests/cassettes/remote_work_policy.json",
        "rag:remote_work:cost_budget",
    ),
]


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------

def run_gate(
    checks: list[tuple],
    base_dir: Path,
    only: str | None = None,
    verbose: bool = True,
) -> GateReport:
    """Run all checks and return a GateReport."""
    try:
        from evalcraft import replay
        from evalcraft.core.models import Cassette
    except ImportError:
        print("ERROR: evalcraft is not installed. Run: pip install evalcraft")
        sys.exit(2)

    start = time.monotonic()
    results: list[CheckResult] = []

    # Cache loaded cassettes to avoid re-reading files
    _cassette_cache: dict[str, Any] = {}

    for check_fn, kwargs, cassette_rel_path, check_name in checks:
        if only and only not in check_name:
            continue

        cassette_path = (base_dir / cassette_rel_path).resolve()

        if not cassette_path.exists():
            results.append(CheckResult(
                name=check_name,
                cassette=str(cassette_rel_path),
                passed=False,
                message=f"Cassette file not found: {cassette_path}",
            ))
            if verbose:
                print(f"  [SKIP] {check_name}: cassette not found")
            continue

        # Load and cache cassette
        if str(cassette_path) not in _cassette_cache:
            try:
                run = replay(cassette_path)
                _cassette_cache[str(cassette_path)] = run.cassette
            except Exception as e:
                results.append(CheckResult(
                    name=check_name,
                    cassette=str(cassette_rel_path),
                    passed=False,
                    message=f"Failed to load cassette: {e}",
                ))
                continue

        cassette = _cassette_cache[str(cassette_path)]

        try:
            passed, message = check_fn(cassette, **kwargs)
        except Exception as e:
            passed, message = False, f"Check raised exception: {e}"

        result = CheckResult(
            name=check_name,
            cassette=str(cassette_rel_path),
            passed=passed,
            message=message,
        )
        results.append(result)

        if verbose:
            icon = "PASS" if passed else "FAIL"
            line = f"  [{icon}] {check_name}"
            if not passed and message:
                line += f"\n         {message}"
            print(line)

    duration = time.monotonic() - start
    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count

    return GateReport(
        passed=failed_count == 0,
        total=len(results),
        passed_count=passed_count,
        failed_count=failed_count,
        duration_s=duration,
        checks=results,
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evalcraft CI gate — run eval checks against cassettes."
    )
    parser.add_argument(
        "--only",
        metavar="FILTER",
        help="Only run checks whose name contains FILTER (e.g. 'cost', 'rag')",
    )
    parser.add_argument(
        "--json-output",
        metavar="PATH",
        help="Write full report to a JSON file",
    )
    parser.add_argument(
        "--base-dir",
        metavar="DIR",
        default=str(Path(__file__).parent),
        help="Base directory for resolving relative cassette paths",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-check output")
    args = parser.parse_args()

    base_dir = Path(args.base_dir)

    print("=" * 60)
    print("evalcraft CI Gate")
    print("=" * 60)
    print()

    report = run_gate(
        checks=CHECKS,
        base_dir=base_dir,
        only=args.only,
        verbose=not args.quiet,
    )

    print()
    print("=" * 60)
    status = "PASSED" if report.passed else "FAILED"
    print(f"Result:  {status}")
    print(f"Checks:  {report.passed_count}/{report.total} passed")
    print(f"Score:   {report.score:.0%}")
    print(f"Time:    {report.duration_s:.2f}s")
    print("=" * 60)

    if args.json_output:
        out_path = Path(args.json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        report_dict = {
            "passed": report.passed,
            "total": report.total,
            "passed_count": report.passed_count,
            "failed_count": report.failed_count,
            "score": report.score,
            "duration_s": report.duration_s,
            "checks": [
                {
                    "name": r.name,
                    "cassette": r.cassette,
                    "passed": r.passed,
                    "message": r.message,
                }
                for r in report.checks
            ],
        }
        out_path.write_text(json.dumps(report_dict, indent=2))
        print(f"Report:  {out_path}")

    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
