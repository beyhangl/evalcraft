"""Auto-generate pytest test files from cassettes.

Reads a cassette and emits a complete, runnable test file with assertions
for tool calls, output content, cost, tokens, and tool ordering.

Usage::

    evalcraft generate-tests tests/cassettes/weather.json
    evalcraft generate-tests tests/cassettes/weather.json --output tests/test_weather_auto.py
"""

from __future__ import annotations

import re

from evalcraft.core.models import Cassette
from evalcraft.eval.scorers.structured import _extract_json


def generate_test_code(cassette: Cassette, cassette_path: str) -> str:
    """Generate a complete pytest file from a cassette.

    Args:
        cassette: The loaded cassette to generate tests from.
        cassette_path: The path to the cassette file (used in generated code).

    Returns:
        A string containing valid Python test code.
    """
    cassette.compute_metrics()

    tool_sequence = cassette.get_tool_sequence()
    tool_calls = cassette.get_tool_calls()
    unique_tools = list(dict.fromkeys(tool_sequence))  # Preserve order, deduplicate
    has_output = bool(cassette.output_text)
    if has_output:
        json_ok, json_value, _ = _extract_json(cassette.output_text)
    else:
        json_ok, json_value = False, None
    output_is_json_object = json_ok and isinstance(json_value, dict)
    has_cost = cassette.total_cost_usd > 0
    has_tokens = cassette.total_tokens > 0
    has_latency = cassette.total_duration_ms > 0

    # Build import set based on what we'll assert
    imports = ["replay"]
    if tool_calls:
        imports.append("assert_tool_called")
    if len(unique_tools) > 1:
        imports.append("assert_tool_order")
    if has_output:
        imports.extend(["assert_output_contains", "assert_output_matches"])
    if output_is_json_object:
        imports.extend(["assert_output_json", "assert_output_has_keys"])
    if has_cost:
        imports.append("assert_cost_under")
    if has_tokens:
        imports.append("assert_token_count_under")
    if has_latency:
        imports.append("assert_latency_under")

    # Sanitise cassette name for use as a Python identifier
    safe_name = re.sub(r"[^a-zA-Z0-9]", "_", cassette.name or "agent")
    safe_name = re.sub(r"_+", "_", safe_name).strip("_") or "agent"

    lines: list[str] = []

    # Header
    lines.append(f'"""Auto-generated tests for cassette: {cassette.name or cassette_path}')
    lines.append("")
    lines.append(f"Agent: {cassette.agent_name or 'unknown'}")
    lines.append(f"Framework: {cassette.framework or 'unknown'}")
    lines.append(f"Tool calls: {len(tool_calls)}")
    lines.append(f"LLM calls: {cassette.llm_call_count}")
    lines.append(f"Total cost: ${cassette.total_cost_usd:.4f}")
    lines.append(f"Total tokens: {cassette.total_tokens}")
    lines.append('"""')
    lines.append("")
    lines.append(f"from evalcraft import {', '.join(imports)}")
    lines.append("")
    lines.append("")

    # Cassette path constant
    lines.append(f'CASSETTE_PATH = "{cassette_path}"')
    lines.append("")
    lines.append("")

    # Helper to load replay
    lines.append("def _replay():")
    lines.append('    """Replay the cassette — zero API calls, zero cost."""')
    lines.append("    return replay(CASSETTE_PATH)")
    lines.append("")
    lines.append("")

    # Test: each tool was called
    for tool_name in unique_tools:
        count = tool_sequence.count(tool_name)
        func_name = re.sub(r"[^a-zA-Z0-9]", "_", tool_name)
        lines.append(f"def test_{safe_name}_calls_{func_name}():")
        lines.append(f'    """Assert that {tool_name} was called."""')
        lines.append("    run = _replay()")
        lines.append(f'    result = assert_tool_called(run, "{tool_name}", times={count})')
        lines.append("    assert result.passed, result.message")
        lines.append("")
        lines.append("")

    # Test: tool call with specific args
    for span in tool_calls:
        if span.tool_args and span.tool_name:
            func_name = re.sub(r"[^a-zA-Z0-9]", "_", span.tool_name)
            lines.append(f"def test_{safe_name}_{func_name}_args():")
            lines.append(f'    """Assert that {span.tool_name} was called with expected args."""')
            lines.append("    run = _replay()")
            lines.append("    result = assert_tool_called(")
            lines.append(f'        run, "{span.tool_name}",')
            lines.append(f"        with_args={span.tool_args!r},")
            lines.append("    )")
            lines.append("    assert result.passed, result.message")
            lines.append("")
            lines.append("")
            break  # Only generate one args test per tool to avoid bloat

    # Test: tool ordering
    if len(unique_tools) > 1:
        lines.append(f"def test_{safe_name}_tool_order():")
        lines.append('    """Assert tools were called in the expected order."""')
        lines.append("    run = _replay()")
        lines.append(f"    result = assert_tool_order(run, {unique_tools!r})")
        lines.append("    assert result.passed, result.message")
        lines.append("")
        lines.append("")

    # Test: output contains key terms
    if has_output:
        # Extract a few meaningful words from the output for contains checks
        words = _extract_key_terms(cassette.output_text)
        if words:
            term = words[0]
            lines.append(f"def test_{safe_name}_output_contains_key_term():")
            lines.append('    """Assert the output contains an expected term."""')
            lines.append("    run = _replay()")
            lines.append(f"    result = assert_output_contains(run, {term!r})")
            lines.append("    assert result.passed, result.message")
            lines.append("")
            lines.append("")

        # Test: output is not empty
        lines.append(f"def test_{safe_name}_output_not_empty():")
        lines.append('    """Assert the agent produced non-empty output."""')
        lines.append("    run = _replay()")
        lines.append('    result = assert_output_matches(run, r".+")')
        lines.append("    assert result.passed, result.message")
        lines.append("")
        lines.append("")

        # Test: structured output — the recorded output is JSON, so lock its shape
        # deterministically (valid JSON + the same top-level keys).
        if output_is_json_object and json_value:
            top_keys = list(json_value.keys())[:8]
            lines.append(f"def test_{safe_name}_output_is_json():")
            lines.append('    """Assert the output is valid structured JSON ($0, offline)."""')
            lines.append("    run = _replay()")
            lines.append("    result = assert_output_json(run)")
            lines.append("    assert result.passed, result.message")
            lines.append("")
            lines.append("")
            lines.append(f"def test_{safe_name}_output_shape():")
            lines.append('    """Lock the shape of the structured output (top-level keys)."""')
            lines.append("    run = _replay()")
            lines.append(f"    result = assert_output_has_keys(run, {top_keys!r})")
            lines.append("    assert result.passed, result.message")
            lines.append("")
            lines.append("")

    # Test: cost budget
    if has_cost:
        # Set budget to 2x actual cost — reasonable headroom
        budget = round(cassette.total_cost_usd * 2, 4) or 0.01
        lines.append(f"def test_{safe_name}_cost_budget():")
        lines.append('    """Assert the run stays within cost budget."""')
        lines.append("    run = _replay()")
        lines.append(f"    result = assert_cost_under(run, max_usd={budget})")
        lines.append("    assert result.passed, result.message")
        lines.append("")
        lines.append("")

    # Test: token budget
    if has_tokens:
        # Set budget to 2x actual tokens
        token_budget = cassette.total_tokens * 2
        lines.append(f"def test_{safe_name}_token_budget():")
        lines.append('    """Assert the run stays within token budget."""')
        lines.append("    run = _replay()")
        lines.append(f"    result = assert_token_count_under(run, max_tokens={token_budget})")
        lines.append("    assert result.passed, result.message")
        lines.append("")
        lines.append("")

    # Test: latency budget
    if has_latency:
        # Set budget to 3x actual latency
        latency_budget = round(cassette.total_duration_ms * 3, 0)
        lines.append(f"def test_{safe_name}_latency_budget():")
        lines.append('    """Assert the run stays within latency budget."""')
        lines.append("    run = _replay()")
        lines.append(f"    result = assert_latency_under(run, max_ms={latency_budget})")
        lines.append("    assert result.passed, result.message")
        lines.append("")

    return "\n".join(lines)


def _extract_key_terms(text: str, max_terms: int = 3) -> list[str]:
    """Extract meaningful terms from output text for use in assertions.

    Picks the longest non-stopword tokens as likely-meaningful terms.
    """
    _STOPWORDS = {
        "the", "a", "an", "is", "it", "in", "to", "and", "of", "for",
        "on", "at", "by", "or", "as", "be", "was", "are", "has", "had",
        "its", "with", "that", "this", "from", "not", "but", "your",
        "you", "we", "they", "them", "their", "our", "can", "will",
        "just", "been", "have", "all", "very", "also", "than", "more",
        "most", "some", "any", "no", "so", "if", "do", "did", "does",
    }
    # Extract words 3+ chars, lowercase, strip punctuation
    words = re.findall(r"[a-zA-Z]{3,}", text)
    unique = []
    seen: set[str] = set()
    for w in words:
        low = w.lower()
        if low not in _STOPWORDS and low not in seen:
            seen.add(low)
            unique.append(w)
    # Sort by length descending — longer words are more specific
    unique.sort(key=len, reverse=True)
    return unique[:max_terms]
