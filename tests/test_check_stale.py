"""Tests for staleness detection (evalcraft check-stale).

Covers the StalenessChecker logic + the CLI gate, and — critically — that the
recomputed prompt hash matches what capture_provenance recorded (the hash-parity
refactor in core/models.py).
"""

import json
import time

from click.testing import CliRunner

from evalcraft.cli.main import cli
from evalcraft.core.models import Cassette, Provenance, Span, SpanKind, compute_prompt_hash
from evalcraft.regression.detector import Severity
from evalcraft.staleness import StalenessChecker, hash_prompts_file


def _cassette_with_provenance(models, *, prompt_hash="abc1234567890def", recorded_at=None):
    c = Cassette(name="prov_cass")
    c.provenance = Provenance(
        recorded_at=recorded_at if recorded_at is not None else time.time(),
        sdk_version="0.2.1",
        python_version="3.10",
        models=list(models),
        prompt_hash=prompt_hash,
    )
    return c


def _save(tmp_path, name, models, *, prompt_hash="abc1234567890def", recorded_at=None):
    c = _cassette_with_provenance(models, prompt_hash=prompt_hash, recorded_at=recorded_at)
    c.name = name
    path = tmp_path / f"{name}.json"
    c.save(path)
    return path


# ── StalenessChecker ─────────────────────────────────────────────────────────

def test_no_provenance_emits_info_finding():
    report = StalenessChecker().check(Cassette(name="legacy"))  # provenance None
    assert len(report.findings) == 1
    assert report.findings[0].category == "no_provenance"
    assert report.findings[0].severity == Severity.INFO
    assert report.has_critical is False


def test_retired_model_is_critical():
    report = StalenessChecker().check(
        _cassette_with_provenance(["gpt-4o"]), current_models=["gpt-5.1"]
    )
    assert report.has_critical
    finding = next(f for f in report.findings if f.category == "model_retired")
    assert finding.severity == Severity.CRITICAL
    assert finding.recorded_value == "gpt-4o"


def test_model_present_no_finding():
    report = StalenessChecker().check(
        _cassette_with_provenance(["gpt-5.1"]),
        current_models=["gpt-5.1", "claude-sonnet-4-5"],
    )
    assert not any(f.category == "model_retired" for f in report.findings)
    assert not report.has_critical


def test_prompt_drift_is_warning():
    report = StalenessChecker().check(
        _cassette_with_provenance([], prompt_hash="recordedhash0001"),
        current_prompt_hash="differenthash999",
    )
    finding = next(f for f in report.findings if f.category == "prompt_drift")
    assert finding.severity == Severity.WARNING


def test_prompt_hash_match_no_finding(tmp_path):
    # Build a cassette via capture_provenance so the recorded hash is "real".
    c = Cassette(name="m")
    c.input_text = "hi"
    c.add_span(Span(kind=SpanKind.LLM_RESPONSE, model="gpt-5.1", input="hi", output="yo"))
    c.capture_provenance()
    recorded = c.provenance.prompt_hash

    prompts = tmp_path / "prompts.json"
    prompts.write_text(json.dumps({"input_text": "hi", "llm_inputs": ["hi"]}))
    current = hash_prompts_file(prompts)
    assert current == recorded  # hash parity holds

    report = StalenessChecker().check(c, current_prompt_hash=current)
    assert not any(f.category == "prompt_drift" for f in report.findings)


def test_recompute_matches_capture_provenance():
    c = Cassette(name="m")
    c.input_text = "what is 2+2?"
    c.add_span(Span(kind=SpanKind.LLM_RESPONSE, model="gpt-5.1", input="what is 2+2?", output="4"))
    prov = c.capture_provenance()
    assert compute_prompt_hash("what is 2+2?", ["what is 2+2?"]) == prov.prompt_hash


def test_age_over_threshold_is_info():
    old = time.time() - 40 * 86400
    report = StalenessChecker(max_age_days=30).check(_cassette_with_provenance([], recorded_at=old))
    finding = next(f for f in report.findings if f.category == "age")
    assert finding.severity == Severity.INFO


def test_age_within_threshold_no_finding():
    report = StalenessChecker(max_age_days=30).check(
        _cassette_with_provenance([], recorded_at=time.time())
    )
    assert not any(f.category == "age" for f in report.findings)


def test_report_to_dict_shape_and_severity_strings():
    report = StalenessChecker().check(
        _cassette_with_provenance(["gpt-4o"]), current_models=["gpt-5.1"]
    )
    d = report.to_dict()
    assert set(d) >= {
        "cassette_name", "has_findings", "has_critical",
        "finding_count", "max_severity", "findings",
    }
    assert d["has_critical"] is True
    assert d["max_severity"] == "CRITICAL"
    assert d["findings"][0]["severity"] in {"CRITICAL", "WARNING", "INFO"}


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_check_stale_exit_1_on_critical(tmp_path):
    path = _save(tmp_path, "retired", ["gpt-4o"])
    result = CliRunner().invoke(cli, ["check-stale", str(path), "--models", "gpt-5.1"])
    assert result.exit_code == 1, result.output
    assert "model_retired" in result.output


def test_cli_check_stale_json_output(tmp_path):
    path = _save(tmp_path, "retired", ["gpt-4o"])
    result = CliRunner().invoke(cli, ["check-stale", str(path), "--models", "gpt-5.1", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert "cassettes" in data
    assert data["cassettes"][0]["has_critical"] is True


def test_cli_multiple_cassettes_aggregate_exit(tmp_path):
    good = _save(tmp_path, "good", ["gpt-5.1"])
    bad = _save(tmp_path, "bad", ["gpt-4o"])
    result = CliRunner().invoke(cli, ["check-stale", str(good), str(bad), "--models", "gpt-5.1"])
    assert result.exit_code == 1
    assert "good" in result.output and "bad" in result.output


def test_cli_no_options_falls_back_to_age_and_noprov(tmp_path):
    path = tmp_path / "legacy.json"
    Cassette(name="legacy").save(path)  # no provenance
    result = CliRunner().invoke(cli, ["check-stale", str(path)])
    assert result.exit_code == 0, result.output
    assert "no_provenance" in result.output
