"""Evalcraft CLI — capture, replay, diff, eval, and inspect agent cassettes."""

from __future__ import annotations

import datetime
import json
import runpy
import sys
from pathlib import Path
from typing import Any

import click

from evalcraft.capture.recorder import CaptureContext
from evalcraft.core.models import Cassette, SpanKind
from evalcraft.replay.engine import ReplayDiff, ReplayEngine
from evalcraft.replay.network_guard import ReplayNetworkViolation


# ─── helpers ──────────────────────────────────────────────────────────────────

def _load_cassette(path: str) -> Cassette:
    p = Path(path)
    if not p.exists():
        click.echo(click.style(f"Error: file not found: {path}", fg="red"), err=True)
        sys.exit(1)
    try:
        return Cassette.load(p)
    except Exception as e:
        click.echo(click.style(f"Error loading cassette: {e}", fg="red"), err=True)
        sys.exit(1)


def _fmt_duration(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.2f}s"


def _fmt_cost(usd: float) -> str:
    if usd == 0:
        return "$0.00"
    if usd < 0.01:
        return f"${usd:.6f}"
    return f"${usd:.4f}"


_SPAN_COLORS: dict[SpanKind, str] = {
    SpanKind.LLM_REQUEST: "blue",
    SpanKind.LLM_RESPONSE: "blue",
    SpanKind.TOOL_CALL: "yellow",
    SpanKind.TOOL_RESULT: "yellow",
    SpanKind.AGENT_STEP: "magenta",
    SpanKind.USER_INPUT: "green",
    SpanKind.AGENT_OUTPUT: "green",
}


# ─── CLI root ─────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(version="0.1.0", prog_name="evalcraft")
def cli() -> None:
    """evalcraft — capture, replay, and evaluate AI agent runs."""


# ─── init ─────────────────────────────────────────────────────────────────────

@cli.command("init")
@click.option(
    "--framework",
    "-f",
    default=None,
    type=click.Choice(
        ["openai", "anthropic", "langgraph", "crewai", "generic"],
        case_sensitive=False,
    ),
    help="Agent framework to scaffold for (skips interactive prompt).",
)
@click.option(
    "--dir",
    "-d",
    "tests_dir",
    default="tests",
    show_default=True,
    help="Directory to create test files in.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Overwrite existing files (default: skip).",
)
def init(framework: str | None, tests_dir: str, overwrite: bool) -> None:
    """Scaffold an evalcraft test project in the current directory.

    Creates a complete, runnable test suite with capture, replay, mock,
    and assertion examples tailored to your agent framework.

    Examples:

        evalcraft init

        evalcraft init --framework anthropic --dir agent-tests

        evalcraft init --framework openai --overwrite
    """
    from evalcraft.cli.init_cmd import run_init

    run_init(framework=framework, tests_dir=tests_dir, overwrite=overwrite)


# ─── capture ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("script", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default=None, help="Output cassette path (default: <script>.cassette.json)")
@click.option("--name", "-n", default="", help="Cassette name")
@click.option("--agent", "-a", default="", help="Agent name tag")
@click.option("--framework", "-f", default="", help="Framework tag")
def capture(script: str, output: str | None, name: str, agent: str, framework: str) -> None:
    """Run SCRIPT with evalcraft capture enabled and save the cassette.

    The script is executed in the current Python interpreter with a
    CaptureContext active, so any evalcraft instrumentation in the script
    (record_llm_call, record_tool_call, etc.) is automatically recorded.

    Example:

        evalcraft capture my_agent.py --output cassettes/run1.json
    """
    script_path = Path(script)
    out_path = Path(output) if output else script_path.with_suffix(".cassette.json")
    cassette_name = name or script_path.stem

    click.echo(
        click.style("  capturing", fg="cyan", bold=True)
        + f"  {script_path.name}  →  {out_path}"
    )

    ctx = CaptureContext(
        name=cassette_name,
        agent_name=agent,
        framework=framework,
        save_path=out_path,
    )

    try:
        with ctx:
            script_dir = str(script_path.parent.resolve())
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            runpy.run_path(str(script_path.resolve()), run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (None, 0):
            click.echo(click.style(f"  script exited with code {exc.code}", fg="yellow"))
    except Exception as exc:
        click.echo(click.style(f"  error: {exc}", fg="red"), err=True)
        sys.exit(1)

    c = ctx.cassette
    click.echo(click.style("  saved", fg="green", bold=True) + f"     {out_path}")
    click.echo(
        f"  spans={len(c.spans)}"
        f"  llm={c.llm_call_count}"
        f"  tools={c.tool_call_count}"
        f"  tokens={c.total_tokens}"
        f"  cost={_fmt_cost(c.total_cost_usd)}"
        f"  time={_fmt_duration(c.total_duration_ms)}"
    )


# ─── replay ───────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--verbose", "-v", is_flag=True, help="Show each span")
@click.option(
    "--block-network/--no-block-network",
    default=True,
    show_default=True,
    help=(
        "Block outgoing network connections during replay (default: on). "
        "Use --no-block-network to allow real HTTP calls."
    ),
)
@click.option(
    "--allow-host",
    "allow_hosts",
    multiple=True,
    metavar="HOST",
    help="Allow a specific hostname even when --block-network is active (repeatable).",
)
def replay(cassette: str, verbose: bool, block_network: bool, allow_hosts: tuple[str, ...]) -> None:
    """Replay CASSETTE and display the results.

    Feeds recorded responses back through the replay engine without making
    any real LLM API calls.  By default, all outgoing network connections
    are blocked to guarantee a fully deterministic replay.

    Examples:

        evalcraft replay cassettes/run1.json --verbose

        evalcraft replay cassettes/run1.json --no-block-network

        evalcraft replay cassettes/run1.json --allow-host localhost --allow-host 127.0.0.1
    """
    c = _load_cassette(cassette)
    engine = ReplayEngine(
        c,
        block_network=block_network,
        network_allowlist=list(allow_hosts) if allow_hosts else None,
    )

    if block_network:
        hosts_note = (
            f"  (allowlist: {', '.join(allow_hosts)})" if allow_hosts else "  (network blocked)"
        )
        click.echo(click.style("  network", fg="yellow") + hosts_note)

    try:
        run = engine.run()
    except ReplayNetworkViolation as exc:
        click.echo(click.style("  network violation", fg="red", bold=True), err=True)
        click.echo(click.style(f"  {exc}", fg="red"), err=True)
        sys.exit(1)
    rc = run.cassette

    click.echo(click.style("  replaying", fg="cyan", bold=True) + f"  {Path(cassette).name}")
    click.echo()
    click.echo(f"  name         {rc.name or '(unnamed)'}")
    click.echo(f"  agent        {rc.agent_name or '—'}")
    click.echo(f"  framework    {rc.framework or '—'}")
    click.echo(f"  fingerprint  {rc.fingerprint or '—'}")
    click.echo(f"  spans        {len(rc.spans)}")
    click.echo(f"  llm calls    {rc.llm_call_count}")
    click.echo(f"  tool calls   {rc.tool_call_count}")
    click.echo(f"  tokens       {rc.total_tokens:,}")
    click.echo(f"  cost         {_fmt_cost(rc.total_cost_usd)}")
    click.echo(f"  duration     {_fmt_duration(rc.total_duration_ms)}")

    if rc.output_text:
        click.echo()
        click.echo(click.style("  output:", bold=True))
        preview = rc.output_text[:500]
        if len(rc.output_text) > 500:
            preview += "…"
        click.echo(f"  {preview}")

    if verbose:
        click.echo()
        click.echo(click.style("  spans:", bold=True))
        for i, span in enumerate(rc.spans):
            color = _SPAN_COLORS.get(span.kind, "white")
            tokens_str = f"  ({span.token_usage.total_tokens}t)" if span.token_usage else ""
            detail = span.tool_name or span.model or span.name or ""
            click.echo(
                f"  {click.style(f'[{i}]', fg=color)}"
                f"  {click.style(span.kind.value, fg=color):<22}"
                f"  {detail}{tokens_str}"
            )

    click.echo()
    click.echo(click.style("  done", fg="green", bold=True))


# ─── diff ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("old", type=click.Path(exists=True, dir_okay=False))
@click.argument("new", type=click.Path(exists=True, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def diff(old: str, new: str, as_json: bool) -> None:
    """Compare two cassettes and show what changed.

    Useful for detecting regressions between agent runs — changes in tool
    order, output text, token usage, or cost.

    Example:

        evalcraft diff cassettes/baseline.json cassettes/new_run.json
    """
    c_old = _load_cassette(old)
    c_new = _load_cassette(new)

    d = ReplayDiff.compute(c_old, c_new)

    if as_json:
        click.echo(json.dumps(d.to_dict(), indent=2))
        return

    click.echo(
        click.style("  diff", fg="cyan", bold=True)
        + f"  {Path(old).name}  →  {Path(new).name}"
    )
    click.echo()

    if not d.has_changes:
        click.echo(click.style("  no changes detected", fg="green"))
        return

    def _row(label: str, changed: bool, old_val: Any, new_val: Any) -> None:
        if not changed:
            click.echo(
                f"  {click.style('=', fg='green')}  {label:<22}  "
                + click.style("unchanged", fg="green")
            )
        else:
            old_s = str(old_val)
            new_s = str(new_val)
            if len(old_s) > 60:
                old_s = old_s[:57] + "…"
            if len(new_s) > 60:
                new_s = new_s[:57] + "…"
            click.echo(
                f"  {click.style('~', fg='yellow')}  {label:<22}  "
                + click.style(old_s, fg="red")
                + "  →  "
                + click.style(new_s, fg="green")
            )

    _row("tool sequence", d.tool_sequence_changed, d.old_tool_sequence, d.new_tool_sequence)
    _row("output text", d.output_changed, d.old_output, d.new_output)
    _row("token count", d.token_count_changed, d.old_tokens, d.new_tokens)
    _row("cost", d.cost_changed, _fmt_cost(d.old_cost), _fmt_cost(d.new_cost))
    _row("span count", d.span_count_changed, d.old_span_count, d.new_span_count)


# ─── eval ─────────────────────────────────────────────────────────────────────

@cli.command("eval")
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--max-cost", default=None, type=float, metavar="USD", help="Max cost threshold in USD")
@click.option("--max-tokens", default=None, type=int, help="Max token count threshold")
@click.option("--max-latency", default=None, type=float, metavar="MS", help="Max latency in milliseconds")
@click.option("--tool", "required_tools", multiple=True, metavar="NAME", help="Tool that must have been called (repeatable)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def eval_cmd(
    cassette: str,
    max_cost: float | None,
    max_tokens: int | None,
    max_latency: float | None,
    required_tools: tuple[str, ...],
    as_json: bool,
) -> None:
    """Run eval assertions on CASSETTE and report pass/fail.

    Without thresholds, prints a metrics summary. With thresholds, runs
    assertions and exits 1 if any fail (useful in CI).

    Example:

        evalcraft eval cassettes/run1.json \\
            --max-cost 0.05 \\
            --max-tokens 4000 \\
            --tool web_search \\
            --tool summarize
    """
    from evalcraft.eval.scorers import (
        Evaluator,
        assert_cost_under,
        assert_latency_under,
        assert_token_count_under,
        assert_tool_called,
    )

    c = _load_cassette(cassette)
    c.compute_metrics()

    # No assertions — show metrics summary
    if not max_cost and not max_tokens and not max_latency and not required_tools:
        click.echo(click.style("  eval", fg="cyan", bold=True) + f"  {Path(cassette).name}")
        click.echo()
        click.echo(click.style("  metrics (no thresholds set)", bold=True))
        click.echo(f"  tokens    {c.total_tokens:,}")
        click.echo(f"  cost      {_fmt_cost(c.total_cost_usd)}")
        click.echo(f"  latency   {_fmt_duration(c.total_duration_ms)}")
        click.echo(f"  llm       {c.llm_call_count} calls")
        click.echo(f"  tools     {c.get_tool_sequence() or '(none)'}")
        return

    evaluator = Evaluator()
    if max_cost is not None:
        evaluator.add(assert_cost_under, c, max_cost)
    if max_tokens is not None:
        evaluator.add(assert_token_count_under, c, max_tokens)
    if max_latency is not None:
        evaluator.add(assert_latency_under, c, max_latency)
    for tool in required_tools:
        evaluator.add(assert_tool_called, c, tool)

    result = evaluator.run()

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
        if not result.passed:
            sys.exit(1)
        return

    click.echo(click.style("  eval", fg="cyan", bold=True) + f"  {Path(cassette).name}")
    click.echo()

    for assertion in result.assertions:
        if assertion.passed:
            icon = click.style("  PASS", fg="green", bold=True)
            click.echo(f"{icon}  {assertion.name}")
        else:
            icon = click.style("  FAIL", fg="red", bold=True)
            click.echo(f"{icon}  {assertion.name}")
            click.echo(f"        {click.style(assertion.message, fg='red')}")
            click.echo(f"        expected: {assertion.expected}")
            click.echo(f"        actual:   {assertion.actual}")

    click.echo()
    n_pass = sum(1 for a in result.assertions if a.passed)
    n_total = len(result.assertions)
    score_pct = f"{result.score * 100:.0f}%"
    score_color = "green" if result.passed else "red"
    click.echo(
        click.style(f"  score: {score_pct}", fg=score_color, bold=True)
        + f"  ({n_pass}/{n_total} passed)"
    )

    if not result.passed:
        sys.exit(1)


# ─── info ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Output raw cassette JSON")
@click.option("--spans", is_flag=True, help="Show all spans")
def info(cassette: str, as_json: bool, spans: bool) -> None:
    """Show metadata for CASSETTE — spans, tools, tokens, cost.

    Example:

        evalcraft info cassettes/run1.json --spans
    """
    c = _load_cassette(cassette)
    c.compute_metrics()

    if as_json:
        click.echo(json.dumps(c.to_dict(), indent=2, default=str))
        return

    created = datetime.datetime.fromtimestamp(c.created_at).strftime("%Y-%m-%d %H:%M:%S")

    click.echo(click.style("  cassette info", fg="cyan", bold=True))
    click.echo()
    click.echo(f"  id           {c.id}")
    click.echo(f"  name         {c.name or '(unnamed)'}")
    click.echo(f"  agent        {c.agent_name or '—'}")
    click.echo(f"  framework    {c.framework or '—'}")
    click.echo(f"  version      {c.version}")
    click.echo(f"  created      {created}")
    click.echo(f"  fingerprint  {c.fingerprint or '—'}")

    click.echo()
    click.echo(click.style("  metrics", bold=True))
    click.echo(f"  spans        {len(c.spans)}")
    click.echo(f"  llm calls    {c.llm_call_count}")
    click.echo(f"  tool calls   {c.tool_call_count}")
    click.echo(f"  tokens       {c.total_tokens:,}")
    click.echo(f"  cost         {_fmt_cost(c.total_cost_usd)}")
    click.echo(f"  duration     {_fmt_duration(c.total_duration_ms)}")

    tool_seq = c.get_tool_sequence()
    if tool_seq:
        click.echo()
        click.echo(click.style("  tool sequence", bold=True))
        for i, tool in enumerate(tool_seq):
            click.echo(f"  {i + 1:>3}.  {tool}")

    if c.input_text:
        click.echo()
        click.echo(click.style("  input:", bold=True))
        preview = c.input_text[:300]
        if len(c.input_text) > 300:
            preview += "…"
        click.echo(f"  {preview}")

    if c.output_text:
        click.echo()
        click.echo(click.style("  output:", bold=True))
        preview = c.output_text[:300]
        if len(c.output_text) > 300:
            preview += "…"
        click.echo(f"  {preview}")

    if c.metadata:
        click.echo()
        click.echo(click.style("  metadata", bold=True))
        for key, val in c.metadata.items():
            click.echo(f"  {key:<16}  {val}")

    if spans:
        click.echo()
        click.echo(click.style("  all spans", bold=True))
        for i, span in enumerate(c.spans):
            color = _SPAN_COLORS.get(span.kind, "white")
            tokens_str = f"  {span.token_usage.total_tokens}t" if span.token_usage else ""
            cost_str = f"  {_fmt_cost(span.cost_usd)}" if span.cost_usd else ""
            dur_str = f"  {_fmt_duration(span.duration_ms)}" if span.duration_ms else ""
            extra = span.tool_name or span.model or ""
            click.echo(
                f"  {click.style(f'[{i}]', fg=color)}"
                f"  {click.style(span.kind.value, fg=color):<28}"
                f"  {extra:<24}"
                f"{dur_str}{tokens_str}{cost_str}"
            )
            if span.error:
                click.echo(f"       {click.style('error: ' + span.error, fg='red')}")


# ─── mock ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default=None, help="Output Python file (default: stdout)")
@click.option("--var", default="mock_llm", help="Variable name for MockLLM factory (default: mock_llm)")
def mock(cassette: str, output: str | None, var: str) -> None:
    """Generate MockLLM and tool fixtures from CASSETTE.

    Emits a Python module with a factory function that returns a MockLLM
    pre-loaded with all recorded responses, plus a TOOL_RESULTS dict and a
    ReplayEngine factory — ready to paste into your test suite.

    Example:

        evalcraft mock cassettes/run1.json --output tests/fixtures/mock_agent.py
    """
    c = _load_cassette(cassette)

    llm_spans = [s for s in c.spans if s.kind == SpanKind.LLM_RESPONSE and s.output]
    tool_spans = c.get_tool_calls()
    tool_names = list(dict.fromkeys(s.tool_name for s in tool_spans if s.tool_name))

    lines: list[str] = [
        '"""Auto-generated mock fixtures.',
        f'   Source:    {Path(cassette).name}',
        f'   Agent:     {c.agent_name or "(unknown)"}',
        f'   Framework: {c.framework or "(unknown)"}',
        f'   LLM spans: {len(llm_spans)}',
        f'   Tools:     {len(tool_names)}',
        '"""',
        "",
        "from evalcraft.mock.llm import MockLLM",
        "from evalcraft.replay.engine import ReplayEngine",
        "",
        "",
    ]

    # MockLLM factory
    lines.append(f"def make_{var}() -> MockLLM:")
    lines.append(f'    """MockLLM with {len(llm_spans)} recorded response(s)."""')
    model_name = c.framework or "mock-llm"
    lines.append(f'    mock = MockLLM(model={model_name!r})')
    lines.append("")

    if llm_spans:
        for i, span in enumerate(llm_spans):
            pt = span.token_usage.prompt_tokens if span.token_usage else 10
            ct = span.token_usage.completion_tokens if span.token_usage else 20
            input_repr = repr(str(span.input or ""))
            output_repr = repr(str(span.output or ""))
            lines.append(f"    # LLM call {i}")
            lines.append(f"    mock.add_response(")
            lines.append(f"        {input_repr},")
            lines.append(f"        {output_repr},")
            lines.append(f"        prompt_tokens={pt},")
            lines.append(f"        completion_tokens={ct},")
            lines.append(f"    )")
    else:
        lines.append('    mock.add_response("*", "mock response")')

    lines.extend(["", "    return mock", ""])

    # Tool fixtures
    if tool_names:
        lines.append("")
        lines.append("# Recorded tool results — override as needed in your tests")
        lines.append("TOOL_RESULTS: dict = {")
        for tool_name in tool_names:
            first_call = next(s for s in tool_spans if s.tool_name == tool_name)
            lines.append(f"    {tool_name!r}: {first_call.tool_result!r},")
        lines.append("}")
        lines.append("")
        lines.append("")
        lines.append("def make_replay_engine(cassette_path: str) -> ReplayEngine:")
        lines.append('    """ReplayEngine pre-loaded with recorded tool results."""')
        lines.append("    engine = ReplayEngine(cassette_path)")
        for tool_name in tool_names:
            lines.append(
                f"    engine.override_tool_result({tool_name!r}, TOOL_RESULTS[{tool_name!r}])"
            )
        lines.append("    return engine")
        lines.append("")

    code = "\n".join(lines)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(code)
        click.echo(click.style("  generated", fg="green", bold=True) + f"  {out_path}")
        click.echo(f"  llm responses: {len(llm_spans)}")
        click.echo(f"  tool fixtures: {len(tool_names)}")
    else:
        click.echo(code)


# ─── generate-tests ──────────────────────────────────────────────────────────

@cli.command("generate-tests")
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default=None, help="Output Python file path (default: stdout)")
def generate_tests(cassette: str, output: str | None) -> None:
    """Auto-generate a pytest test file from CASSETTE.

    Reads the cassette and emits a complete, runnable test file with
    assertions for tool calls, output content, cost, tokens, and latency.

    Examples:

        evalcraft generate-tests tests/cassettes/weather.json

        evalcraft generate-tests tests/cassettes/weather.json -o tests/test_weather.py
    """
    from evalcraft.cli.generate_cmd import generate_test_code

    c = _load_cassette(cassette)
    code = generate_test_code(c, cassette)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(code)
        click.echo(
            click.style("  generated", fg="green", bold=True)
            + f"  {out_path}"
        )
        c.compute_metrics()
        click.echo(f"  tests: tool calls ({len(c.get_tool_calls())}), output, cost, tokens, latency")
    else:
        click.echo(code)


# ─── golden ──────────────────────────────────────────────────────────────────

@cli.group()
def golden() -> None:
    """Manage golden-set baselines for regression detection."""


@golden.command("save")
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--name", "-n", required=True, help="Name for the golden set")
@click.option("--output", "-o", default=None, help="Output path (default: <name>.golden.json)")
@click.option("--description", "-d", default="", help="Description of the golden set")
def golden_save(cassette: str, name: str, output: str | None, description: str) -> None:
    """Save CASSETTE as a golden-set baseline.

    Creates a versioned golden-set file that subsequent runs can be
    compared against.

    Example:

        evalcraft golden save cassettes/run1.json --name weather_agent
    """
    from evalcraft.golden.manager import GoldenSet

    c = _load_cassette(cassette)
    out_path = Path(output) if output else Path(f"{name}.golden.json")

    # If golden set exists, load it and bump version
    if out_path.exists():
        gs = GoldenSet.load(out_path)
        gs._cassettes.clear()
        gs.add_cassette(c)
        gs.bump_version()
        click.echo(
            click.style("  updated", fg="cyan", bold=True)
            + f"  {name} -> v{gs.version}"
        )
    else:
        gs = GoldenSet(name=name, description=description)
        gs.add_cassette(c)
        click.echo(
            click.style("  created", fg="cyan", bold=True)
            + f"  {name} v{gs.version}"
        )

    gs.save(out_path)
    click.echo(click.style("  saved", fg="green", bold=True) + f"     {out_path}")
    click.echo(f"  cassettes: {gs.cassette_count}")
    click.echo(f"  version:   v{gs.version}")


@golden.command("compare")
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--against", "-a", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Golden set to compare against")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def golden_compare(cassette: str, against: str, as_json: bool) -> None:
    """Compare CASSETTE against a golden-set baseline.

    Reports per-field pass/fail with configurable thresholds defined
    in the golden set.

    Example:

        evalcraft golden compare cassettes/new_run.json --against weather_agent.golden.json
    """
    from evalcraft.golden.manager import GoldenSet

    c = _load_cassette(cassette)
    gs = GoldenSet.load(against)
    result = gs.compare(c)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2, default=str))
        if not result.passed:
            sys.exit(1)
        return

    click.echo(
        click.style("  golden compare", fg="cyan", bold=True)
        + f"  {Path(cassette).name} vs {gs.name} v{gs.version}"
    )
    click.echo()

    for f in result.fields:
        if f.passed:
            icon = click.style("  PASS", fg="green", bold=True)
            click.echo(f"{icon}  {f.name}")
        else:
            icon = click.style("  FAIL", fg="red", bold=True)
            click.echo(f"{icon}  {f.name}")
            if f.message:
                click.echo(f"        {click.style(f.message, fg='red')}")

    click.echo()
    n_pass = sum(1 for f in result.fields if f.passed)
    n_total = len(result.fields)
    status = "PASS" if result.passed else "FAIL"
    color = "green" if result.passed else "red"
    click.echo(
        click.style(f"  {status}", fg=color, bold=True)
        + f"  ({n_pass}/{n_total} checks passed)"
    )

    if not result.passed:
        sys.exit(1)


# ─── regression ──────────────────────────────────────────────────────────────

@cli.command("regression")
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--golden", "-g", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Golden cassette or golden-set file to compare against")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def regression_cmd(cassette: str, golden: str, as_json: bool) -> None:
    """Check CASSETTE for regressions against a golden baseline.

    Detects: tool sequence changes, output drift, cost increases,
    latency increases, token bloat, and error introduction.

    Example:

        evalcraft regression cassettes/new_run.json --golden cassettes/baseline.json
    """
    from evalcraft.golden.manager import GoldenSet
    from evalcraft.regression.detector import RegressionDetector

    c = _load_cassette(cassette)

    golden_path = Path(golden)
    # Detect if it's a golden-set file or a plain cassette
    with open(golden_path) as f:
        golden_data = json.load(f)

    if golden_data.get("evalcraft_golden_set"):
        gs = GoldenSet.from_dict(golden_data)
        golden_cassette = gs.get_primary_cassette()
        if golden_cassette is None:
            click.echo(click.style("Error: golden set has no cassettes", fg="red"), err=True)
            sys.exit(1)
    else:
        golden_cassette = Cassette.from_dict(golden_data)

    detector = RegressionDetector()
    report = detector.compare(golden_cassette, c)

    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2, default=str))
        if report.has_critical:
            sys.exit(1)
        return

    click.echo(
        click.style("  regression check", fg="cyan", bold=True)
        + f"  {Path(cassette).name}"
    )
    click.echo()

    if not report.has_regressions:
        click.echo(click.style("  no regressions detected", fg="green", bold=True))
        return

    _SEV_COLORS = {"CRITICAL": "red", "WARNING": "yellow", "INFO": "blue"}

    for r in report.regressions:
        color = _SEV_COLORS.get(r.severity.value, "white")
        icon = click.style(f"  {r.severity.value:<8}", fg=color, bold=True)
        click.echo(f"{icon}  [{r.category}] {r.message}")

    click.echo()
    click.echo(
        f"  {len(report.regressions)} regression(s) found — "
        f"max severity: {click.style(report.max_severity.value if report.max_severity else 'NONE', bold=True)}"
    )

    if report.has_critical:
        sys.exit(1)


# ─── sanitize ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default=None,
              help="Output path (default: overwrite source)")
@click.option("--mode", "-m",
              type=click.Choice(["mask", "hash", "remove"], case_sensitive=False),
              default="mask", show_default=True,
              help="Redaction mode: mask=***, hash=sha256[:8], remove=''")
@click.option("--pattern", "-p", "extra_patterns", multiple=True,
              metavar="NAME=REGEX",
              help="Extra redaction pattern (repeatable).  E.g. --pattern mykey=MY_KEY_\\w+")
@click.option("--no-builtin", is_flag=True,
              help="Disable all built-in patterns (use only --pattern)")
@click.option("--scan-only", is_flag=True,
              help="Report found PII without writing any output")
@click.option("--json", "as_json", is_flag=True,
              help="Output scan results as JSON (implies --scan-only)")
def sanitize(
    cassette: str,
    output: str | None,
    mode: str,
    extra_patterns: tuple[str, ...],
    no_builtin: bool,
    scan_only: bool,
    as_json: bool,
) -> None:
    """Redact PII and secrets from CASSETTE.

    By default all built-in patterns are applied (API keys, emails, phone
    numbers, SSNs, credit cards, IP addresses) and matched text is replaced
    with ``***`` (MASK mode).

    Examples:

        evalcraft sanitize run.cassette.json

        evalcraft sanitize run.cassette.json --output clean.json --mode hash

        evalcraft sanitize run.cassette.json --scan-only

        evalcraft sanitize run.cassette.json --pattern "mytoken=TOKEN_[A-Z0-9]+"
    """
    import re as _re
    from evalcraft.sanitize.redactor import CassetteRedactor, RedactMode

    # Parse extra patterns
    parsed_patterns: dict[str, Any] = {}
    for p in extra_patterns:
        if "=" not in p:
            click.echo(
                click.style(f"  error: pattern must be NAME=REGEX, got: {p!r}", fg="red"),
                err=True,
            )
            sys.exit(1)
        p_name, p_regex = p.split("=", 1)
        try:
            parsed_patterns[p_name.strip()] = _re.compile(p_regex.strip())
        except _re.error as exc:
            click.echo(
                click.style(f"  error: invalid regex for pattern {p_name!r}: {exc}", fg="red"),
                err=True,
            )
            sys.exit(1)

    redactor = CassetteRedactor(
        mode=RedactMode(mode),
        patterns=parsed_patterns if parsed_patterns else None,
        use_builtin=not no_builtin,
    )

    c = _load_cassette(cassette)

    if as_json or scan_only:
        findings = redactor.scan(c)
        total = sum(len(v) for v in findings.values())
        if as_json:
            click.echo(json.dumps({"cassette": cassette, "findings": findings, "total": total}, indent=2))
            return
        # human-readable scan report
        click.echo(
            click.style("  scan", fg="cyan", bold=True)
            + f"  {Path(cassette).name}"
        )
        click.echo()
        if not findings:
            click.echo(click.style("  no PII detected", fg="green"))
            return
        for cat, matches in findings.items():
            click.echo(
                click.style(f"  {cat:<22}", fg="yellow")
                + f"  {len(matches)} match(es)"
            )
            for m in matches[:3]:
                preview = m[:60] + ("…" if len(m) > 60 else "")
                click.echo(f"    {click.style(preview, fg='red')}")
            if len(matches) > 3:
                click.echo(f"    … and {len(matches) - 3} more")
        click.echo()
        click.echo(f"  total: {total} sensitive value(s) found in {len(findings)} category(ies)")
        return

    # Redact and save
    out_path = Path(output) if output else Path(cassette)
    clean = redactor.redact(c)
    clean.save(out_path)

    click.echo(
        click.style("  sanitized", fg="green", bold=True)
        + f"  {Path(cassette).name}  →  {out_path}"
    )
    click.echo(f"  mode: {mode}  |  patterns: {len(redactor._patterns)}")


# ─── alert ────────────────────────────────────────────────────────────────────

@cli.group()
def alert() -> None:
    """Send regression alerts to Slack, email, or generic webhooks."""


@alert.command("test")
@click.option("--slack", "slack_url", default=None, metavar="WEBHOOK_URL",
              help="Send test alert to Slack webhook URL")
@click.option("--email", "email_addr", default=None, metavar="ADDRESS",
              help="Send test alert to email address")
@click.option("--smtp-host", default="localhost", show_default=True, help="SMTP host")
@click.option("--smtp-port", default=587, show_default=True, type=int, help="SMTP port")
@click.option("--smtp-user", default="", help="SMTP username")
@click.option("--smtp-password", default="", help="SMTP password")
@click.option("--from", "sender", default="evalcraft@localhost", show_default=True,
              help="Sender email address")
def alert_test(
    slack_url: str | None,
    email_addr: str | None,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    sender: str,
) -> None:
    """Send a test alert to verify your alert configuration.

    Examples:

        evalcraft alert test --slack https://hooks.slack.com/services/...

        evalcraft alert test --email you@example.com --smtp-host smtp.example.com
    """
    from evalcraft.alerts.email import EmailAlert, SMTPConfig
    from evalcraft.alerts.slack import SlackAlert
    from evalcraft.regression.detector import Regression, RegressionReport, Severity

    if not slack_url and not email_addr:
        click.echo(
            click.style("  error: specify --slack and/or --email", fg="red"), err=True
        )
        sys.exit(1)

    # Build a synthetic test report
    report = RegressionReport(golden_name="test_cassette")
    report.regressions = [
        Regression(
            category="cost_increase",
            severity=Severity.CRITICAL,
            message="Cost increased 3.50x ($0.0010 -> $0.0035)",
            golden_value=0.001,
            current_value=0.0035,
            metadata={"ratio": 3.5},
        ),
        Regression(
            category="token_bloat",
            severity=Severity.WARNING,
            message="Token usage increased 1.40x (1000 -> 1400)",
            golden_value=1000,
            current_value=1400,
            metadata={"ratio": 1.4},
        ),
    ]

    if slack_url:
        preview = slack_url[:50] + ("…" if len(slack_url) > 50 else "")
        click.echo(click.style("  testing", fg="cyan", bold=True) + f"  Slack: {preview}")
        try:
            SlackAlert(webhook_url=slack_url).send_regression(report)
            click.echo(click.style("  sent", fg="green", bold=True) + "     Slack test alert delivered")
        except Exception as exc:
            click.echo(click.style(f"  error: {exc}", fg="red"), err=True)
            sys.exit(1)

    if email_addr:
        click.echo(click.style("  testing", fg="cyan", bold=True) + f"  email: {email_addr}")
        try:
            smtp_cfg = SMTPConfig(
                host=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_password,
            )
            EmailAlert(smtp=smtp_cfg, sender=sender).send_regression(report, [email_addr])
            click.echo(
                click.style("  sent", fg="green", bold=True) + f"     test email → {email_addr}"
            )
        except Exception as exc:
            click.echo(click.style(f"  error: {exc}", fg="red"), err=True)
            sys.exit(1)


# ─── cloud ────────────────────────────────────────────────────────────────────

@cli.group()
def cloud() -> None:
    """Push cassettes and golden sets to the Evalcraft cloud dashboard."""


@cloud.command("login")
@click.option("--api-key", prompt="API key", hide_input=True,
              help="Your Evalcraft API key (ec_...)")
@click.option("--url", default="https://api.evalcraft.dev/v1",
              help="Override API base URL")
def cloud_login(api_key: str, url: str) -> None:
    """Save your API key to ~/.evalcraft/config.json.

    Example:

        evalcraft cloud login --api-key ec_xxxxxxxxxxxx
    """
    from evalcraft.cloud.client import EvalcraftCloud
    EvalcraftCloud.save_config(api_key=api_key, base_url=url)
    click.echo(click.style("  saved", fg="green", bold=True) + "  ~/.evalcraft/config.json")
    click.echo("  API key stored.  Run `evalcraft cloud status` to verify.")


@cloud.command("status")
def cloud_status() -> None:
    """Check connection to the Evalcraft dashboard.

    Example:

        evalcraft cloud status
    """
    from evalcraft.cloud.client import EvalcraftCloud
    client = EvalcraftCloud()
    if not client.api_key:
        click.echo(click.style("  not logged in", fg="yellow", bold=True))
        click.echo("  Run `evalcraft cloud login` to set your API key.")
        return

    click.echo(click.style("  checking", fg="cyan") + f"  {client.base_url}")
    result = client.check_connection()
    if result["ok"]:
        click.echo(click.style("  connected", fg="green", bold=True))
        if result.get("detail"):
            click.echo(f"  {result['detail']}")
    else:
        click.echo(click.style("  unreachable", fg="red", bold=True))
        click.echo(f"  {result['message']}")

    queued = client.queue_size()
    if queued:
        click.echo(f"  offline queue: {queued} item(s) pending — run `evalcraft cloud flush`")


@cloud.command("upload")
@click.argument("cassette", type=click.Path(exists=True, dir_okay=False))
@click.option("--golden", is_flag=True, help="Treat file as a golden set instead of a cassette")
def cloud_upload(cassette: str, golden: bool) -> None:
    """Upload CASSETTE (or a golden-set file) to the dashboard.

    Example:

        evalcraft cloud upload cassettes/run1.json
        evalcraft cloud upload weather.golden.json --golden
    """
    from evalcraft.cloud.client import EvalcraftCloud, CloudUploadError

    client = EvalcraftCloud()
    if not client.api_key:
        click.echo(click.style("  error", fg="red", bold=True) + "  not logged in.")
        click.echo("  Run `evalcraft cloud login` first.")
        sys.exit(1)

    path = Path(cassette)
    click.echo(click.style("  uploading", fg="cyan", bold=True) + f"  {path.name}")

    try:
        if golden:
            from evalcraft.golden.manager import GoldenSet
            gs = GoldenSet.load(path)
            resp = client.upload_golden(gs)
            click.echo(click.style("  uploaded", fg="green", bold=True)
                       + f"  golden set '{gs.name}' v{gs.version}")
        else:
            c = _load_cassette(cassette)
            resp = client.upload(c)
            click.echo(click.style("  uploaded", fg="green", bold=True)
                       + f"  cassette '{c.name or c.id}'")
        if resp.get("url"):
            click.echo(f"  dashboard: {resp['url']}")
    except CloudUploadError as exc:
        click.echo(click.style("  failed", fg="red", bold=True) + f"  {exc}")
        click.echo("  Saved to offline queue — run `evalcraft cloud flush` to retry.")
        sys.exit(1)


@cloud.command("flush")
def cloud_flush() -> None:
    """Retry all items in the offline queue.

    Items are queued automatically when uploads fail (network error,
    API unreachable).

    Example:

        evalcraft cloud flush
    """
    from evalcraft.cloud.client import EvalcraftCloud

    client = EvalcraftCloud()
    queued = client.queue_size()
    if queued == 0:
        click.echo(click.style("  empty", fg="green") + "  offline queue is empty.")
        return

    click.echo(click.style("  flushing", fg="cyan", bold=True) + f"  {queued} queued item(s)")
    succeeded, failed = client.flush_queue()
    if failed == 0:
        click.echo(click.style("  done", fg="green", bold=True)
                   + f"  {succeeded} item(s) uploaded successfully.")
    else:
        click.echo(click.style("  partial", fg="yellow", bold=True)
                   + f"  {succeeded} uploaded, {failed} still pending.")
        sys.exit(1)
