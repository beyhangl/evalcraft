# evalcraft assertions

All take a `Cassette` or the `AgentRun` returned by `replay()` as the first
argument and return an `AssertionResult` with `.passed` and `.message`.

## Offline — no model call, $0, deterministic

| Assertion | Checks |
|---|---|
| `assert_tool_called(run, name, times=None, with_args=None, before=None, after=None)` | A tool was called (optionally N times, with args, before/after another) |
| `assert_no_tool_called(run, name)` | A tool was never called |
| `assert_tool_order(run, tools, strict=False)` | Tools appear in this order (subsequence unless `strict`) |
| `assert_tool_trajectory(run, tools, mode="strict")` | `strict` exact list · `unordered` same tools and counts · `subset` no unexpected tools · `superset` all required tools |
| `assert_tool_args_match_schema(run, name, schema, which="all")` | Recorded tool arguments match a JSON Schema (dict, `.json` path, or pydantic model) |
| `assert_output_contains(run, text)` / `assert_output_matches(run, regex)` | Final output text |
| `assert_output_json(run)` / `assert_output_json_schema(run, schema)` | Output is JSON / matches a schema |
| `assert_output_has_keys`, `assert_output_field`, `assert_output_value_in`, `assert_output_value_in_range` | Fields in JSON output |
| `assert_match_groups(run, regex, ...)` | Regex capture groups in the output |
| `assert_no_loops(run, similarity=1.0)` / `assert_no_repeated_tool_calls(run)` | The agent did not repeat the same tool call or output |
| `assert_cost_under(run, max_usd)` | Total cost budget (cache reads/writes priced separately) |
| `assert_token_count_under(run, max_tokens)` | Token budget |
| `assert_latency_under(run, max_ms)` | Latency budget |

## Live — calls a real model, needs an API key, costs money

`assert_output_semantic`, `assert_factual_consistency`, `assert_tone`,
`assert_custom_criteria`, `assert_faithfulness`, `assert_context_relevance`,
`assert_answer_relevance`, `assert_context_recall`, `assert_no_hallucination`,
`pairwise_compare`, `pairwise_rank`. Run these on a schedule, not per commit.
Use `eval_n(...)` to repeat one and get a pass rate with a confidence interval.
