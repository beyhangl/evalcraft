import { Cassette, Span, AgentRun } from '../core/models.js';
import { SpanKind } from '../core/types.js';

// ── ReplayDiff ────────────────────────────────────────────────────────────────

export class ReplayDiff {
  toolSequenceChanged = false;
  outputChanged = false;
  tokenCountChanged = false;
  costChanged = false;
  spanCountChanged = false;

  oldToolSequence: string[] = [];
  newToolSequence: string[] = [];
  oldOutput = '';
  newOutput = '';
  oldTokens = 0;
  newTokens = 0;
  oldCost = 0;
  newCost = 0;
  oldSpanCount = 0;
  newSpanCount = 0;

  get hasChanges(): boolean {
    return (
      this.toolSequenceChanged ||
      this.outputChanged ||
      this.tokenCountChanged ||
      this.costChanged ||
      this.spanCountChanged
    );
  }

  static compute(oldCassette: Cassette, newCassette: Cassette): ReplayDiff {
    const diff = new ReplayDiff();

    diff.oldToolSequence = oldCassette.getToolSequence();
    diff.newToolSequence = newCassette.getToolSequence();
    diff.toolSequenceChanged =
      JSON.stringify(diff.oldToolSequence) !==
      JSON.stringify(diff.newToolSequence);

    diff.oldOutput = oldCassette.output_text;
    diff.newOutput = newCassette.output_text;
    diff.outputChanged = diff.oldOutput !== diff.newOutput;

    diff.oldTokens = oldCassette.total_tokens;
    diff.newTokens = newCassette.total_tokens;
    diff.tokenCountChanged = diff.oldTokens !== diff.newTokens;

    diff.oldCost = oldCassette.total_cost_usd;
    diff.newCost = newCassette.total_cost_usd;
    diff.costChanged = diff.oldCost !== diff.newCost;

    diff.oldSpanCount = oldCassette.spans.length;
    diff.newSpanCount = newCassette.spans.length;
    diff.spanCountChanged = diff.oldSpanCount !== diff.newSpanCount;

    return diff;
  }

  toDict(): Record<string, unknown> {
    return {
      has_changes: this.hasChanges,
      tool_sequence_changed: this.toolSequenceChanged,
      output_changed: this.outputChanged,
      token_count_changed: this.tokenCountChanged,
      cost_changed: this.costChanged,
      span_count_changed: this.spanCountChanged,
      old_tool_sequence: this.oldToolSequence,
      new_tool_sequence: this.newToolSequence,
      old_output: this.oldOutput,
      new_output: this.newOutput,
      old_tokens: this.oldTokens,
      new_tokens: this.newTokens,
      old_cost: this.oldCost,
      new_cost: this.newCost,
    };
  }

  summary(): string {
    if (!this.hasChanges) return 'No changes detected.';
    const parts: string[] = [];
    if (this.toolSequenceChanged) {
      parts.push(
        `Tool sequence: ${JSON.stringify(this.oldToolSequence)} → ${JSON.stringify(this.newToolSequence)}`,
      );
    }
    if (this.outputChanged) parts.push('Output text changed');
    if (this.tokenCountChanged) {
      parts.push(`Tokens: ${this.oldTokens} → ${this.newTokens}`);
    }
    if (this.costChanged) {
      parts.push(
        `Cost: $${this.oldCost.toFixed(4)} → $${this.newCost.toFixed(4)}`,
      );
    }
    if (this.spanCountChanged) {
      parts.push(`Spans: ${this.oldSpanCount} → ${this.newSpanCount}`);
    }
    return parts.join('\n');
  }
}

// ── ReplayEngine ──────────────────────────────────────────────────────────────

export class ReplayEngine {
  cassette: Cassette;
  private _toolOverrides: Map<string, unknown> = new Map();
  private _llmOverrides: Map<number, unknown> = new Map();
  private _spanFilter: ((span: Span) => boolean) | null = null;
  private _currentIndex = 0;

  constructor(cassette: Cassette | string) {
    if (typeof cassette === 'string') {
      this.cassette = Cassette.load(cassette);
    } else {
      this.cassette = Cassette.fromDict(
        JSON.parse(JSON.stringify(cassette.toDict())) as Record<string, unknown>,
      );
    }
  }

  get spans(): Span[] {
    if (this._spanFilter) {
      return this.cassette.spans.filter(this._spanFilter);
    }
    return this.cassette.spans;
  }

  overrideToolResult(toolName: string, result: unknown): this {
    this._toolOverrides.set(toolName, result);
    return this;
  }

  overrideLlmResponse(callIndex: number, response: unknown): this {
    this._llmOverrides.set(callIndex, response);
    return this;
  }

  filterSpans(predicate: (span: Span) => boolean): this {
    this._spanFilter = predicate;
    return this;
  }

  run(): AgentRun {
    const replayed = Cassette.fromDict(
      JSON.parse(JSON.stringify(this.cassette.toDict())) as Record<
        string,
        unknown
      >,
    );
    const replayedSpans: Span[] = [];
    let llmCallIndex = 0;

    for (const span of this.spans) {
      const rs = span.clone();

      if (
        rs.kind === SpanKind.TOOL_CALL &&
        rs.tool_name != null &&
        this._toolOverrides.has(rs.tool_name)
      ) {
        rs.tool_result = this._toolOverrides.get(rs.tool_name);
        rs.output = this._toolOverrides.get(rs.tool_name);
      }

      if (
        rs.kind === SpanKind.LLM_REQUEST ||
        rs.kind === SpanKind.LLM_RESPONSE
      ) {
        if (this._llmOverrides.has(llmCallIndex)) {
          rs.output = this._llmOverrides.get(llmCallIndex);
        }
        llmCallIndex += 1;
      }

      replayedSpans.push(rs);
    }

    replayed.spans = replayedSpans;
    replayed.computeMetrics();
    replayed.computeFingerprint();

    return new AgentRun(replayed, true, null, true);
  }

  step(): Span | null {
    const spans = this.spans;
    if (this._currentIndex >= spans.length) return null;

    const span = spans[this._currentIndex].clone();

    if (
      span.kind === SpanKind.TOOL_CALL &&
      span.tool_name != null &&
      this._toolOverrides.has(span.tool_name)
    ) {
      span.tool_result = this._toolOverrides.get(span.tool_name);
      span.output = this._toolOverrides.get(span.tool_name);
    }

    this._currentIndex += 1;
    return span;
  }

  reset(): void {
    this._currentIndex = 0;
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

  diff(other: Cassette | string): ReplayDiff {
    const otherCassette =
      typeof other === 'string' ? Cassette.load(other) : other;
    return ReplayDiff.compute(this.cassette, otherCassette);
  }
}

// ── Convenience function ──────────────────────────────────────────────────────

export function replay(
  cassettePath: string,
  toolOverrides?: Record<string, unknown>,
): AgentRun {
  const engine = new ReplayEngine(cassettePath);
  if (toolOverrides) {
    for (const [name, result] of Object.entries(toolOverrides)) {
      engine.overrideToolResult(name, result);
    }
  }
  return engine.run();
}
