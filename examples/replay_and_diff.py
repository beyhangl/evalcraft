"""replay_and_diff.py — Replay cassettes and detect regressions with diff.

Shows how to:
1. Build two cassettes (baseline + modified run)
2. Replay with tool result overrides
3. Diff the two runs to catch regressions
4. Use step-by-step replay for debugging

Run:
    python examples/replay_and_diff.py
"""

from pathlib import Path

from evalcraft import CaptureContext, MockLLM, MockTool, replay
from evalcraft.replay.engine import ReplayEngine, ReplayDiff
from evalcraft import (
    assert_tool_called,
    assert_tool_order,
    assert_output_contains,
    assert_cost_under,
)


# ---------------------------------------------------------------------------
# Build cassettes
# ---------------------------------------------------------------------------

def build_baseline_cassette(path: Path) -> None:
    """Capture a baseline run: good weather, normal flow."""
    llm = MockLLM()
    llm.add_response("*", "It's 18°C and partly cloudy in Paris today.")

    weather = MockTool("get_weather")
    weather.returns({"temp_c": 18, "condition": "partly cloudy"})

    with CaptureContext(
        name="weather_baseline",
        agent_name="weather_agent",
        save_path=path,
    ) as ctx:
        ctx.record_input("What's the weather in Paris?")
        result = weather.call(city="Paris")
        prompt = f"Weather data: {result}. Write a short answer."
        response = llm.complete(prompt)
        ctx.record_output(response.content)

    print(f"Built baseline cassette: {path}")
    print(f"  Tool sequence: {ctx.cassette.get_tool_sequence()}")
    print(f"  Output: {ctx.cassette.output_text}")


def build_regression_cassette(path: Path) -> None:
    """Simulate a regression: agent now calls two tools instead of one."""
    llm = MockLLM()
    llm.add_response("*", "It's 18°C in Paris. Tomorrow: sunny 22°C.")

    weather = MockTool("get_weather")
    weather.returns({"temp_c": 18, "condition": "partly cloudy"})

    forecast = MockTool("get_forecast")  # NEW: agent started calling this too
    forecast.returns({"tomorrow": "sunny", "high_c": 22})

    with CaptureContext(
        name="weather_regression",
        agent_name="weather_agent",
        save_path=path,
    ) as ctx:
        ctx.record_input("What's the weather in Paris?")
        result = weather.call(city="Paris")
        fc_result = forecast.call(city="Paris", days=1)
        prompt = f"Weather: {result}. Forecast: {fc_result}. Write a short answer."
        response = llm.complete(prompt)
        ctx.record_output(response.content)

    print(f"\nBuilt regression cassette: {path}")
    print(f"  Tool sequence: {ctx.cassette.get_tool_sequence()}")
    print(f"  Output: {ctx.cassette.output_text}")


# ---------------------------------------------------------------------------
# Demo 1: Simple replay
# ---------------------------------------------------------------------------

def demo_simple_replay(cassette_path: Path) -> None:
    print("\n" + "=" * 60)
    print("Demo 1: Simple replay")
    print("=" * 60)

    run = replay(cassette_path)

    print(f"Replayed: {run.replayed}")
    print(f"Output:   {run.cassette.output_text}")
    print(f"Spans:    {len(run.cassette.spans)}")

    assert run.replayed is True
    assert len(run.cassette.spans) > 0
    print("PASS: replay works")


# ---------------------------------------------------------------------------
# Demo 2: Replay with tool override
# ---------------------------------------------------------------------------

def demo_tool_override(cassette_path: Path) -> None:
    print("\n" + "=" * 60)
    print("Demo 2: Replay with tool result override")
    print("=" * 60)

    # Replay but pretend the weather changed to a storm
    engine = ReplayEngine(cassette_path)
    engine.override_tool_result(
        "get_weather",
        {"temp_c": 4, "condition": "heavy rain and thunderstorms"},
    )
    run = engine.run()

    # Check that the override was applied in the span
    tool_spans = run.cassette.get_tool_calls()
    if tool_spans:
        overridden = tool_spans[0]
        print(f"Overridden tool result: {overridden.tool_result}")
        assert overridden.tool_result["condition"] == "heavy rain and thunderstorms"

    print("PASS: tool override applied")


# ---------------------------------------------------------------------------
# Demo 3: LLM response override
# ---------------------------------------------------------------------------

def demo_llm_override(cassette_path: Path) -> None:
    print("\n" + "=" * 60)
    print("Demo 3: Replay with LLM response override")
    print("=" * 60)

    engine = ReplayEngine(cassette_path)
    engine.override_llm_response(0, "Bonjour! Il fait beau à Paris aujourd'hui.")
    run = engine.run()

    llm_spans = run.cassette.get_llm_calls()
    if llm_spans:
        overridden_output = llm_spans[0].output
        print(f"Overridden LLM output: {overridden_output}")

    print("PASS: LLM override applied")


# ---------------------------------------------------------------------------
# Demo 4: Regression detection with diff
# ---------------------------------------------------------------------------

def demo_diff(baseline_path: Path, regression_path: Path) -> None:
    print("\n" + "=" * 60)
    print("Demo 4: Regression detection with diff")
    print("=" * 60)

    engine = ReplayEngine(baseline_path)
    from evalcraft.core.models import Cassette
    diff = engine.diff(regression_path)

    print(f"Has changes: {diff.has_changes}")
    print(f"Tool sequence changed: {diff.tool_sequence_changed}")
    if diff.tool_sequence_changed:
        print(f"  Before: {diff.old_tool_sequence}")
        print(f"  After:  {diff.new_tool_sequence}")

    print(f"Output changed: {diff.output_changed}")
    print(f"Token count changed: {diff.token_count_changed}")
    if diff.token_count_changed:
        print(f"  Before: {diff.old_tokens} tokens")
        print(f"  After:  {diff.new_tokens} tokens")

    print("\nDiff summary:")
    print(diff.summary())

    # In a real CI gate you'd fail the build if unexpected changes exist
    if diff.tool_sequence_changed:
        print("\nWARN: Tool sequence changed — new tool was added!")
    if diff.output_changed:
        print("WARN: Output text changed — check if this is intentional")

    print("PASS: diff completed")


# ---------------------------------------------------------------------------
# Demo 5: Step-by-step replay for debugging
# ---------------------------------------------------------------------------

def demo_step_by_step(cassette_path: Path) -> None:
    print("\n" + "=" * 60)
    print("Demo 5: Step-by-step replay")
    print("=" * 60)

    engine = ReplayEngine(cassette_path)
    step_num = 0

    while True:
        span = engine.step()
        if span is None:
            break

        step_num += 1
        print(f"  Step {step_num}: [{span.kind.value}] {span.name}")
        if span.tool_name:
            print(f"    tool_args: {span.tool_args}")
            print(f"    tool_result: {span.tool_result}")

    print(f"PASS: stepped through {step_num} spans")


# ---------------------------------------------------------------------------
# Demo 6: Assertions on replayed run
# ---------------------------------------------------------------------------

def demo_assertions(cassette_path: Path) -> None:
    print("\n" + "=" * 60)
    print("Demo 6: Eval assertions on replayed cassette")
    print("=" * 60)

    run = replay(cassette_path)
    c = run.cassette

    checks = [
        assert_tool_called(c, "get_weather"),
        assert_tool_called(c, "get_weather", with_args={"city": "Paris"}),
        assert_tool_order(c, ["get_weather"]),
        assert_output_contains(c, "18"),
        assert_cost_under(c, max_usd=0.01),
    ]

    all_passed = True
    for r in checks:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name}")
        if not r.passed:
            print(f"         {r.message}")
            all_passed = False

    if all_passed:
        print("\nAll assertions passed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    cassette_dir = Path("tests/cassettes")
    cassette_dir.mkdir(parents=True, exist_ok=True)

    baseline_path = cassette_dir / "weather_baseline.json"
    regression_path = cassette_dir / "weather_regression.json"

    print("Building cassettes...")
    build_baseline_cassette(baseline_path)
    build_regression_cassette(regression_path)

    demo_simple_replay(baseline_path)
    demo_tool_override(baseline_path)
    demo_llm_override(baseline_path)
    demo_diff(baseline_path, regression_path)
    demo_step_by_step(baseline_path)
    demo_assertions(baseline_path)

    print("\n" + "=" * 60)
    print("All demos complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
