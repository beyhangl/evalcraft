import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { SpanKind, TokenUsage, makeTokenUsage, tokenUsageFromDict } from './types.js';

// ── Span ────────────────────────────────────────────────────────────────────

export interface SpanData {
  id?: string;
  kind?: SpanKind;
  name?: string;
  timestamp?: number;
  duration_ms?: number;
  parent_id?: string | null;
  input?: unknown;
  output?: unknown;
  error?: string | null;
  model?: string | null;
  token_usage?: TokenUsage | null;
  cost_usd?: number | null;
  tool_name?: string | null;
  tool_args?: Record<string, unknown> | null;
  tool_result?: unknown;
  metadata?: Record<string, unknown>;
}

export class Span {
  id: string;
  kind: SpanKind;
  name: string;
  timestamp: number;
  duration_ms: number;
  parent_id: string | null;
  input: unknown;
  output: unknown;
  error: string | null;
  model: string | null;
  token_usage: TokenUsage | null;
  cost_usd: number | null;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  tool_result: unknown;
  metadata: Record<string, unknown>;

  constructor(data: SpanData = {}) {
    this.id = data.id ?? crypto.randomUUID();
    this.kind = data.kind ?? SpanKind.LLM_REQUEST;
    this.name = data.name ?? '';
    this.timestamp = data.timestamp ?? Date.now() / 1000;
    this.duration_ms = data.duration_ms ?? 0;
    this.parent_id = data.parent_id ?? null;
    this.input = data.input ?? null;
    this.output = data.output ?? null;
    this.error = data.error ?? null;
    this.model = data.model ?? null;
    this.token_usage = data.token_usage ?? null;
    this.cost_usd = data.cost_usd ?? null;
    this.tool_name = data.tool_name ?? null;
    this.tool_args = data.tool_args ?? null;
    this.tool_result = data.tool_result ?? undefined;
    this.metadata = data.metadata ?? {};
  }

  toDict(): Record<string, unknown> {
    return {
      id: this.id,
      kind: this.kind,
      name: this.name,
      timestamp: this.timestamp,
      duration_ms: this.duration_ms,
      parent_id: this.parent_id,
      input: this.input,
      output: this.output,
      error: this.error,
      model: this.model,
      token_usage: this.token_usage,
      cost_usd: this.cost_usd,
      tool_name: this.tool_name,
      tool_args: this.tool_args,
      tool_result: this.tool_result,
      metadata: this.metadata,
    };
  }

  static fromDict(data: Record<string, unknown>): Span {
    const tu = data['token_usage']
      ? tokenUsageFromDict(data['token_usage'] as Record<string, unknown>)
      : null;
    return new Span({
      id: data['id'] as string,
      kind: (data['kind'] as SpanKind) ?? SpanKind.LLM_REQUEST,
      name: (data['name'] as string) ?? '',
      timestamp: (data['timestamp'] as number) ?? Date.now() / 1000,
      duration_ms: (data['duration_ms'] as number) ?? 0,
      parent_id: (data['parent_id'] as string | null) ?? null,
      input: data['input'],
      output: data['output'],
      error: (data['error'] as string | null) ?? null,
      model: (data['model'] as string | null) ?? null,
      token_usage: tu,
      cost_usd: (data['cost_usd'] as number | null) ?? null,
      tool_name: (data['tool_name'] as string | null) ?? null,
      tool_args: (data['tool_args'] as Record<string, unknown> | null) ?? null,
      tool_result: data['tool_result'],
      metadata: (data['metadata'] as Record<string, unknown>) ?? {},
    });
  }

  clone(): Span {
    return Span.fromDict(JSON.parse(JSON.stringify(this.toDict())));
  }
}

// ── Cassette ─────────────────────────────────────────────────────────────────

export interface CassetteData {
  id?: string;
  name?: string;
  version?: string;
  created_at?: number;
  agent_name?: string;
  framework?: string;
  spans?: Span[];
  input_text?: string;
  output_text?: string;
  total_tokens?: number;
  total_cost_usd?: number;
  total_duration_ms?: number;
  llm_call_count?: number;
  tool_call_count?: number;
  fingerprint?: string;
  metadata?: Record<string, unknown>;
}

export class Cassette {
  id: string;
  name: string;
  version: string;
  created_at: number;
  agent_name: string;
  framework: string;
  spans: Span[];
  input_text: string;
  output_text: string;
  total_tokens: number;
  total_cost_usd: number;
  total_duration_ms: number;
  llm_call_count: number;
  tool_call_count: number;
  fingerprint: string;
  metadata: Record<string, unknown>;

  constructor(data: CassetteData = {}) {
    this.id = data.id ?? crypto.randomUUID();
    this.name = data.name ?? '';
    this.version = data.version ?? '1.0';
    this.created_at = data.created_at ?? Date.now() / 1000;
    this.agent_name = data.agent_name ?? '';
    this.framework = data.framework ?? '';
    this.spans = data.spans ?? [];
    this.input_text = data.input_text ?? '';
    this.output_text = data.output_text ?? '';
    this.total_tokens = data.total_tokens ?? 0;
    this.total_cost_usd = data.total_cost_usd ?? 0;
    this.total_duration_ms = data.total_duration_ms ?? 0;
    this.llm_call_count = data.llm_call_count ?? 0;
    this.tool_call_count = data.tool_call_count ?? 0;
    this.fingerprint = data.fingerprint ?? '';
    this.metadata = data.metadata ?? {};
  }

  computeFingerprint(): string {
    const content = JSON.stringify(
      this.spans.map((s) => s.toDict()),
      (_k, v) => (v === undefined ? null : v),
    );
    const hash = crypto.createHash('sha256').update(content).digest('hex');
    this.fingerprint = hash.slice(0, 16);
    return this.fingerprint;
  }

  computeMetrics(): void {
    this.total_tokens = 0;
    this.total_cost_usd = 0;
    this.total_duration_ms = 0;
    this.llm_call_count = 0;
    this.tool_call_count = 0;

    for (const span of this.spans) {
      this.total_duration_ms += span.duration_ms;
      if (span.token_usage) {
        this.total_tokens += span.token_usage.total_tokens;
      }
      if (span.cost_usd != null) {
        this.total_cost_usd += span.cost_usd;
      }
      if (
        span.kind === SpanKind.LLM_REQUEST ||
        span.kind === SpanKind.LLM_RESPONSE
      ) {
        this.llm_call_count += 1;
      }
      if (span.kind === SpanKind.TOOL_CALL) {
        this.tool_call_count += 1;
      }
    }
  }

  addSpan(span: Span): void {
    this.spans.push(span);
  }

  getToolCalls(): Span[] {
    return this.spans.filter((s) => s.kind === SpanKind.TOOL_CALL);
  }

  getLlmCalls(): Span[] {
    return this.spans.filter(
      (s) =>
        s.kind === SpanKind.LLM_REQUEST || s.kind === SpanKind.LLM_RESPONSE,
    );
  }

  getToolSequence(): string[] {
    return this.getToolCalls()
      .map((s) => s.tool_name)
      .filter((n): n is string => n != null);
  }

  toDict(): Record<string, unknown> {
    this.computeMetrics();
    this.computeFingerprint();
    return {
      evalcraft_version: '0.1.0',
      cassette: {
        id: this.id,
        name: this.name,
        version: this.version,
        created_at: this.created_at,
        agent_name: this.agent_name,
        framework: this.framework,
        input_text: this.input_text,
        output_text: this.output_text,
        total_tokens: this.total_tokens,
        total_cost_usd: this.total_cost_usd,
        total_duration_ms: this.total_duration_ms,
        llm_call_count: this.llm_call_count,
        tool_call_count: this.tool_call_count,
        fingerprint: this.fingerprint,
        metadata: this.metadata,
      },
      spans: this.spans.map((s) => s.toDict()),
    };
  }

  static fromDict(data: Record<string, unknown>): Cassette {
    const cassetteData = (data['cassette'] ??
      data) as Record<string, unknown>;
    const spansData = (data['spans'] as Record<string, unknown>[]) ?? [];
    const c = new Cassette({
      id: (cassetteData['id'] as string) ?? crypto.randomUUID(),
      name: (cassetteData['name'] as string) ?? '',
      version: (cassetteData['version'] as string) ?? '1.0',
      created_at: (cassetteData['created_at'] as number) ?? Date.now() / 1000,
      agent_name: (cassetteData['agent_name'] as string) ?? '',
      framework: (cassetteData['framework'] as string) ?? '',
      input_text: (cassetteData['input_text'] as string) ?? '',
      output_text: (cassetteData['output_text'] as string) ?? '',
      total_tokens: (cassetteData['total_tokens'] as number) ?? 0,
      total_cost_usd: (cassetteData['total_cost_usd'] as number) ?? 0,
      total_duration_ms: (cassetteData['total_duration_ms'] as number) ?? 0,
      llm_call_count: (cassetteData['llm_call_count'] as number) ?? 0,
      tool_call_count: (cassetteData['tool_call_count'] as number) ?? 0,
      fingerprint: (cassetteData['fingerprint'] as string) ?? '',
      metadata: (cassetteData['metadata'] as Record<string, unknown>) ?? {},
    });
    c.spans = spansData.map((s) => Span.fromDict(s));
    return c;
  }

  save(filePath: string): string {
    const dir = path.dirname(filePath);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(this.toDict(), null, 2));
    return filePath;
  }

  static load(filePath: string): Cassette {
    const data = JSON.parse(fs.readFileSync(filePath, 'utf-8')) as Record<
      string,
      unknown
    >;
    return Cassette.fromDict(data);
  }
}

// ── AgentRun ──────────────────────────────────────────────────────────────────

export class AgentRun {
  cassette: Cassette;
  success: boolean;
  error: string | null;
  replayed: boolean;

  constructor(
    cassette: Cassette,
    success = true,
    error: string | null = null,
    replayed = false,
  ) {
    this.cassette = cassette;
    this.success = success;
    this.error = error;
    this.replayed = replayed;
  }

  toDict(): Record<string, unknown> {
    return {
      cassette: this.cassette.toDict(),
      success: this.success,
      error: this.error,
      replayed: this.replayed,
    };
  }
}

// ── EvalResult / AssertionResult ──────────────────────────────────────────────

export class AssertionResult {
  name: string;
  passed: boolean;
  expected: unknown;
  actual: unknown;
  message: string;

  constructor(data: {
    name?: string;
    passed?: boolean;
    expected?: unknown;
    actual?: unknown;
    message?: string;
  } = {}) {
    this.name = data.name ?? '';
    this.passed = data.passed ?? true;
    this.expected = data.expected ?? null;
    this.actual = data.actual ?? null;
    this.message = data.message ?? '';
  }

  toDict(): Record<string, unknown> {
    return {
      name: this.name,
      passed: this.passed,
      expected: this.expected,
      actual: this.actual,
      message: this.message,
    };
  }
}

export class EvalResult {
  passed: boolean;
  score: number;
  assertions: AssertionResult[];
  metadata: Record<string, unknown>;

  constructor(data: {
    passed?: boolean;
    score?: number;
    assertions?: AssertionResult[];
    metadata?: Record<string, unknown>;
  } = {}) {
    this.passed = data.passed ?? true;
    this.score = data.score ?? 1.0;
    this.assertions = data.assertions ?? [];
    this.metadata = data.metadata ?? {};
  }

  get failedAssertions(): AssertionResult[] {
    return this.assertions.filter((a) => !a.passed);
  }

  toDict(): Record<string, unknown> {
    return {
      passed: this.passed,
      score: this.score,
      assertions: this.assertions.map((a) => a.toDict()),
      metadata: this.metadata,
    };
  }
}

// re-export types
export { SpanKind, TokenUsage, makeTokenUsage };
