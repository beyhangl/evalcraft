import { describe, it, expect } from 'vitest';
import { Cassette, Span, SpanKind, ReplayEngine, ReplayDiff, replay } from '../src/index.js';
import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs';

function makeCassetteWithTools(): Cassette {
  const c = new Cassette({ name: 'test', output_text: 'done' });
  c.addSpan(new Span({ id: 's1', kind: SpanKind.TOOL_CALL, tool_name: 'search', tool_result: { data: 'original' } }));
  c.addSpan(new Span({ id: 's2', kind: SpanKind.LLM_RESPONSE, model: 'gpt-4', output: 'thinking...' }));
  c.addSpan(new Span({ id: 's3', kind: SpanKind.TOOL_CALL, tool_name: 'summarize', tool_result: 'summary' }));
  return c;
}

describe('ReplayEngine', () => {
  it('creates from Cassette object', () => {
    const c = makeCassetteWithTools();
    const engine = new ReplayEngine(c);
    expect(engine.spans).toHaveLength(3);
  });

  it('run returns AgentRun with replayed=true', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    const run = engine.run();
    expect(run.replayed).toBe(true);
    expect(run.success).toBe(true);
  });

  it('run preserves spans', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    const run = engine.run();
    expect(run.cassette.spans).toHaveLength(3);
  });

  it('overrideToolResult replaces tool result', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    engine.overrideToolResult('search', { data: 'overridden' });
    const run = engine.run();
    const searchSpan = run.cassette.getToolCalls().find(s => s.tool_name === 'search');
    expect(searchSpan?.tool_result).toEqual({ data: 'overridden' });
  });

  it('overrideToolResult chaining works', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    engine
      .overrideToolResult('search', 'new-search')
      .overrideToolResult('summarize', 'new-summary');
    const run = engine.run();
    const seq = run.cassette.getToolSequence();
    expect(seq).toContain('search');
    expect(seq).toContain('summarize');
  });

  it('overrideLlmResponse replaces LLM output by index', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    engine.overrideLlmResponse(0, 'new response');
    const run = engine.run();
    const llmSpan = run.cassette.getLlmCalls()[0];
    expect(llmSpan?.output).toBe('new response');
  });

  it('filterSpans excludes non-matching spans', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    engine.filterSpans(s => s.kind === SpanKind.TOOL_CALL);
    expect(engine.spans).toHaveLength(2);
  });

  it('getToolCalls returns only tool spans', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    expect(engine.getToolCalls()).toHaveLength(2);
  });

  it('getLlmCalls returns only LLM spans', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    expect(engine.getLlmCalls()).toHaveLength(1);
  });

  it('getToolSequence returns tool names in order', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    expect(engine.getToolSequence()).toEqual(['search', 'summarize']);
  });

  it('step() iterates one span at a time', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    const s1 = engine.step();
    expect(s1?.id).toBe('s1');
    const s2 = engine.step();
    expect(s2?.id).toBe('s2');
    const s3 = engine.step();
    expect(s3?.id).toBe('s3');
    const done = engine.step();
    expect(done).toBeNull();
  });

  it('reset() restarts step iteration', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    engine.step();
    engine.step();
    engine.reset();
    expect(engine.step()?.id).toBe('s1');
  });

  it('step() applies tool override', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    engine.overrideToolResult('search', 'stepped-result');
    const s = engine.step();
    expect(s?.tool_result).toBe('stepped-result');
  });

  it('run produces cassette with computed fingerprint', () => {
    const engine = new ReplayEngine(makeCassetteWithTools());
    const run = engine.run();
    expect(run.cassette.fingerprint).toBeTruthy();
    expect(run.cassette.fingerprint).toHaveLength(16);
  });
});

describe('ReplayDiff', () => {
  it('no changes when cassettes identical', () => {
    const c1 = makeCassetteWithTools();
    c1.computeMetrics();
    const c2 = Cassette.fromDict(JSON.parse(JSON.stringify(c1.toDict())) as Record<string, unknown>);
    const diff = ReplayDiff.compute(c1, c2);
    expect(diff.hasChanges).toBe(false);
  });

  it('detects tool sequence change', () => {
    const c1 = makeCassetteWithTools();
    const c2 = new Cassette();
    c2.addSpan(new Span({ kind: SpanKind.TOOL_CALL, tool_name: 'other' }));
    const diff = ReplayDiff.compute(c1, c2);
    expect(diff.toolSequenceChanged).toBe(true);
    expect(diff.hasChanges).toBe(true);
  });

  it('detects output change', () => {
    const c1 = new Cassette({ output_text: 'hello' });
    const c2 = new Cassette({ output_text: 'world' });
    const diff = ReplayDiff.compute(c1, c2);
    expect(diff.outputChanged).toBe(true);
  });

  it('detects span count change', () => {
    const c1 = makeCassetteWithTools();
    const c2 = new Cassette();
    const diff = ReplayDiff.compute(c1, c2);
    expect(diff.spanCountChanged).toBe(true);
  });

  it('summary returns "No changes detected." when clean', () => {
    const c = makeCassetteWithTools();
    c.computeMetrics();
    const diff = ReplayDiff.compute(c, Cassette.fromDict(JSON.parse(JSON.stringify(c.toDict())) as Record<string, unknown>));
    expect(diff.summary()).toBe('No changes detected.');
  });

  it('summary lists changes', () => {
    const c1 = new Cassette({ output_text: 'hello' });
    const c2 = new Cassette({ output_text: 'world' });
    const diff = ReplayDiff.compute(c1, c2);
    expect(diff.summary()).toContain('Output text changed');
  });

  it('toDict includes has_changes', () => {
    const diff = new ReplayDiff();
    const d = diff.toDict();
    expect('has_changes' in d).toBe(true);
  });
});

describe('replay() convenience function', () => {
  it('replays from file path', () => {
    const c = makeCassetteWithTools();
    const tmpFile = path.join(os.tmpdir(), 'evalcraft-test.json');
    c.save(tmpFile);

    const run = replay(tmpFile);
    expect(run.replayed).toBe(true);
    expect(run.cassette.spans).toHaveLength(3);

    fs.unlinkSync(tmpFile);
  });

  it('applies tool overrides from file', () => {
    const c = makeCassetteWithTools();
    const tmpFile = path.join(os.tmpdir(), 'evalcraft-test2.json');
    c.save(tmpFile);

    const run = replay(tmpFile, { search: 'override' });
    const searchSpan = run.cassette.getToolCalls().find(s => s.tool_name === 'search');
    expect(searchSpan?.tool_result).toBe('override');

    fs.unlinkSync(tmpFile);
  });
});
