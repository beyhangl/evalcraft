"""basic_capture.py — Capture an agent run into a cassette.

This example shows how to use CaptureContext to record every LLM call,
tool invocation, and agent decision into a replayable cassette file.

Run:
    python examples/basic_capture.py
"""

from pathlib import Path
from evalcraft import CaptureContext, assert_tool_called, assert_cost_under


def simulate_weather_agent(user_query: str, ctx: CaptureContext) -> str:
    """A simple simulated agent that answers weather questions.

    In a real integration you'd replace these ctx.record_* calls with
    the evalcraft OpenAI/LangChain adapter, which hooks them automatically.
    """
    ctx.record_input(user_query)

    # Simulate tool call: get_weather
    weather_data = {"city": "Paris", "temp_c": 18, "condition": "partly cloudy"}
    ctx.record_tool_call(
        tool_name="get_weather",
        args={"city": "Paris"},
        result=weather_data,
        duration_ms=320.0,
    )

    # Simulate a follow-up tool call: get_forecast
    forecast_data = {"tomorrow": "sunny", "high_c": 22}
    ctx.record_tool_call(
        tool_name="get_forecast",
        args={"city": "Paris", "days": 1},
        result=forecast_data,
        duration_ms=280.0,
    )

    # Simulate LLM synthesizing the final answer
    prompt = (
        f"User asked: {user_query}\n"
        f"Current weather: {weather_data}\n"
        f"Forecast: {forecast_data}\n"
        "Write a concise answer."
    )
    answer = "It's 18°C and partly cloudy in Paris today. Tomorrow looks sunny with a high of 22°C."
    ctx.record_llm_call(
        model="gpt-4.1-mini",
        input=prompt,
        output=answer,
        duration_ms=750.0,
        prompt_tokens=95,
        completion_tokens=28,
        cost_usd=0.00023,
    )

    ctx.record_output(answer)
    return answer


def main():
    cassette_path = Path("tests/cassettes/weather_agent.json")
    cassette_path.parent.mkdir(parents=True, exist_ok=True)

    print("Capturing agent run...")
    with CaptureContext(
        name="weather_agent_test",
        agent_name="weather_agent",
        framework="custom",
        save_path=cassette_path,
    ) as ctx:
        answer = simulate_weather_agent("What's the weather in Paris today?", ctx)

    cassette = ctx.cassette

    print(f"\nCaptured cassette: {cassette.name}")
    print(f"  Spans:       {len(cassette.spans)}")
    print(f"  Tool calls:  {cassette.tool_call_count}")
    print(f"  LLM calls:   {cassette.llm_call_count}")
    print(f"  Tokens:      {cassette.total_tokens}")
    print(f"  Cost:        ${cassette.total_cost_usd:.5f}")
    print(f"  Fingerprint: {cassette.fingerprint}")
    print(f"  Saved to:    {cassette_path}")
    print(f"\nAgent output: {answer}")

    # Spot-check the cassette with scorers
    r1 = assert_tool_called(cassette, "get_weather")
    r2 = assert_tool_called(cassette, "get_forecast", with_args={"city": "Paris"})
    r3 = assert_cost_under(cassette, max_usd=0.01)

    print("\nQuick assertions:")
    for result in [r1, r2, r3]:
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {result.name}")
        if not result.passed:
            print(f"         {result.message}")


if __name__ == "__main__":
    main()
