"""Cassette expiry policy: check-stale, [tool.evalcraft] config, and the pytest plugin."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from evalcraft.cli.main import cli
from evalcraft.config import ConfigError, load_config
from evalcraft.core.models import Cassette, Provenance
from evalcraft.regression.detector import Severity
from evalcraft.staleness import StalenessChecker, cassette_age_days, is_expired

REPO_ROOT = Path(__file__).resolve().parent.parent
DAY = 86400


def _aged(days: float, *, provenance: bool = True) -> Cassette:
    c = Cassette(name="aged")
    c.created_at = time.time() - days * DAY
    if provenance:
        c.provenance = Provenance(recorded_at=c.created_at, models=["m"], prompt_hash="h")
    return c


# ── checker ──────────────────────────────────────────────────────────────────

class TestChecker:
    def test_expired_is_critical(self):
        report = StalenessChecker(expire_after_days=90).check(_aged(120))
        finding = next(f for f in report.findings if f.category == "expired")
        assert finding.severity == Severity.CRITICAL
        assert report.has_critical
        assert "re-record" in finding.message.lower()

    def test_within_policy_is_fine(self):
        report = StalenessChecker(expire_after_days=90).check(_aged(10))
        assert not report.has_critical

    def test_legacy_cassette_uses_created_at(self):
        report = StalenessChecker(expire_after_days=90).check(_aged(120, provenance=False))
        assert "expired" in [f.category for f in report.findings]

    def test_age_note_suppressed_when_expired(self):
        cats = [f.category for f in
                StalenessChecker(max_age_days=30, expire_after_days=90).check(_aged(120)).findings]
        assert "expired" in cats and "age" not in cats
        cats = [f.category for f in
                StalenessChecker(max_age_days=30, expire_after_days=90).check(_aged(60)).findings]
        assert "age" in cats and "expired" not in cats

    def test_helpers(self):
        age = cassette_age_days(_aged(120))
        assert age is not None and 119 < age < 121
        assert is_expired(_aged(120), 90) and not is_expired(_aged(120), None)
        future = _aged(-5)
        assert cassette_age_days(future) == 0.0

    def test_millisecond_timestamps(self):
        c = _aged(120, provenance=False)
        c.created_at *= 1000
        age = cassette_age_days(c)
        assert age is not None and 119 < age < 121

    def test_undated_file_has_unknown_age(self, tmp_path):
        c = _aged(400, provenance=False)
        c.save(tmp_path / "c.json")
        data = json.loads((tmp_path / "c.json").read_text())
        del data["cassette"]["created_at"]
        (tmp_path / "c.json").write_text(json.dumps(data))
        loaded = Cassette.load(tmp_path / "c.json")
        assert cassette_age_days(loaded) is None and not is_expired(loaded, 90)
        report = StalenessChecker(expire_after_days=90).check(loaded)
        finding = next(f for f in report.findings if f.category == "unknown_age")
        assert finding.severity == Severity.WARNING
        # Without a policy there is nothing to warn about.
        assert "unknown_age" not in [f.category for f in StalenessChecker().check(loaded).findings]

    def test_zero_timestamp_is_unknown_but_samples_are_exempt(self):
        c = Cassette(name="z", created_at=0.0)
        cats = [f.category for f in StalenessChecker(expire_after_days=90).check(c).findings]
        assert "unknown_age" in cats
        c.metadata = {"sample": True}
        cats = [f.category for f in StalenessChecker(expire_after_days=90).check(c).findings]
        assert "unknown_age" not in cats


# ── config ───────────────────────────────────────────────────────────────────

def _pyproject(directory: Path, body: str) -> Path:
    path = directory / "pyproject.toml"
    path.write_text(body)
    return path


class TestConfig:
    def test_no_file_or_table(self, tmp_path):
        assert load_config(tmp_path).expire_after_days is None
        _pyproject(tmp_path, "[project]\nname = 'x'\n")
        assert load_config(tmp_path).models is None

    def test_values_and_relative_paths(self, tmp_path):
        _pyproject(tmp_path, '[tool.evalcraft]\nexpire_after_days = 90\nmax_age_days = 30\n'
                             'models = "a, b"\ntools = "tests/tools.json"\n')
        sub = tmp_path / "tests"
        sub.mkdir()
        cfg = load_config(sub)  # found by walking up
        assert cfg.expire_after_days == 90 and cfg.max_age_days == 30
        assert cfg.models == ["a", "b"]
        assert cfg.tools == tmp_path / "tests" / "tools.json"

    def test_table_found_above_a_plain_pyproject(self, tmp_path):
        _pyproject(tmp_path, "[tool.evalcraft]\nexpire_after_days = 30\n")
        sub = tmp_path / "pkg"
        sub.mkdir()
        _pyproject(sub, "[project]\nname = 'pkg'\n")
        assert load_config(sub).expire_after_days == 30

    def test_search_stops_at_repository_root(self, tmp_path):
        _pyproject(tmp_path, "[tool.evalcraft]\nexpire_after_days = 30\n")
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        assert load_config(repo).expire_after_days is None

    def test_unknown_keys_are_reported_not_fatal(self, tmp_path):
        _pyproject(tmp_path, "[tool.evalcraft]\nexpire_afer_days = 90\n")
        cfg = load_config(tmp_path)
        assert cfg.expire_after_days is None and cfg.unknown_keys == ["expire_afer_days"]

    @pytest.mark.parametrize("body", [
        "expire_after_days = 0",
        "models = []",
        'models = ""',
        "expire_after_days = true",
        'expire_after_days = "90"',
        "models = [1, 2]",
        "tools = 3",
    ])
    def test_bad_values_raise(self, tmp_path, body):
        _pyproject(tmp_path, f"[tool.evalcraft]\n{body}\n")
        with pytest.raises(ConfigError):
            load_config(tmp_path)

    def test_invalid_toml_raises(self, tmp_path):
        _pyproject(tmp_path, "[tool.evalcraft\n")
        with pytest.raises(ConfigError):
            load_config(tmp_path)


# ── CLI ──────────────────────────────────────────────────────────────────────

class TestCli:
    def test_flag_fails_expired(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _aged(120).save(tmp_path / "old.json")
        result = CliRunner().invoke(cli, ["check-stale", "old.json", "--expire-after-days", "90"])
        assert result.exit_code == 1, result.output
        assert "expired" in result.output

    def test_config_policy_is_used_and_flag_wins(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _pyproject(tmp_path, "[tool.evalcraft]\nexpire_after_days = 90\n")
        _aged(120).save(tmp_path / "old.json")
        assert CliRunner().invoke(cli, ["check-stale", "old.json"]).exit_code == 1
        result = CliRunner().invoke(
            cli, ["check-stale", "old.json", "--expire-after-days", "365"])
        assert result.exit_code == 0, result.output

    def test_config_models_and_tools(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "tools.json").write_text("[]")
        _pyproject(tmp_path, '[tool.evalcraft]\nmodels = ["other"]\ntools = "tools.json"\n')
        _aged(1).save(tmp_path / "c.json")
        result = CliRunner().invoke(cli, ["check-stale", "c.json"])
        assert result.exit_code == 1  # model "m" is not in the configured set
        assert "model_retired" in result.output and "no_tool_definitions" in result.output

    def test_bad_config_is_a_usage_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _pyproject(tmp_path, "[tool.evalcraft]\nexpire_after_days = -1\n")
        _aged(1).save(tmp_path / "c.json")
        result = CliRunner().invoke(cli, ["check-stale", "c.json"])
        assert result.exit_code == 2
        assert "expire_after_days" in result.output

    def test_unknown_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _pyproject(tmp_path, "[tool.evalcraft]\nexpire_after = 90\n")
        _aged(1).save(tmp_path / "c.json")
        result = CliRunner().invoke(cli, ["check-stale", "c.json"])
        assert result.exit_code == 0
        assert "unknown [tool.evalcraft] key(s) ['expire_after']" in result.output

    def test_zero_turns_a_configured_policy_off(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _pyproject(tmp_path, "[tool.evalcraft]\nexpire_after_days = 90\n")
        _aged(120).save(tmp_path / "old.json")
        result = CliRunner().invoke(cli, ["check-stale", "old.json", "--expire-after-days", "0"])
        assert result.exit_code == 0, result.output

    def test_missing_configured_file_is_a_usage_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _pyproject(tmp_path, '[tool.evalcraft]\ntools = "nope.json"\n')
        _aged(1).save(tmp_path / "c.json")
        result = CliRunner().invoke(cli, ["check-stale", "c.json"])
        assert result.exit_code == 2 and "nope.json" in result.output


# ── pytest plugin ────────────────────────────────────────────────────────────

PLUGIN_TESTS = '''
import pytest

@pytest.mark.evalcraft_capture(name="run")
def test_capture(capture_context, mock_llm):
    mock_llm.add_response("*", "{answer}")
    mock_llm.complete("q")

@pytest.mark.evalcraft_cassette("tests/cassettes/run.json")
def test_replay(cassette):
    if cassette is None:
        pytest.skip("recording")
    assert cassette.llm_call_count == 1
'''


def _pytest(project: Path, *args: str, ci: bool = False) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CI"}
    if ci:
        env["CI"] = "true"
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", *args],
        cwd=project, env=env, capture_output=True, text=True, timeout=120,
    )


def _project(tmp_path: Path, answer: str = "v1", policy: str | None = "90") -> Path:
    (tmp_path / "tests" / "cassettes").mkdir(parents=True)
    (tmp_path / "tests" / "test_it.py").write_text(PLUGIN_TESTS.format(answer=answer))
    body = "[tool.pytest.ini_options]\n"
    if policy is not None:
        body += f"\n[tool.evalcraft]\nexpire_after_days = {policy}\n"
    _pyproject(tmp_path, body)
    return tmp_path


def _cassette_path(project: Path) -> Path:
    return project / "tests" / "cassettes" / "run.json"


def _age_file(path: Path, days: float) -> None:
    data = json.loads(path.read_text())
    stamp = time.time() - days * DAY
    data["cassette"]["created_at"] = stamp
    if data["cassette"].get("provenance"):
        data["cassette"]["provenance"]["recorded_at"] = stamp
    path.write_text(json.dumps(data))


def _answer(project: Path) -> str:
    data = json.loads(_cassette_path(project).read_text())
    return next(s["output"] for s in data["spans"] if s.get("output"))


class TestPlugin:
    def _recorded_and_aged(self, tmp_path: Path, **kw) -> Path:
        project = _project(tmp_path, **kw)
        assert _pytest(project, "--evalcraft-record=new").returncode == 0
        _age_file(_cassette_path(project), 120)
        return project

    def test_fresh_cassette_passes_everywhere(self, tmp_path):
        project = _project(tmp_path)
        _pytest(project, "--evalcraft-record=new")
        result = _pytest(project, ci=True)
        assert result.returncode == 0, result.stdout

    def test_expired_warns_locally(self, tmp_path):
        project = self._recorded_and_aged(tmp_path)
        result = _pytest(project)
        assert result.returncode == 0, result.stdout
        assert "EvalcraftExpiredCassetteWarning" in result.stdout
        assert "past the 90-day policy" in result.stdout

    def test_expired_fails_in_ci(self, tmp_path):
        project = self._recorded_and_aged(tmp_path)
        result = _pytest(project, ci=True)
        assert result.returncode != 0
        assert "Cassette expired" in result.stdout

    def test_record_new_refreshes_only_expired(self, tmp_path):
        project = self._recorded_and_aged(tmp_path)
        (project / "tests" / "test_it.py").write_text(PLUGIN_TESTS.format(answer="v2"))
        assert _pytest(project, "--evalcraft-record=new").returncode == 0
        assert _answer(project) == "v2"
        assert cassette_age_days(Cassette.load(_cassette_path(project))) < 1
        assert _pytest(project, ci=True).returncode == 0
        # A fresh cassette is left alone by the next `new` run.
        (project / "tests" / "test_it.py").write_text(PLUGIN_TESTS.format(answer="v3"))
        assert _pytest(project, "--evalcraft-record=new").returncode == 0
        assert _answer(project) == "v2"

    def test_option_overrides_config(self, tmp_path):
        project = self._recorded_and_aged(tmp_path)
        result = _pytest(project, "--evalcraft-expire-after-days", "365", ci=True)
        assert result.returncode == 0, result.stdout

    def test_option_without_config(self, tmp_path):
        project = self._recorded_and_aged(tmp_path, policy=None)
        assert _pytest(project, ci=True).returncode == 0
        assert _pytest(project, "--evalcraft-expire-after-days", "90", ci=True).returncode != 0

    def test_no_policy_never_expires(self, tmp_path):
        project = self._recorded_and_aged(tmp_path, policy=None)
        (project / "tests" / "test_it.py").write_text(PLUGIN_TESTS.format(answer="v2"))
        _pytest(project, "--evalcraft-record=new")
        assert _answer(project) == "v1"

    def test_zero_option_turns_policy_off(self, tmp_path):
        project = self._recorded_and_aged(tmp_path)
        assert _pytest(project, "--evalcraft-expire-after-days", "0", ci=True).returncode == 0

    def test_warns_once_when_both_fixtures_load(self, tmp_path):
        project = self._recorded_and_aged(tmp_path)
        (project / "tests" / "test_both.py").write_text(
            "import pytest\n\n"
            "@pytest.mark.evalcraft_cassette('tests/cassettes/run.json')\n"
            "def test_both(cassette, replay_engine):\n"
            "    assert cassette is not None and replay_engine is not None\n"
        )
        result = _pytest(project, "tests/test_both.py", "-W", "always")
        assert result.returncode == 0, result.stdout
        assert result.stdout.count("EvalcraftExpiredCassetteWarning") == 1
        assert "test_both.py" in result.stdout

    def test_unknown_config_key_warns(self, tmp_path):
        project = _project(tmp_path, policy=None)
        _pyproject(project, "[tool.evalcraft]\nexpire_afer_days = 90\n")
        result = _pytest(project)
        assert result.returncode == 0, result.stdout
        assert "expire_afer_days" in result.stdout + result.stderr

    def test_bad_config_is_reported(self, tmp_path):
        project = self._recorded_and_aged(tmp_path, policy=None)
        _pyproject(project, "[tool.evalcraft]\nexpire_after_days = 0\n")
        result = _pytest(project, ci=True)
        assert result.returncode != 0
        assert "expire_after_days must be a positive integer" in result.stdout + result.stderr
