import { describe, it, expect, afterEach } from 'vitest';
import {
  CaptureContext,
  getActiveContext,
  recordSpan,
  recordLlmCall,
  recordToolCall,
  Span,
  SpanKind,
} from '../src/index.js';

afterEach(() => {
  // Ensure context is cleared between tests
  const ctx = getActiveContext();
  if (ctx) ctx.exit();
});

describe('CaptureContext', () => {
  it('enter/exit sets active context', () => {
    const ctx = new CaptureContext({ name: 'test' });
    expect(getActiveContext()).toBeNull();
    ctx.enter();
    expect(getActiveContext()).toBe(ctx);
    ctx.exit();
    expect(getActiveContext()).toBeNull();
  });

  it('recordSpan adds span to cassette', () => {
    const ctx = new CaptureContext({ name: 'test' });
    ctx.enter();
    ctx.recordSpan(new Span({ kind: SpanKind.TOOL_CALL, tool_name: 'search' }));
    expect(ctx.cassette.spans).toHaveLength(1);
    ctx.exit();
  });

  it('recordLlmCall creates LLM_RESPONSE span', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    ctx.recordLlmCall({
      model: 'gpt-4',
      input: 'hello',
      output: 'world',
      prompt_tokens: 5,
      completion_tokens: 10,
    });
    const span = ctx.cassette.spans[0];
    expect(span.kind).toBe(SpanKind.LLM_RESPONSE);
    expect(span.model).toBe('gpt-4');
    expect(span.token_usage?.total_tokens).toBe(15);
    ctx.exit();
  });

  it('recordToolCall creates TOOL_CALL span', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    ctx.recordToolCall({ tool_name: 'search', args: { q: 'test' }, result: 'results' });
    const span = ctx.cassette.spans[0];
    expect(span.kind).toBe(SpanKind.TOOL_CALL);
    expect(span.tool_name).toBe('search');
    expect(span.tool_args).toEqual({ q: 'test' });
    ctx.exit();
  });

  it('recordInput sets cassette input_text', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    ctx.recordInput('What is the weather?');
    expect(ctx.cassette.input_text).toBe('What is the weather?');
    ctx.exit();
  });

  it('recordOutput sets cassette output_text', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    ctx.recordOutput("It's sunny");
    expect(ctx.cassette.output_text).toBe("It's sunny");
    ctx.exit();
  });

  it('run() wraps async function', async () => {
    const ctx = new CaptureContext({ name: 'async-test' });
    let inner: CaptureContext | null = null;
    await ctx.run(async () => {
      inner = getActiveContext();
    });
    expect(inner).toBe(ctx);
    expect(getActiveContext()).toBeNull();
  });

  it('runSync() wraps sync function', () => {
    const ctx = new CaptureContext({ name: 'sync-test' });
    let inner: CaptureContext | null = null;
    ctx.runSync(() => {
      inner = getActiveContext();
    });
    expect(inner).toBe(ctx);
    expect(getActiveContext()).toBeNull();
  });

  it('exit finalizes metrics and fingerprint', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    ctx.recordLlmCall({
      model: 'gpt-4',
      input: 'hi',
      output: 'hello',
      prompt_tokens: 3,
      completion_tokens: 5,
    });
    ctx.exit();
    expect(ctx.cassette.total_tokens).toBe(8);
    expect(ctx.cassette.fingerprint).toBeTruthy();
  });

  it('nested contexts restore previous context on exit', () => {
    const outer = new CaptureContext({ name: 'outer' });
    outer.enter();
    const inner = new CaptureContext({ name: 'inner' });
    inner.enter();
    expect(getActiveContext()).toBe(inner);
    inner.exit();
    expect(getActiveContext()).toBe(outer);
    outer.exit();
    expect(getActiveContext()).toBeNull();
  });
});

describe('module-level helpers', () => {
  it('recordSpan returns null when no context', () => {
    const result = recordSpan(new Span());
    expect(result).toBeNull();
  });

  it('recordSpan records to active context', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    const span = new Span({ kind: SpanKind.AGENT_STEP });
    recordSpan(span);
    expect(ctx.cassette.spans).toHaveLength(1);
    ctx.exit();
  });

  it('recordLlmCall returns null when no context', () => {
    const result = recordLlmCall({ model: 'x', input: 'a', output: 'b' });
    expect(result).toBeNull();
  });

  it('recordToolCall records to active context', () => {
    const ctx = new CaptureContext();
    ctx.enter();
    recordToolCall({ tool_name: 'calc', result: 42 });
    expect(ctx.cassette.spans[0].tool_name).toBe('calc');
    ctx.exit();
  });
});
