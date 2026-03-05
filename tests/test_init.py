"""Tests for evalcraft init — scaffold command.

Tests:
    - scaffold_project() function (unit-level, no CLI)
    - CLI command via Click test runner
    - Interactive prompt mode
    - Non-interactive --framework flag
    - All 5 frameworks
    - File content validation
    - Overwrite flag
    - Skip-existing behaviour
    - Error handling (invalid framework, missing template)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from evalcraft.cli.init_cmd import FRAMEWORKS, scaffold_project
from evalcraft.cli.main import cli


# ─── helpers ──────────────────────────────────────────────────────────────────


def _run_init(runner: CliRunner, args: list[str]) -> object:
    """Invoke `evalcraft init` via the Click test runner."""
    return runner.invoke(cli, ["init", *args], catch_exceptions=False)


# ─── scaffold_project — unit tests ────────────────────────────────────────────


class TestScaffoldProject:
    """Unit tests for scaffold_project() without invoking the CLI."""

    def test_creates_all_four_artifacts(self, tmp_path):
        """scaffold_project creates test file, cassettes dir, toml, conftest."""
        results = scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )

        expected_keys = {
            "tests/test_agent.py",
            "tests/cassettes/.gitkeep",
            "evalcraft.toml",
            "conftest.py",
        }
        assert set(results.keys()) == expected_keys

    def test_all_files_written_first_run(self, tmp_path):
        """All results are True (written) on a fresh project directory."""
        results = scaffold_project(
            framework="openai",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        assert all(results.values()), f"Some files not written: {results}"

    def test_files_exist_on_disk_after_scaffold(self, tmp_path):
        """All four generated files actually exist on disk."""
        scaffold_project(
            framework="anthropic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        assert (tmp_path / "tests" / "test_agent.py").exists()
        assert (tmp_path / "tests" / "cassettes").is_dir()
        assert (tmp_path / "evalcraft.toml").exists()
        assert (tmp_path / "conftest.py").exists()

    def test_skip_existing_without_overwrite(self, tmp_path):
        """Second run without --overwrite skips files that already exist."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        results2 = scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        # test_agent.py and evalcraft.toml and conftest.py should be skipped
        assert results2["tests/test_agent.py"] is False
        assert results2["evalcraft.toml"] is False
        assert results2["conftest.py"] is False

    def test_overwrite_replaces_existing_files(self, tmp_path):
        """With overwrite=True, existing files are replaced."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        # Corrupt the test file to confirm it gets replaced
        test_file = tmp_path / "tests" / "test_agent.py"
        test_file.write_text("CORRUPTED")

        results = scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
            overwrite=True,
        )

        assert results["tests/test_agent.py"] is True
        content = test_file.read_text()
        assert "CORRUPTED" not in content
        assert "evalcraft" in content.lower()

    def test_invalid_framework_raises_value_error(self, tmp_path):
        """scaffold_project raises ValueError for an unsupported framework."""
        with pytest.raises(ValueError, match="Unknown framework"):
            scaffold_project(
                framework="bogus_framework",
                tests_dir=Path("tests"),
                project_dir=tmp_path,
            )

    def test_all_five_frameworks_scaffold_without_error(self, tmp_path):
        """Every supported framework can be scaffolded without raising."""
        for fw in FRAMEWORKS:
            fw_dir = tmp_path / fw
            fw_dir.mkdir()
            results = scaffold_project(
                framework=fw,
                tests_dir=Path("tests"),
                project_dir=fw_dir,
            )
            assert "tests/test_agent.py" in results, f"{fw}: test_agent.py missing"

    def test_custom_tests_dir(self, tmp_path):
        """Non-default --dir value is reflected in generated paths."""
        results = scaffold_project(
            framework="generic",
            tests_dir=Path("agent-tests"),
            project_dir=tmp_path,
        )
        assert "agent-tests/test_agent.py" in results
        assert (tmp_path / "agent-tests" / "test_agent.py").exists()

    def test_cassettes_dir_created(self, tmp_path):
        """The cassettes/ directory is created even when it doesn't exist."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        cassettes = tmp_path / "tests" / "cassettes"
        assert cassettes.is_dir()

    def test_gitkeep_created_in_cassettes(self, tmp_path):
        """A .gitkeep file is placed inside tests/cassettes/."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        gitkeep = tmp_path / "tests" / "cassettes" / ".gitkeep"
        assert gitkeep.exists()


# ─── file content validation ──────────────────────────────────────────────────


class TestGeneratedFileContent:
    """Verify the generated files contain expected patterns."""

    def test_test_agent_py_imports_evalcraft(self, tmp_path):
        """Generated test_agent.py imports from evalcraft."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "tests" / "test_agent.py").read_text()
        assert "from evalcraft" in content

    def test_test_agent_py_contains_capture_context(self, tmp_path):
        """Generated test_agent.py uses CaptureContext."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "tests" / "test_agent.py").read_text()
        assert "CaptureContext" in content

    def test_test_agent_py_contains_mock_llm(self, tmp_path):
        """Generated test_agent.py uses MockLLM."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "tests" / "test_agent.py").read_text()
        assert "MockLLM" in content

    def test_evalcraft_toml_has_framework(self, tmp_path):
        """evalcraft.toml contains the chosen framework value."""
        scaffold_project(
            framework="openai",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "evalcraft.toml").read_text()
        assert 'framework = "openai"' in content

    def test_evalcraft_toml_has_cassette_dir(self, tmp_path):
        """evalcraft.toml contains the cassette_dir setting."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "evalcraft.toml").read_text()
        assert "cassette_dir" in content
        assert "cassettes" in content

    def test_conftest_mentions_pytest(self, tmp_path):
        """conftest.py mentions pytest configuration."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "conftest.py").read_text()
        assert "pytest" in content.lower()

    def test_anthropic_template_references_anthropic(self, tmp_path):
        """Anthropic-specific template mentions AnthropicAdapter."""
        scaffold_project(
            framework="anthropic",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "tests" / "test_agent.py").read_text()
        assert "AnthropicAdapter" in content or "anthropic" in content.lower()

    def test_openai_template_references_openai(self, tmp_path):
        """OpenAI-specific template mentions get_weather or openai."""
        scaffold_project(
            framework="openai",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "tests" / "test_agent.py").read_text()
        assert "OpenAIAdapter" in content or "openai" in content.lower()

    def test_langgraph_template_references_langgraph(self, tmp_path):
        """LangGraph-specific template mentions LangGraphAdapter."""
        scaffold_project(
            framework="langgraph",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "tests" / "test_agent.py").read_text()
        assert "LangGraphAdapter" in content or "langgraph" in content.lower()

    def test_crewai_template_references_crewai(self, tmp_path):
        """CrewAI-specific template mentions CrewAIAdapter."""
        scaffold_project(
            framework="crewai",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "tests" / "test_agent.py").read_text()
        assert "CrewAIAdapter" in content or "crewai" in content.lower()

    def test_tests_dir_placeholder_replaced(self, tmp_path):
        """The {tests_dir} placeholder is replaced in all generated files."""
        scaffold_project(
            framework="generic",
            tests_dir=Path("my-tests"),
            project_dir=tmp_path,
        )
        for name in ["my-tests/test_agent.py", "evalcraft.toml", "conftest.py"]:
            path = tmp_path / name
            if path.exists():
                content = path.read_text()
                assert "{tests_dir}" not in content, f"{name} still has {{tests_dir}} placeholder"

    def test_framework_placeholder_replaced_in_toml(self, tmp_path):
        """The {framework} placeholder is replaced in evalcraft.toml."""
        scaffold_project(
            framework="openai",
            tests_dir=Path("tests"),
            project_dir=tmp_path,
        )
        content = (tmp_path / "evalcraft.toml").read_text()
        assert "{framework}" not in content


# ─── CLI tests ────────────────────────────────────────────────────────────────


class TestInitCLI:
    """Integration tests via Click's CliRunner."""

    def test_cli_non_interactive_openai(self, tmp_path):
        """Non-interactive mode scaffolds files and exits 0."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = _run_init(runner, ["--framework", "openai"])

        assert result.exit_code == 0, result.output
        assert "created" in result.output or "done" in result.output

    def test_cli_non_interactive_all_frameworks(self, tmp_path):
        """All frameworks work non-interactively without error."""
        runner = CliRunner()
        for fw in FRAMEWORKS:
            fw_dir = tmp_path / fw
            fw_dir.mkdir()
            with runner.isolated_filesystem(temp_dir=fw_dir):
                result = _run_init(runner, ["--framework", fw])
            assert result.exit_code == 0, f"{fw}: exit_code={result.exit_code}\n{result.output}"

    def test_cli_custom_dir(self, tmp_path):
        """--dir option sets the tests directory."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = _run_init(runner, ["--framework", "generic", "--dir", "agent-tests"])

        assert result.exit_code == 0
        assert "agent-tests" in result.output

    def test_cli_output_shows_created_files(self, tmp_path):
        """CLI output lists the files that were created."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = _run_init(runner, ["--framework", "generic"])

        assert "test_agent.py" in result.output
        assert "evalcraft.toml" in result.output
        assert "conftest.py" in result.output

    def test_cli_overwrite_flag(self, tmp_path):
        """--overwrite replaces existing files (no skip message)."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _run_init(runner, ["--framework", "generic"])
            result2 = _run_init(runner, ["--framework", "generic", "--overwrite"])

        assert result2.exit_code == 0
        # When overwriting, "skipped" should not appear for the main files
        assert "skipped" not in result2.output or "skipped (already exist)" not in result2.output

    def test_cli_interactive_numeric_choice(self, tmp_path):
        """Interactive mode accepts a numeric choice (e.g., '1' = openai)."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                cli,
                ["init"],
                input="1\n",  # Selects 'openai'
                catch_exceptions=False,
            )

        assert result.exit_code == 0, result.output
        assert "openai" in result.output.lower()

    def test_cli_interactive_name_choice(self, tmp_path):
        """Interactive mode accepts framework name as direct input."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                cli,
                ["init"],
                input="anthropic\n",
                catch_exceptions=False,
            )

        assert result.exit_code == 0, result.output
        assert "anthropic" in result.output.lower()

    def test_cli_shows_next_steps(self, tmp_path):
        """CLI output includes 'Next steps' guidance."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = _run_init(runner, ["--framework", "generic"])

        assert "Next steps" in result.output
        assert "pytest" in result.output

    def test_cli_help_text(self):
        """evalcraft init --help prints help without error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--help"])

        assert result.exit_code == 0
        assert "framework" in result.output
        assert "dir" in result.output

    def test_cli_skip_message_on_second_run(self, tmp_path):
        """CLI shows skip message when files already exist."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _run_init(runner, ["--framework", "generic"])
            result2 = _run_init(runner, ["--framework", "generic"])

        assert "skipped" in result2.output

    def test_cli_created_files_are_valid_python(self, tmp_path):
        """Generated test_agent.py parses as valid Python (compile check)."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _run_init(runner, ["--framework", "generic"])
            test_file = Path("tests") / "test_agent.py"
            source = test_file.read_text()

        # compile() raises SyntaxError if the source is invalid
        try:
            compile(source, "<test_agent.py>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Generated test_agent.py has a syntax error: {exc}")

    def test_cli_conftest_is_valid_python(self, tmp_path):
        """Generated conftest.py parses as valid Python (compile check)."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _run_init(runner, ["--framework", "generic"])
            source = Path("conftest.py").read_text()

        try:
            compile(source, "<conftest.py>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Generated conftest.py has a syntax error: {exc}")

    def test_cli_init_is_registered_as_subcommand(self):
        """'evalcraft init' appears in the top-level help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "init" in result.output
