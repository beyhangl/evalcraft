"""evalcraft init — scaffold a new agent test project.

Creates:
  <tests_dir>/test_agent.py   — complete working test with capture + mock + assertions
  <tests_dir>/cassettes/      — empty cassette directory (with .gitkeep)
  evalcraft.toml              — config with sensible defaults
  conftest.py                 — pytest config with evalcraft fixtures

Public API:
    scaffold_project(...)   — create files programmatically
    run_init(...)           — entry-point called by the CLI command
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

# ─── supported frameworks ──────────────────────────────────────────────────────

FRAMEWORKS: list[str] = ["openai", "anthropic", "langgraph", "crewai", "generic"]

_FRAMEWORK_LABELS: dict[str, str] = {
    "openai": "OpenAI (gpt-5.4, gpt-5.4-nano, o3, o4-mini, …)",
    "anthropic": "Anthropic (Claude Opus 4.6, Sonnet 4.6, Mythos, …)",
    "langgraph": "LangGraph (stateful agent graphs via LangChain)",
    "crewai": "CrewAI (multi-agent crews)",
    "generic": "Generic (framework-agnostic, raw evalcraft primitives)",
}

_FRAMEWORK_ADAPTER_IMPORT: dict[str, str] = {
    "openai": "from evalcraft.adapters import OpenAIAdapter",
    "anthropic": "from evalcraft.adapters import AnthropicAdapter",
    "langgraph": "from evalcraft.adapters import LangGraphAdapter",
    "crewai": "from evalcraft.adapters import CrewAIAdapter",
    "generic": "# No special adapter needed — use CaptureContext directly",
}


# ─── template loading ──────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _load_template(filename: str) -> str:
    """Load a template file from the templates/ directory."""
    path = _TEMPLATES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


def _render_template(template: str, tests_dir: str, framework: str) -> str:
    """Substitute {tests_dir} and {framework} placeholders in a template."""
    return template.replace("{tests_dir}", tests_dir).replace("{framework}", framework)


# ─── file writers ──────────────────────────────────────────────────────────────

def _write_file(path: Path, content: str, *, overwrite: bool) -> bool:
    """Write *content* to *path*.  Returns True if written, False if skipped."""
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


# ─── public scaffold API ───────────────────────────────────────────────────────

def scaffold_project(
    *,
    framework: str,
    tests_dir: Path,
    project_dir: Path,
    overwrite: bool = False,
) -> dict[str, bool]:
    """Create all scaffold files for an evalcraft project.

    Args:
        framework: One of the FRAMEWORKS values.
        tests_dir: Relative or absolute path to the tests directory.
        project_dir: Root directory where evalcraft.toml and conftest.py go.
        overwrite: If True, overwrite existing files.

    Returns:
        dict mapping relative path (str) -> True (written) | False (skipped).

    Raises:
        ValueError: if *framework* is not in FRAMEWORKS.
        FileNotFoundError: if a template file is missing from the package.
    """
    if framework not in FRAMEWORKS:
        raise ValueError(
            f"Unknown framework {framework!r}. Choose from: {FRAMEWORKS}"
        )

    tests_dir_abs = (
        project_dir / tests_dir if not tests_dir.is_absolute() else tests_dir
    )
    tests_dir_rel = str(tests_dir)

    results: dict[str, bool] = {}

    # 1. tests/test_agent.py
    test_template = _load_template(f"test_agent_{framework}.py")
    test_content = _render_template(test_template, tests_dir_rel, framework)
    test_path = tests_dir_abs / "test_agent.py"
    results[str(test_path.relative_to(project_dir))] = _write_file(
        test_path, test_content, overwrite=overwrite
    )

    # 2. tests/cassettes/ — empty directory with a .gitkeep sentinel
    cassettes_dir = tests_dir_abs / "cassettes"
    cassettes_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = cassettes_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("", encoding="utf-8")
    cassettes_key = str((cassettes_dir / ".gitkeep").relative_to(project_dir))
    results[cassettes_key] = True

    # 2b. a sample recording, so the replay tests pass on the very first run
    sample_name, sample_json = _sample_cassette_json(framework)
    sample_path = cassettes_dir / sample_name
    results[str(sample_path.relative_to(project_dir))] = _write_file(
        sample_path, sample_json, overwrite=overwrite
    )

    # 3. evalcraft.toml
    toml_template = _load_template("evalcraft.toml")
    toml_content = _render_template(toml_template, tests_dir_rel, framework)
    toml_path = project_dir / "evalcraft.toml"
    results[str(toml_path.relative_to(project_dir))] = _write_file(
        toml_path, toml_content, overwrite=overwrite
    )

    # 4. conftest.py
    conftest_template = _load_template("conftest.py")
    conftest_content = _render_template(conftest_template, tests_dir_rel, framework)
    conftest_path = project_dir / "conftest.py"
    results[str(conftest_path.relative_to(project_dir))] = _write_file(
        conftest_path, conftest_content, overwrite=overwrite
    )

    return results


# ─── CLI entry-point (called from main.py) ────────────────────────────────────


# Sample recordings shipped by ``init`` so the scaffold's replay tests have a
# real cassette to read on the first run. Keys match each template's
# ``@pytest.mark.evalcraft_cassette`` path; tools match what those tests assert.
_SAMPLE_CASSETTES: dict[str, tuple[str, list[str], str]] = {
    "generic": ("my_run.json", ["lookup"], "Order 4521 has shipped."),
    "openai": ("openai_weather.json", ["get_weather"], "It is 18C and cloudy in Paris."),
    "anthropic": ("anthropic_search.json", ["web_search"], "Here is what I found."),
    "langgraph": ("langgraph_search.json", ["tavily_search"], "Here is what I found."),
    "crewai": ("crewai_research.json", ["web_search", "file_write"], "Report written."),
}


def _sample_cassette_json(framework: str) -> tuple[str, str]:
    """Build the deterministic sample cassette for ``framework``.

    Fixed ids and timestamps keep it byte-identical across runs, and the model
    name is deliberately generic so ``check-stale`` never flags the sample as a
    reasoning model with missing reasoning state.
    """
    import json

    from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage

    filename, tools, output = _SAMPLE_CASSETTES[framework]
    c = Cassette(
        id="sample-" + framework, name=filename.removesuffix(".json"),
        created_at=0.0, agent_name=f"{framework}_example", framework=framework,
        metadata={"sample": True, "note": (
            "Example recording written by `evalcraft init`. Replace it by "
            "recording your own agent: pytest --evalcraft-record=new"
        )},
    )
    c.input_text = "Example request"
    for i, tool in enumerate(tools):
        c.add_span(Span(id=f"tool-{i}", kind=SpanKind.TOOL_CALL, name=f"tool:{tool}",
                        timestamp=0.0, tool_name=tool, tool_args={"query": "example"},
                        tool_result={"ok": True}))
    c.add_span(Span(id="llm-0", kind=SpanKind.LLM_RESPONSE, name="llm:example-model",
                    timestamp=0.0, model="example-model", input="Example request",
                    output=output, cost_usd=0.0001,
                    token_usage=TokenUsage(prompt_tokens=20, completion_tokens=10,
                                           total_tokens=30)))
    c.output_text = output
    c.compute_fingerprint()
    return filename, json.dumps(c.to_dict(), indent=2, sort_keys=True) + "\n"


def run_init(
    framework: str | None,
    tests_dir: str,
    overwrite: bool,
) -> None:
    """Execute the init scaffold workflow.

    Separated from the Click command decorator so it can be tested without
    invoking the Click runner.
    """
    click.echo()
    click.echo(click.style("  evalcraft init", fg="cyan", bold=True))
    click.echo()

    # ── Framework selection ────────────────────────────────────────────────────
    if framework is None:
        click.echo("  Which framework does your agent use?\n")
        for i, fw in enumerate(FRAMEWORKS, start=1):
            label = _FRAMEWORK_LABELS[fw]
            click.echo(f"  {click.style(str(i), bold=True, fg='cyan')}.  {label}")

        click.echo()
        try:
            raw = click.prompt(
                "  Select",
                default="5",
                show_default=True,
            ).strip()
        except click.exceptions.Abort:
            # stdin closed with no answer (CI, a coding agent, `< /dev/null`):
            # nobody can answer the prompt, so take the default rather than
            # aborting. Piped answers and real terminals still prompt normally.
            raw = "5"
            click.echo("\n  No input available — using the generic scaffold "
                       "(pass --framework to choose).")

        # Accept a numeric choice (1-5) or the framework name directly
        if raw.isdigit():
            idx = int(raw) - 1
            if idx < 0 or idx >= len(FRAMEWORKS):
                click.echo(
                    click.style(f"  Error: invalid choice {raw!r}", fg="red"), err=True
                )
                sys.exit(1)
            framework = FRAMEWORKS[idx]
        elif raw.lower() in FRAMEWORKS:
            framework = raw.lower()
        else:
            click.echo(
                click.style(f"  Error: unknown framework {raw!r}", fg="red"), err=True
            )
            click.echo(f"  Valid choices: {', '.join(FRAMEWORKS)}")
            sys.exit(1)

    project_dir = Path.cwd()
    tests_path = Path(tests_dir)

    click.echo()
    click.echo(f"  framework   {click.style(framework, fg='green', bold=True)}")
    click.echo(f"  tests dir   {tests_path}")
    click.echo(f"  project dir {project_dir}")
    click.echo()

    # ── Scaffold ───────────────────────────────────────────────────────────────
    try:
        results = scaffold_project(
            framework=framework,
            tests_dir=tests_path,
            project_dir=project_dir,
            overwrite=overwrite,
        )
    except FileNotFoundError as exc:
        click.echo(click.style(f"  Error: {exc}", fg="red"), err=True)
        sys.exit(1)
    except ValueError as exc:
        click.echo(click.style(f"  Error: {exc}", fg="red"), err=True)
        sys.exit(1)

    # ── Report ─────────────────────────────────────────────────────────────────
    for rel_path, written in results.items():
        if written:
            icon = click.style("  created", fg="green", bold=True)
        else:
            icon = click.style("  skipped", fg="yellow", bold=True)
        click.echo(f"{icon}  {rel_path}")

    n_skipped = sum(1 for v in results.values() if not v)

    click.echo()
    if n_skipped:
        click.echo(
            click.style("  tip:", fg="yellow", bold=True)
            + f"  {n_skipped} file(s) skipped (already exist)."
            "  Use --overwrite to replace them."
        )

    click.echo(click.style("  done", fg="green", bold=True))
    click.echo()
    click.echo("  Next steps:")
    click.echo("    pip install 'evalcraft[pytest]'")
    click.echo(f"    pytest {tests_dir}/test_agent.py -v")
    click.echo()
    click.echo("  To record a real cassette from a live agent run:")
    click.echo(f"    pytest {tests_dir}/test_agent.py -v --evalcraft-record=new")
    click.echo()
    click.echo(f"  Adapter import for {framework}:")
    click.echo(f"    {_FRAMEWORK_ADAPTER_IMPORT[framework]}")
    click.echo()
