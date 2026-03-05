import {
  Cassette,
  AgentRun,
  AssertionResult,
  EvalResult,
} from '../core/models.js';

function getCassette(obj: Cassette | AgentRun): Cassette {
  if (obj instanceof AgentRun) return obj.cassette;
  return obj;
}

// ── Tool assertions ───────────────────────────────────────────────────────────

export function assertToolCalled(
  cassette: Cassette | AgentRun,
  toolName: string,
  options: {
    times?: number;
    withArgs?: Record<string, unknown>;
    before?: string;
    after?: string;
  } = {},
): AssertionResult {
  const c = getCassette(cassette);
  const toolCalls = c.getToolCalls().filter((s) => s.tool_name === toolName);

  if (toolCalls.length === 0) {
    return new AssertionResult({
      name: `assertToolCalled(${toolName})`,
      passed: false,
      expected: toolName,
      actual: c.getToolSequence(),
      message: `Tool '${toolName}' was never called. Called tools: ${JSON.stringify(c.getToolSequence())}`,
    });
  }

  if (options.times != null && toolCalls.length !== options.times) {
    return new AssertionResult({
      name: `assertToolCalled(${toolName}, times=${options.times})`,
      passed: false,
      expected: options.times,
      actual: toolCalls.length,
      message: `Tool '${toolName}' was called ${toolCalls.length} times, expected ${options.times}`,
    });
  }

  if (options.withArgs) {
    const matched = toolCalls.some((tc) =>
      Object.entries(options.withArgs!).every(
        ([k, v]) => tc.tool_args != null && tc.tool_args[k] === v,
      ),
    );
    if (!matched) {
      return new AssertionResult({
        name: `assertToolCalled(${toolName}, withArgs=...)`,
        passed: false,
        expected: options.withArgs,
        actual: toolCalls.map((tc) => tc.tool_args),
        message: `Tool '${toolName}' was never called with args: ${JSON.stringify(options.withArgs)}`,
      });
    }
  }

  if (options.before) {
    const seq = c.getToolSequence();
    const toolIdx = seq.indexOf(toolName);
    const beforeIdx = seq.indexOf(options.before);
    if (toolIdx === -1 || beforeIdx === -1 || toolIdx >= beforeIdx) {
      return new AssertionResult({
        name: `assertToolCalled(${toolName}, before=${options.before})`,
        passed: false,
        expected: `${toolName} before ${options.before}`,
        actual: seq,
        message:
          toolIdx === -1 || beforeIdx === -1
            ? `Tool not found in sequence`
            : `Tool '${toolName}' was not called before '${options.before}'. Sequence: ${JSON.stringify(seq)}`,
      });
    }
  }

  if (options.after) {
    const seq = c.getToolSequence();
    const toolIdx = seq.indexOf(toolName);
    const afterIdx = seq.indexOf(options.after);
    if (toolIdx === -1 || afterIdx === -1 || toolIdx <= afterIdx) {
      return new AssertionResult({
        name: `assertToolCalled(${toolName}, after=${options.after})`,
        passed: false,
        expected: `${toolName} after ${options.after}`,
        actual: seq,
        message:
          toolIdx === -1 || afterIdx === -1
            ? `Tool not found in sequence`
            : `Tool '${toolName}' was not called after '${options.after}'. Sequence: ${JSON.stringify(seq)}`,
      });
    }
  }

  return new AssertionResult({
    name: `assertToolCalled(${toolName})`,
    passed: true,
    expected: toolName,
    actual: toolName,
  });
}

export function assertToolOrder(
  cassette: Cassette | AgentRun,
  expectedOrder: string[],
  strict = false,
): AssertionResult {
  const c = getCassette(cassette);
  const actual = c.getToolSequence();

  if (strict) {
    if (JSON.stringify(actual) !== JSON.stringify(expectedOrder)) {
      return new AssertionResult({
        name: 'assertToolOrder(strict)',
        passed: false,
        expected: expectedOrder,
        actual,
        message: `Tool sequence mismatch.\nExpected: ${JSON.stringify(expectedOrder)}\nActual: ${JSON.stringify(actual)}`,
      });
    }
  } else {
    const iter = actual[Symbol.iterator]();
    for (const tool of expectedOrder) {
      let found = false;
      for (const next of iter) {
        if (next === tool) {
          found = true;
          break;
        }
      }
      if (!found) {
        return new AssertionResult({
          name: 'assertToolOrder',
          passed: false,
          expected: expectedOrder,
          actual,
          message: `Expected tool '${tool}' not found in order. Sequence: ${JSON.stringify(actual)}`,
        });
      }
    }
  }

  return new AssertionResult({
    name: 'assertToolOrder',
    passed: true,
    expected: expectedOrder,
    actual,
  });
}

export function assertNoToolCalled(
  cassette: Cassette | AgentRun,
  toolName: string,
): AssertionResult {
  const c = getCassette(cassette);
  const calls = c.getToolCalls().filter((s) => s.tool_name === toolName);
  if (calls.length > 0) {
    return new AssertionResult({
      name: `assertNoToolCalled(${toolName})`,
      passed: false,
      expected: `${toolName} not called`,
      actual: `Called ${calls.length} times`,
      message: `Tool '${toolName}' was called ${calls.length} times, expected 0`,
    });
  }
  return new AssertionResult({
    name: `assertNoToolCalled(${toolName})`,
    passed: true,
  });
}

// ── Output assertions ─────────────────────────────────────────────────────────

export function assertOutputContains(
  cassette: Cassette | AgentRun,
  substring: string,
  caseSensitive = true,
): AssertionResult {
  const c = getCassette(cassette);
  const output = c.output_text;
  const passed = caseSensitive
    ? output.includes(substring)
    : output.toLowerCase().includes(substring.toLowerCase());

  return new AssertionResult({
    name: `assertOutputContains(${JSON.stringify(substring)})`,
    passed,
    expected: substring,
    actual: passed ? substring : output.slice(0, 200),
    message: passed ? '' : `Output does not contain '${substring}'`,
  });
}

export function assertOutputMatches(
  cassette: Cassette | AgentRun,
  pattern: string,
): AssertionResult {
  const c = getCassette(cassette);
  const output = c.output_text;
  const match = new RegExp(pattern).exec(output);

  return new AssertionResult({
    name: `assertOutputMatches(${JSON.stringify(pattern)})`,
    passed: match != null,
    expected: pattern,
    actual: match ? match[0] : output.slice(0, 200),
    message: match ? '' : `Output does not match pattern '${pattern}'`,
  });
}

// ── Cost and performance assertions ───────────────────────────────────────────

export function assertCostUnder(
  cassette: Cassette | AgentRun,
  maxUsd: number,
): AssertionResult {
  const c = getCassette(cassette);
  c.computeMetrics();
  return new AssertionResult({
    name: `assertCostUnder($${maxUsd})`,
    passed: c.total_cost_usd <= maxUsd,
    expected: maxUsd,
    actual: c.total_cost_usd,
    message:
      c.total_cost_usd <= maxUsd
        ? ''
        : `Cost $${c.total_cost_usd.toFixed(4)} exceeds limit $${maxUsd.toFixed(4)}`,
  });
}

export function assertLatencyUnder(
  cassette: Cassette | AgentRun,
  maxMs: number,
): AssertionResult {
  const c = getCassette(cassette);
  c.computeMetrics();
  return new AssertionResult({
    name: `assertLatencyUnder(${maxMs}ms)`,
    passed: c.total_duration_ms <= maxMs,
    expected: maxMs,
    actual: c.total_duration_ms,
    message:
      c.total_duration_ms <= maxMs
        ? ''
        : `Latency ${c.total_duration_ms.toFixed(1)}ms exceeds limit ${maxMs.toFixed(1)}ms`,
  });
}

export function assertTokenCountUnder(
  cassette: Cassette | AgentRun,
  maxTokens: number,
): AssertionResult {
  const c = getCassette(cassette);
  c.computeMetrics();
  return new AssertionResult({
    name: `assertTokenCountUnder(${maxTokens})`,
    passed: c.total_tokens <= maxTokens,
    expected: maxTokens,
    actual: c.total_tokens,
    message:
      c.total_tokens <= maxTokens
        ? ''
        : `Token count ${c.total_tokens} exceeds limit ${maxTokens}`,
  });
}

// ── Evaluator ─────────────────────────────────────────────────────────────────

export class Evaluator {
  private _checks: Array<() => AssertionResult> = [];

  add(
    assertionFn: (...args: unknown[]) => AssertionResult,
    ...args: unknown[]
  ): this {
    this._checks.push(() => assertionFn(...args));
    return this;
  }

  run(): EvalResult {
    const results = this._checks.map((fn) => fn());
    const allPassed = results.every((r) => r.passed);
    const score = results.length
      ? results.filter((r) => r.passed).length / results.length
      : 1.0;
    return new EvalResult({ passed: allPassed, score, assertions: results });
  }
}
