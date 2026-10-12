"""Tests for evalcraft.cli.doctor_cmd."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

from evalcraft.cli.doctor_cmd import run_doctor


class TestDoctor:
    def test_runs_without_error(self, capsys):
        """Doctor should run and produce output without crashing."""
        run_doctor(cassette_dir="tests/cassettes")
        captured = capsys.readouterr()

        # Should print something
        assert "evalcraft doctor" in captured.out
        assert "passed" in captured.out

    def test_detects_evalcraft_installed(self, capsys):
        run_doctor()
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

    def test_detects_current_google_genai_sdk(self, monkeypatch, capsys):
        original = importlib.import_module
        imports = []

        def fake_import(name, *args, **kwargs):
            imports.append(name)
            if name == "google.genai":
                return SimpleNamespace(__version__="test-sdk")
            return original(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", fake_import)
        run_doctor(cassette_dir="nonexistent/path")
        assert "google-genai test-sdk" in capsys.readouterr().out
        assert "google.genai" in imports
        assert "google.generativeai" not in imports

    def test_missing_google_genai_install_hint(self, monkeypatch, capsys):
        original = importlib.import_module

        def fake_import(name, *args, **kwargs):
            if name == "google.genai":
                raise ImportError("optional SDK absent")
            return original(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", fake_import)
        run_doctor(cassette_dir="nonexistent/path")
        output = capsys.readouterr().out
        assert (
            'google-genai not installed — install with: pip install "evalcraft[gemini]"' in output
        )
