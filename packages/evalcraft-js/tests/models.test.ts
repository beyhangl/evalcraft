import { describe, it, expect } from 'vitest';
import {
  Span,
  Cassette,
  AgentRun,
  EvalResult,
  AssertionResult,
  SpanKind,
  makeTokenUsage,
} from '../src/index.js';

describe('TokenUsage', () => {
  it('sums total tokens', () => {
    const tu = makeTokenUsage(10, 20);
    expect(tu.total_tokens).toBe(30);
  });

  it('defaults to zeros', () => {
    const tu = makeTokenUsage();
    expect(tu.prompt_tokens).toBe(0);
    expect(tu.completion_tokens).toBe(0);
    expect(tu.total_tokens).toBe(0);
  });
});

describe('Span', () => {
  it('generates an id by default', () => {
    const s = new Span();
    expect(s.id).toBeTruthy();
    expect(s.id).toHaveLength(36); // UUID length
  });

  it('accepts data overrides', () => {
    const s = new Span({ kind: SpanKind.TOOL_CALL, name: 'my_tool', tool_name: 'search' });
    expect(s.kind).toBe(SpanKind.TOOL_CALL);
    expect(s.name).toBe('my_tool');
    expect(s.tool_name).toBe('search');
  });

  it('round-trips through toDict/fromDict', () => {
    const s = new Span({
      kind: SpanKind.LLM_RESPONSE,
      name: 'llm:gpt-4',
      model: 'gpt-4',
      token_usage: makeTokenUsage(5, 10),
      cost_usd: 0.001,
      input: 'hello',
      output: 'world',
    });
    const s2 = Span.fromDict(s.toDict() as Record<string, unknown>);
    expect(s2.kind).toBe(SpanKind.LLM_RESPONSE);
    expect(s2.model).toBe('gpt-4');
    expect(s2.token_usage?.total_tokens).toBe(15);
    expect(s2.cost_usd).toBe(0.001);
  });

  it('clone produces deep copy', () => {
    const s = new Span({ metadata: { key: 'val' } });
    const c = s.clone();
    c.metadata['key'] = 'changed';
    expect(s.metadata['key']).toBe('val');
  });

  it('handles null token_usage in fromDict', () => {
    const s = new Span({ token_usage: null });
    expect(s.token_usage).toBeNull();
    const s2 = Span.fromDict(s.toDict() as Record<string, unknown>);
    expect(s2.token_usage).toBeNull();
  });
});

describe('Cassette', () => {
  it('creates with defaults', () => {
    const c = new Cassette();
    expect(c.id).toBeTruthy();
    expect(c.spans).toEqual([]);
    expect(c.version).toBe('1.0');
  });

  it('addSpan appends span', () => {
    const c = new Cassette();
    c.addSpan(new Span({ kind: SpanKind.TOOL_CALL, tool_name: 'search' }));
    expect(c.spans).toHaveLength(1);
  });

  it('getToolCalls returns only TOOL_CALL spans', () => {
    const c = new Cassette();
    c.addSpan(new Span({ kind: SpanKind.TOOL_CALL, tool_name: 'search' }));
    c.addSpan(new Span({ kind: SpanKind.LLM_RESPONSE }));
    expect(c.getToolCalls()).toHaveLength(1);
  });

  it('getLlmCalls includes LLM_REQUEST and LLM_RESPONSE', () => {
    const c = new Cassette();
    c.addSpan(new Span({ kind: SpanKind.LLM_REQUEST }));
    c.addSpan(new Span({ kind: SpanKind.LLM_RESPONSE }));
    c.addSpan(new Span({ kind: SpanKind.TOOL_CALL }));
    expect(c.getLlmCalls()).toHaveLength(2);
  });

  it('getToolSequence returns ordered tool names', () => {
    const c = new Cassette();
    c.addSpan(new Span({ kind: SpanKind.TOOL_CALL, tool_name: 'search' }));
    c.addSpan(new Span({ kind: SpanKind.TOOL_CALL, tool_name: 'summarize' }));
    expect(c.getToolSequence()).toEqual(['search', 'summarize']);
  });

  it('computeMetrics sums tokens and costs', () => {
    const c = new Cassette();
    c.addSpan(new Span({
      kind: SpanKind.LLM_RESPONSE,
      token_usage: makeTokenUsage(5, 10),
      cost_usd: 0.01,
      duration_ms: 100,
    }));
    c.addSpan(new Span({
      kind: SpanKind.TOOL_CALL,
      duration_ms: 50,
    }));
    c.computeMetrics();
    expect(c.total_tokens).toBe(15);
    expect(c.total_cost_usd).toBeCloseTo(0.01);
    expect(c.total_duration_ms).toBe(150);
    expect(c.llm_call_count).toBe(1);
    expect(c.tool_call_count).toBe(1);
  });

  it('computeFingerprint returns 16-char hex string', () => {
    const c = new Cassette({ name: 'test' });
    const fp = c.computeFingerprint();
    expect(fp).toHaveLength(16);
    expect(fp).toMatch(/^[0-9a-f]+$/);
  });

  it('same spans produce same fingerprint', () => {
    const c1 = new Cassette();
    const c2 = new Cassette();
    c1.addSpan(new Span({ id: 'abc', kind: SpanKind.TOOL_CALL, tool_name: 'x' }));
    c2.addSpan(new Span({ id: 'abc', kind: SpanKind.TOOL_CALL, tool_name: 'x' }));
    expect(c1.computeFingerprint()).toBe(c2.computeFingerprint());
  });

  it('different spans produce different fingerprints', () => {
    const c1 = new Cassette();
    const c2 = new Cassette();
    c1.addSpan(new Span({ id: 'abc', kind: SpanKind.TOOL_CALL, tool_name: 'x' }));
    c2.addSpan(new Span({ id: 'xyz', kind: SpanKind.TOOL_CALL, tool_name: 'y' }));
    expect(c1.computeFingerprint()).not.toBe(c2.computeFingerprint());
  });

  it('toDict includes evalcraft_version', () => {
    const c = new Cassette({ name: 'test' });
    const d = c.toDict();
    expect(d['evalcraft_version']).toBe('0.1.0');
  });

  it('fromDict round-trips', () => {
    const c = new Cassette({ name: 'agent-test', agent_name: 'my-agent' });
    c.addSpan(new Span({ kind: SpanKind.TOOL_CALL, tool_name: 'search' }));
    const c2 = Cassette.fromDict(c.toDict() as Record<string, unknown>);
    expect(c2.name).toBe('agent-test');
    expect(c2.agent_name).toBe('my-agent');
    expect(c2.spans).toHaveLength(1);
    expect(c2.spans[0].tool_name).toBe('search');
  });
});

describe('AgentRun', () => {
  it('defaults to success', () => {
    const run = new AgentRun(new Cassette());
    expect(run.success).toBe(true);
    expect(run.replayed).toBe(false);
    expect(run.error).toBeNull();
  });

  it('toDict includes replayed flag', () => {
    const run = new AgentRun(new Cassette(), true, null, true);
    const d = run.toDict();
    expect(d['replayed']).toBe(true);
  });
});

describe('AssertionResult', () => {
  it('defaults to passed', () => {
    const r = new AssertionResult();
    expect(r.passed).toBe(true);
    expect(r.message).toBe('');
  });

  it('toDict round-trips', () => {
    const r = new AssertionResult({ name: 'test', passed: false, message: 'oops' });
    const d = r.toDict();
    expect(d['name']).toBe('test');
    expect(d['passed']).toBe(false);
    expect(d['message']).toBe('oops');
  });
});

describe('EvalResult', () => {
  it('failedAssertions filters correctly', () => {
    const r = new EvalResult({
      assertions: [
        new AssertionResult({ passed: true }),
        new AssertionResult({ passed: false, name: 'bad' }),
      ],
    });
    expect(r.failedAssertions).toHaveLength(1);
    expect(r.failedAssertions[0].name).toBe('bad');
  });
});
