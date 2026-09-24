"""Every top-level example must keep running.

Examples are documentation people copy, so a broken one is a broken promise.
Each runs in a scratch copy (some write cassettes) with no API keys set.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"
SCRIPTS = sorted(p.name for p in EXAMPLES.glob("*.py") if not p.name.startswith("test_"))
PYTEST_EXAMPLES = sorted(p.name for p in EXAMPLES.glob("test_*.py"))


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")}
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


@pytest.fixture
def scratch(tmp_path):
    shutil.copytree(EXAMPLES, tmp_path / "examples",
                    ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


@pytest.mark.parametrize("script", SCRIPTS)
def test_example_script_runs(scratch, script):
    proc = subprocess.run([sys.executable, f"examples/{script}"], cwd=scratch,
                          env=_env(), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]


@pytest.mark.parametrize("module", PYTEST_EXAMPLES)
def test_example_test_module_passes(scratch, module):
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           f"examples/{module}"], cwd=scratch, env=_env(),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]


def test_silent_tool_failure_demo_catches_the_regression(scratch):
    proc = subprocess.run([sys.executable, "examples/silent_tool_failure.py"], cwd=scratch,
                          env=_env(), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = proc.stdout.split("After the model swap", 1)[1]
    assert "[PASS] assert_output_contains" in after       # output-only eval is fooled
    assert "[FAIL] assert_tool_called(lookup_order)" in after
    assert "[FAIL] assert_cost_under" in after


def test_readme_quotes_the_real_example_output(scratch):
    """The README's 'What it catches' block must match what the example prints."""
    readme = (REPO_ROOT / "README.md").read_text()
    block = readme.split("$ python examples/silent_tool_failure.py", 1)[1].split("```", 1)[0]
    quoted = [line.strip() for line in block.splitlines() if line.strip()]
    assert quoted, "README example block not found"
    proc = subprocess.run([sys.executable, "examples/silent_tool_failure.py"], cwd=scratch,
                          env=_env(), capture_output=True, text=True, timeout=60)
    actual = {line.strip() for line in proc.stdout.splitlines()}
    missing = [line for line in quoted if line not in actual]
    assert not missing, f"README shows lines the example no longer prints: {missing}"
