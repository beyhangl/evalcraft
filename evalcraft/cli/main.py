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
def replay(cassette: str, verbose: bool) -> None:
    """Replay CASSETTE and display the results.

    Feeds recorded responses back through the replay engine without making
    any real LLM API calls.

    Example:

        evalcraft replay cassettes/run1.json --verbose
    """
    c = _load_cassette(cassette)
    engine = ReplayEngine(c)
    run = engine.run()
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
