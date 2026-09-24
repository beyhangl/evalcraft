"""Committed cassettes are only changed on purpose.

A plain ``pytest`` must never rewrite a recording, and in CI a missing
recording must fail rather than skip. Otherwise a test can be made to "pass"
by re-recording or deleting its baseline, which is exactly how coding agents
have been seen getting red suites green. Each case runs real pytest in a
throwaway project.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CAPTURE_TEST = '''
import pytest

@pytest.mark.evalcraft_capture(name="run")
def test_capture(capture_context, mock_llm):
    mock_llm.add_response("*", "{answer}")
    mock_llm.complete("q")
'''

REPLAY_TEST = '''
import pytest

@pytest.mark.evalcraft_cassette("tests/cassettes/missing.json")
def test_replay(cassette):
    assert cassette is not None
'''


def _pytest(project: Path, *args: str, ci: bool = False) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CI"}
    if ci:
        env["CI"] = "true"
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    # These tests rewrite test_it.py between runs, often within the same second
    # and at the same size, which is exactly when a cached .pyc goes stale.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", *args],
        cwd=project, env=env, capture_output=True, text=True, timeout=120,
    )


def _project(tmp_path: Path, body: str) -> Path:
    (tmp_path / "tests" / "cassettes").mkdir(parents=True)
    (tmp_path / "tests" / "test_it.py").write_text(body)
    return tmp_path


def _recorded_answer(project: Path) -> str:
    data = json.loads((project / "tests" / "cassettes" / "run.json").read_text())
    return next(s["output"] for s in data["spans"] if s.get("output"))


class TestRecordModeGovernsWrites:
    def test_plain_pytest_never_writes(self, tmp_path):
        project = _project(tmp_path, CAPTURE_TEST.format(answer="v1"))
        assert _pytest(project).returncode == 0
        assert not (project / "tests" / "cassettes" / "run.json").exists()

    def test_new_writes_missing_but_keeps_existing(self, tmp_path):
        project = _project(tmp_path, CAPTURE_TEST.format(answer="v1"))
        assert _pytest(project, "--evalcraft-record=new").returncode == 0
        assert _recorded_answer(project) == "v1"
        (project / "tests" / "test_it.py").write_text(CAPTURE_TEST.format(answer="v2"))
        assert _pytest(project, "--evalcraft-record=new").returncode == 0
        assert _recorded_answer(project) == "v1"  # existing recording untouched

    def test_all_overwrites(self, tmp_path):
        project = _project(tmp_path, CAPTURE_TEST.format(answer="v1"))
        _pytest(project, "--evalcraft-record=new")
        (project / "tests" / "test_it.py").write_text(CAPTURE_TEST.format(answer="v2"))
        assert _pytest(project, "--evalcraft-record=all").returncode == 0
        assert _recorded_answer(project) == "v2"


class TestMissingCassette:
    def test_skips_locally(self, tmp_path):
        proc = _pytest(_project(tmp_path, REPLAY_TEST))
        assert proc.returncode == 0 and "1 skipped" in proc.stdout

    def test_fails_in_ci(self, tmp_path):
        proc = _pytest(_project(tmp_path, REPLAY_TEST), ci=True)
        # Raised during fixture setup, so pytest reports an error; CI goes red.
        assert proc.returncode != 0
        assert "skipped" not in proc.stdout.splitlines()[-1]
        assert "missing cassettes fail in CI" in proc.stdout

    def test_ci_can_opt_back_into_skip(self, tmp_path):
        proc = _pytest(_project(tmp_path, REPLAY_TEST), "--evalcraft-missing=skip", ci=True)
        assert proc.returncode == 0 and "1 skipped" in proc.stdout

    def test_local_can_opt_into_fail(self, tmp_path):
        proc = _pytest(_project(tmp_path, REPLAY_TEST), "--evalcraft-missing=fail")
        assert proc.returncode == 1

    def test_ci_false_is_not_ci(self, tmp_path):
        project = _project(tmp_path, REPLAY_TEST)
        env = {**os.environ, "CI": "false",
               "PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")}
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                              cwd=project, env=env, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0 and "1 skipped" in proc.stdout
