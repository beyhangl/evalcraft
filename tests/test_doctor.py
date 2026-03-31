"""Tests for evalcraft.cli.doctor_cmd."""

from __future__ import annotations

from evalcraft.cli.doctor_cmd import run_doctor


class TestDoctor:
    def test_runs_without_error(self, capsys):
        """Doctor should run and produce output without crashing."""
        result = run_doctor(cassette_dir="tests/cassettes")
        captured = capsys.readouterr()

        # Should print something
        assert "evalcraft doctor" in captured.out
        assert "passed" in captured.out

    def test_detects_evalcraft_installed(self, capsys):
        result = run_doctor()
        captured = capsys.readouterr()
        assert "evalcraft" in captured.out

    def test_detects_python_version(self, capsys):
        run_doctor()
        captured = capsys.readouterr()
        assert "Python" in captured.out

    def test_detects_pytest(self, capsys):
        run_doctor()
        captured = capsys.readouterr()
        assert "pytest" in captured.out

    def test_warns_on_missing_cassette_dir(self, capsys):
        run_doctor(cassette_dir="nonexistent/path")
        captured = capsys.readouterr()
        assert "not found" in captured.out or "warning" in captured.out.lower()

    def test_returns_bool(self):
        result = run_doctor()
        assert isinstance(result, bool)
