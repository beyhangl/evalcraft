import { describe, it, expect, afterEach } from 'vitest';
import {
  MockLLM,
  MockTool,
  ToolError,
  CaptureContext,
  getActiveContext,
  SpanKind,
} from '../src/index.js';

afterEach(() => {
  const ctx = getActiveContext();
  if (ctx) ctx.exit();
});

// ── MockLLM ───────────────────────────────────────────────────────────────────

describe('MockLLM', () => {
  it('returns default response when nothing configured', () => {
    const llm = new MockLLM('mock', 'fallback');
    const r = llm.complete('anything');
    expect(r.content).toBe('fallback');
    expect(r.model).toBe('mock');
  });

  it('addResponse matches exact prompt', () => {
    const llm = new MockLLM();
    llm.addResponse("hello", "world");
    expect(llm.complete("hello").content).toBe("world");
  });

  it('wildcard (*) matches any prompt', () => {
    const llm = new MockLLM();
    llm.addResponse('*', 'wildcard-response');
    expect(llm.complete('anything here').content).toBe('wildcard-response');
    expect(llm.complete('totally different').content).toBe('wildcard-response');
  });

  it('addPatternResponse matches regex', () => {
    const llm = new MockLLM();
    llm.addPatternResponse('weather', 'sunny');
    expect(llm.complete('what is the weather today?').content).toBe('sunny');
  });

  it('addSequentialResponses returns in order', () => {
    const llm = new MockLLM();
    llm.addSequentialResponses('q', ['first', 'second', 'third']);
    expect(llm.complete('q').content).toBe('first');
    expect(llm.complete('q').content).toBe('second');
    expect(llm.complete('q').content).toBe('third');
  });

  it('sequential returns last item when exhausted', () => {
    const llm = new MockLLM();
    llm.addSequentialResponses('q', ['a', 'b']);
    llm.complete('q'); // a
    llm.complete('q'); // b
    expect(llm.complete('q').content).toBe('b');
  });

  it('setResponseFn takes priority', () => {
    const llm = new MockLLM();
    llm.addResponse('x', 'not-this');
    llm.setResponseFn((p) => ({ content: `fn:${p}`, model: 'mock', prompt_tokens: 1, completion_tokens: 1, finish_reason: 'stop', tool_calls: null, metadata: {} }));
    expect(llm.complete('x').content).toBe('fn:x');
  });

  it('increments callCount on each call', () => {
    const llm = new MockLLM();
    llm.addResponse('*', 'x');
    llm.complete('a');
    llm.complete('b');
    expect(llm.callCount).toBe(2);
  });

  it('callHistory records prompts', () => {
    const llm = new MockLLM();
    llm.addResponse('*', 'r');
    llm.complete('prompt1');
    llm.complete('prompt2');
    expect(llm.callHistory.map(c => c.prompt)).toEqual(['prompt1', 'prompt2']);
  });

  it('reset clears history', () => {
    const llm = new MockLLM();
    llm.addResponse('*', 'r');
    llm.complete('a');
    llm.reset();
    expect(llm.callCount).toBe(0);
    expect(llm.callHistory).toHaveLength(0);
  });

  it('assertCalled passes when called', () => {
    const llm = new MockLLM();
    llm.addResponse('*', 'x');
    llm.complete('hi');
    expect(() => llm.assertCalled()).not.toThrow();
  });

  it('assertCalled throws when never called', () => {
    const llm = new MockLLM();
    expect(() => llm.assertCalled()).toThrow('never called');
  });

  it('assertCalled(times) checks exact count', () => {
    const llm = new MockLLM();
    llm.addResponse('*', 'x');
    llm.complete('a');
    expect(() => llm.assertCalled(1)).not.toThrow();
    expect(() => llm.assertCalled(2)).toThrow();
  });

  it('assertCalledWith checks prompt', () => {
    const llm = new MockLLM();
    llm.addResponse('*', 'x');
    llm.complete('my prompt');
    expect(() => llm.assertCalledWith('my prompt')).not.toThrow();
    expect(() => llm.assertCalledWith('wrong')).toThrow();
  });

  it('records to active capture context', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    const llm = new MockLLM('gpt-4');
    llm.addResponse('*', 'ok');
    llm.complete('test');
    expect(ctx.cassette.spans).toHaveLength(1);
    expect(ctx.cassette.spans[0].kind).toBe(SpanKind.LLM_RESPONSE);
    expect(ctx.cassette.spans[0].model).toBe('gpt-4');
    ctx.exit();
  });

  it('token_usage is recorded to span', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    const llm = new MockLLM();
    llm.addResponse('*', 'ok', 5, 10);
    llm.complete('hi');
    expect(ctx.cassette.spans[0].token_usage?.total_tokens).toBe(15);
    ctx.exit();
  });
});

// ── MockTool ──────────────────────────────────────────────────────────────────

describe('MockTool', () => {
  it('returns static value', () => {
    const tool = new MockTool('search');
    tool.returns({ results: ['a', 'b'] });
    expect(tool.call()).toEqual({ results: ['a', 'b'] });
  });

  it('returnsFn receives args', () => {
    const tool = new MockTool('calc');
    tool.returnsFn((args: unknown) => {
      const a = args as Record<string, unknown>;
      return (a['x'] as number) * 2;
    });
    expect(tool.call({ x: 5 })).toBe(10);
  });

  it('returnsSequence iterates values', () => {
    const tool = new MockTool('seq');
    tool.returnsSequence([1, 2, 3]);
    expect(tool.call()).toBe(1);
    expect(tool.call()).toBe(2);
    expect(tool.call()).toBe(3);
  });

  it('returnsSequence returns last when exhausted', () => {
    const tool = new MockTool('seq');
    tool.returnsSequence(['a', 'b']);
    tool.call();
    tool.call();
    expect(tool.call()).toBe('b');
  });

  it('raises throws ToolError', () => {
    const tool = new MockTool('bad');
    tool.raises('something went wrong');
    expect(() => tool.call()).toThrow(ToolError);
    expect(() => tool.call()).toThrow('something went wrong');
  });

  it('raisesAfter throws only after N calls', () => {
    const tool = new MockTool('fragile');
    tool.returns('ok').raisesAfter(2, 'boom');
    expect(tool.call()).toBe('ok');
    expect(tool.call()).toBe('ok');
    expect(() => tool.call()).toThrow('boom');
  });

  it('callCount increments', () => {
    const tool = new MockTool('t');
    tool.returns(1);
    tool.call();
    tool.call();
    expect(tool.callCount).toBe(2);
  });

  it('lastCall returns most recent args/result', () => {
    const tool = new MockTool('t');
    tool.returns(99);
    tool.call({ q: 'first' });
    tool.call({ q: 'second' });
    expect(tool.lastCall?.args).toEqual({ q: 'second' });
    expect(tool.lastCall?.result).toBe(99);
  });

  it('lastCall returns null when not called', () => {
    const tool = new MockTool('t');
    expect(tool.lastCall).toBeNull();
  });

  it('reset clears history', () => {
    const tool = new MockTool('t');
    tool.returns(1);
    tool.call();
    tool.reset();
    expect(tool.callCount).toBe(0);
    expect(tool.callHistory).toHaveLength(0);
  });

  it('assertCalled passes when called', () => {
    const tool = new MockTool('t');
    tool.returns(1);
    tool.call();
    expect(() => tool.assertCalled()).not.toThrow();
  });

  it('assertCalled throws when not called', () => {
    const tool = new MockTool('t');
    expect(() => tool.assertCalled()).toThrow("never called");
  });

  it('assertCalledWith passes on matching args', () => {
    const tool = new MockTool('search');
    tool.returns('ok');
    tool.call({ q: 'python' });
    expect(() => tool.assertCalledWith({ q: 'python' })).not.toThrow();
  });

  it('assertCalledWith throws on non-matching args', () => {
    const tool = new MockTool('search');
    tool.returns('ok');
    tool.call({ q: 'python' });
    expect(() => tool.assertCalledWith({ q: 'java' })).toThrow();
  });

  it('assertNotCalled passes when clean', () => {
    const tool = new MockTool('t');
    expect(() => tool.assertNotCalled()).not.toThrow();
  });

  it('assertNotCalled throws when called', () => {
    const tool = new MockTool('t');
    tool.returns(1);
    tool.call();
    expect(() => tool.assertNotCalled()).toThrow();
  });

  it('records to active capture context', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    const tool = new MockTool('search');
    tool.returns({ data: 1 });
    tool.call({ q: 'test' });
    expect(ctx.cassette.spans).toHaveLength(1);
    expect(ctx.cassette.spans[0].tool_name).toBe('search');
    expect(ctx.cassette.spans[0].kind).toBe(SpanKind.TOOL_CALL);
    ctx.exit();
  });

  it('error is recorded to span', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    const tool = new MockTool('broken');
    tool.raises('err!');
    try { tool.call(); } catch { /* expected */ }
    expect(ctx.cassette.spans[0].error).toBe('err!');
    ctx.exit();
  });
});
