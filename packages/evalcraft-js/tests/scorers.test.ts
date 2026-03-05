import { describe, it, expect } from 'vitest';
import {
  Cassette,
  Span,
  AgentRun,
  SpanKind,
  makeTokenUsage,
  assertToolCalled,
  assertToolOrder,
  assertNoToolCalled,
  assertOutputContains,
  assertOutputMatches,
  assertCostUnder,
  assertLatencyUnder,
  assertTokenCountUnder,
  Evaluator,
} from '../src/index.js';

function makeTestCassette(): Cassette {
  const c = new Cassette({ output_text: 'The weather is sunny and 72°F.' });
  c.addSpan(new Span({
    kind: SpanKind.TOOL_CALL,
    tool_name: 'search',
    tool_args: { q: 'weather' },
    duration_ms: 100,
  }));
  c.addSpan(new Span({
    kind: SpanKind.LLM_RESPONSE,
    model: 'gpt-4',
    token_usage: makeTokenUsage(20, 30),
    cost_usd: 0.01,
    duration_ms: 200,
  }));
  c.addSpan(new Span({
    kind: SpanKind.TOOL_CALL,
    tool_name: 'summarize',
    tool_args: { text: 'something' },
    duration_ms: 50,
  }));
  c.computeMetrics();
  return c;
}

// ── assertToolCalled ──────────────────────────────────────────────────────────

describe('assertToolCalled', () => {
  it('passes when tool was called', () => {
    const r = assertToolCalled(makeTestCassette(), 'search');
    expect(r.passed).toBe(true);
  });

  it('fails when tool was not called', () => {
    const r = assertToolCalled(makeTestCassette(), 'missing_tool');
    expect(r.passed).toBe(false);
    expect(r.message).toContain('missing_tool');
  });

  it('times option — passes on exact count', () => {
    const r = assertToolCalled(makeTestCassette(), 'search', { times: 1 });
    expect(r.passed).toBe(true);
  });

  it('times option — fails on wrong count', () => {
    const r = assertToolCalled(makeTestCassette(), 'search', { times: 3 });
    expect(r.passed).toBe(false);
    expect(r.actual).toBe(1);
  });

  it('withArgs option — passes on matching args', () => {
    const r = assertToolCalled(makeTestCassette(), 'search', { withArgs: { q: 'weather' } });
    expect(r.passed).toBe(true);
  });

  it('withArgs option — fails on mismatched args', () => {
    const r = assertToolCalled(makeTestCassette(), 'search', { withArgs: { q: 'wrong' } });
    expect(r.passed).toBe(false);
  });

  it('before option — passes when tool is before other', () => {
    const r = assertToolCalled(makeTestCassette(), 'search', { before: 'summarize' });
    expect(r.passed).toBe(true);
  });

  it('before option — fails when tool is not before other', () => {
    const r = assertToolCalled(makeTestCassette(), 'summarize', { before: 'search' });
    expect(r.passed).toBe(false);
  });

  it('after option — passes when tool is after other', () => {
    const r = assertToolCalled(makeTestCassette(), 'summarize', { after: 'search' });
    expect(r.passed).toBe(true);
  });

  it('after option — fails when tool is not after other', () => {
    const r = assertToolCalled(makeTestCassette(), 'search', { after: 'summarize' });
    expect(r.passed).toBe(false);
  });

  it('accepts AgentRun as input', () => {
    const run = new AgentRun(makeTestCassette());
    const r = assertToolCalled(run, 'search');
    expect(r.passed).toBe(true);
  });
});

// ── assertToolOrder ───────────────────────────────────────────────────────────

describe('assertToolOrder', () => {
  it('non-strict: passes when tools appear in order', () => {
    const r = assertToolOrder(makeTestCassette(), ['search', 'summarize']);
    expect(r.passed).toBe(true);
  });

  it('non-strict: passes with subset', () => {
    const r = assertToolOrder(makeTestCassette(), ['search']);
    expect(r.passed).toBe(true);
  });

  it('non-strict: fails when order is wrong', () => {
    const r = assertToolOrder(makeTestCassette(), ['summarize', 'search']);
    expect(r.passed).toBe(false);
  });

  it('strict: passes on exact sequence', () => {
    const r = assertToolOrder(makeTestCassette(), ['search', 'summarize'], true);
    expect(r.passed).toBe(true);
  });

  it('strict: fails on extra tools', () => {
    const r = assertToolOrder(makeTestCassette(), ['search'], true);
    expect(r.passed).toBe(false);
  });

  it('strict: fails on wrong order', () => {
    const r = assertToolOrder(makeTestCassette(), ['summarize', 'search'], true);
    expect(r.passed).toBe(false);
  });
});

// ── assertNoToolCalled ────────────────────────────────────────────────────────

describe('assertNoToolCalled', () => {
  it('passes when tool was not called', () => {
    const r = assertNoToolCalled(makeTestCassette(), 'email');
    expect(r.passed).toBe(true);
  });

  it('fails when tool was called', () => {
    const r = assertNoToolCalled(makeTestCassette(), 'search');
    expect(r.passed).toBe(false);
    expect(r.message).toContain('search');
  });
});

// ── assertOutputContains ──────────────────────────────────────────────────────

describe('assertOutputContains', () => {
  it('passes when substring found', () => {
    const r = assertOutputContains(makeTestCassette(), 'sunny');
    expect(r.passed).toBe(true);
  });

  it('fails when substring not found', () => {
    const r = assertOutputContains(makeTestCassette(), 'rainy');
    expect(r.passed).toBe(false);
  });

  it('case insensitive mode', () => {
    const r = assertOutputContains(makeTestCassette(), 'SUNNY', false);
    expect(r.passed).toBe(true);
  });

  it('case sensitive fails on wrong case', () => {
    const r = assertOutputContains(makeTestCassette(), 'SUNNY', true);
    expect(r.passed).toBe(false);
  });
});

// ── assertOutputMatches ───────────────────────────────────────────────────────

describe('assertOutputMatches', () => {
  it('passes on matching regex', () => {
    const r = assertOutputMatches(makeTestCassette(), '\\d+°F');
    expect(r.passed).toBe(true);
  });

  it('fails on non-matching regex', () => {
    const r = assertOutputMatches(makeTestCassette(), '^snowing');
    expect(r.passed).toBe(false);
  });
});

// ── assertCostUnder ───────────────────────────────────────────────────────────

describe('assertCostUnder', () => {
  it('passes when cost is under threshold', () => {
    const r = assertCostUnder(makeTestCassette(), 0.05);
    expect(r.passed).toBe(true);
    expect(r.actual).toBeCloseTo(0.01);
  });

  it('fails when cost exceeds threshold', () => {
    const r = assertCostUnder(makeTestCassette(), 0.001);
    expect(r.passed).toBe(false);
    expect(r.message).toContain('exceeds');
  });
});

// ── assertLatencyUnder ────────────────────────────────────────────────────────

describe('assertLatencyUnder', () => {
  it('passes when latency is under threshold', () => {
    const r = assertLatencyUnder(makeTestCassette(), 1000);
    expect(r.passed).toBe(true);
  });

  it('fails when latency exceeds threshold', () => {
    const r = assertLatencyUnder(makeTestCassette(), 50);
    expect(r.passed).toBe(false);
  });
});

// ── assertTokenCountUnder ─────────────────────────────────────────────────────

describe('assertTokenCountUnder', () => {
  it('passes when tokens under limit', () => {
    const r = assertTokenCountUnder(makeTestCassette(), 100);
    expect(r.passed).toBe(true);
    expect(r.actual).toBe(50);
  });

  it('fails when tokens over limit', () => {
    const r = assertTokenCountUnder(makeTestCassette(), 10);
    expect(r.passed).toBe(false);
  });
});

// ── Evaluator ─────────────────────────────────────────────────────────────────

describe('Evaluator', () => {
  it('all passing → passed=true, score=1.0', () => {
    const c = makeTestCassette();
    const ev = new Evaluator();
    ev.add(assertToolCalled, c, 'search');
    ev.add(assertCostUnder, c, 0.05);
    const result = ev.run();
    expect(result.passed).toBe(true);
    expect(result.score).toBe(1.0);
    expect(result.assertions).toHaveLength(2);
  });

  it('one failing → passed=false, score=0.5', () => {
    const c = makeTestCassette();
    const ev = new Evaluator();
    ev.add(assertToolCalled, c, 'search');
    ev.add(assertToolCalled, c, 'nonexistent');
    const result = ev.run();
    expect(result.passed).toBe(false);
    expect(result.score).toBe(0.5);
  });

  it('empty evaluator → passed=true, score=1.0', () => {
    const ev = new Evaluator();
    const result = ev.run();
    expect(result.passed).toBe(true);
    expect(result.score).toBe(1.0);
  });

  it('failedAssertions on EvalResult', () => {
    const c = makeTestCassette();
    const ev = new Evaluator();
    ev.add(assertToolCalled, c, 'search');
    ev.add(assertToolCalled, c, 'missing');
    const result = ev.run();
    expect(result.failedAssertions).toHaveLength(1);
  });

  it('chaining add() works', () => {
    const c = makeTestCassette();
    const result = new Evaluator()
      .add(assertToolCalled, c, 'search')
      .add(assertNoToolCalled, c, 'email')
      .run();
    expect(result.passed).toBe(true);
  });
});
