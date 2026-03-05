import { Cassette, Span } from '../core/models.js';
import { SpanKind, makeTokenUsage } from '../core/types.js';

// ── Active context (async-local equivalent using a simple stack) ─────────────
// Node.js has AsyncLocalStorage but for simplicity we expose a manual stack.
// For production use, wrap with AsyncLocalStorage.

let _activeContext: CaptureContext | null = null;

export function getActiveContext(): CaptureContext | null {
  return _activeContext;
}

function setActiveContext(ctx: CaptureContext | null): void {
  _activeContext = ctx;
}

// ── CaptureContext ────────────────────────────────────────────────────────────

export interface CaptureOptions {
  name?: string;
  agent_name?: string;
  framework?: string;
  save_path?: string | null;
  metadata?: Record<string, unknown>;
}

export class CaptureContext {
  cassette: Cassette;
  savePath: string | null;
  private _startTime = 0;
  private _prevContext: CaptureContext | null = null;

  constructor(options: CaptureOptions = {}) {
    this.cassette = new Cassette({
      name: options.name ?? '',
      agent_name: options.agent_name ?? '',
      framework: options.framework ?? '',
      metadata: options.metadata ?? {},
    });
    this.savePath = options.save_path ?? null;
  }

  enter(): this {
    this._startTime = Date.now();
    this._prevContext = _activeContext;
    setActiveContext(this);
    return this;
  }

  exit(): void {
    this._finalize();
    setActiveContext(this._prevContext);
  }

  private _finalize(): void {
    this.cassette.total_duration_ms = Date.now() - this._startTime;
    this.cassette.computeMetrics();
    this.cassette.computeFingerprint();
    if (this.savePath) {
      this.cassette.save(this.savePath);
    }
  }

  /** Use as async context manager via withCapture() or this helper. */
  async run<T>(fn: () => Promise<T>): Promise<T> {
    this.enter();
    try {
      return await fn();
    } finally {
      this.exit();
    }
  }

  /** Use for sync operations. */
  runSync<T>(fn: () => T): T {
    this.enter();
    try {
      return fn();
    } finally {
      this.exit();
    }
  }

  recordSpan(span: Span): Span {
    this.cassette.addSpan(span);
    return span;
  }

  recordLlmCall(options: {
    model: string;
    input: unknown;
    output: unknown;
    duration_ms?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    cost_usd?: number | null;
    metadata?: Record<string, unknown>;
  }): Span {
    const {
      model,
      input,
      output,
      duration_ms = 0,
      prompt_tokens = 0,
      completion_tokens = 0,
      cost_usd = null,
      metadata = {},
    } = options;
    const span = new Span({
      kind: SpanKind.LLM_RESPONSE,
      name: `llm:${model}`,
      duration_ms,
      input,
      output,
      model,
      token_usage: makeTokenUsage(prompt_tokens, completion_tokens),
      cost_usd,
      metadata,
    });
    return this.recordSpan(span);
  }

  recordToolCall(options: {
    tool_name: string;
    args?: Record<string, unknown> | null;
    result?: unknown;
    duration_ms?: number;
    error?: string | null;
    metadata?: Record<string, unknown>;
  }): Span {
    const {
      tool_name,
      args = null,
      result = null,
      duration_ms = 0,
      error = null,
      metadata = {},
    } = options;
    const span = new Span({
      kind: SpanKind.TOOL_CALL,
      name: `tool:${tool_name}`,
      duration_ms,
      tool_name,
      tool_args: args,
      tool_result: result,
      error,
      metadata,
    });
    return this.recordSpan(span);
  }

  recordInput(text: string): Span {
    this.cassette.input_text = text;
    const span = new Span({
      kind: SpanKind.USER_INPUT,
      name: 'user_input',
      input: text,
    });
    return this.recordSpan(span);
  }

  recordOutput(text: string): Span {
    this.cassette.output_text = text;
    const span = new Span({
      kind: SpanKind.AGENT_OUTPUT,
      name: 'agent_output',
      output: text,
    });
    return this.recordSpan(span);
  }
}

// ── Module-level helpers ──────────────────────────────────────────────────────

export function recordSpan(span: Span): Span | null {
  const ctx = getActiveContext();
  if (ctx) return ctx.recordSpan(span);
  return null;
}

export function recordLlmCall(
  options: Parameters<CaptureContext['recordLlmCall']>[0],
): Span | null {
  const ctx = getActiveContext();
  if (ctx) return ctx.recordLlmCall(options);
  return null;
}

export function recordToolCall(
  options: Parameters<CaptureContext['recordToolCall']>[0],
): Span | null {
  const ctx = getActiveContext();
  if (ctx) return ctx.recordToolCall(options);
  return null;
}

/** Decorator-style wrapper for async functions. */
export function capture(options: CaptureOptions = {}) {
  return function <T>(
    fn: (...args: unknown[]) => Promise<T>,
  ): (...args: unknown[]) => Promise<T> {
    return async (...args: unknown[]): Promise<T> => {
      const ctx = new CaptureContext({
        name: options.name || fn.name,
        ...options,
      });
      return ctx.run(() => fn(...args));
    };
  };
}
