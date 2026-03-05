import { getActiveContext } from '../capture/recorder.js';

export class ToolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ToolError';
  }
}

export class MockTool {
  name: string;
  description: string;

  private _returnValue: unknown = null;
  private _returnFn: ((...args: unknown[]) => unknown) | null = null;
  private _sequentialReturns: unknown[] = [];
  private _error: string | null = null;
  private _errorAfter: number | null = null;
  private _latencyMs = 0;
  private _callHistory: Array<{
    args: Record<string, unknown>;
    result: unknown;
    error: string | null;
  }> = [];
  private _callCount = 0;

  constructor(name: string, description = '') {
    this.name = name;
    this.description = description;
  }

  returns(value: unknown): this {
    this._returnValue = value;
    return this;
  }

  returnsFn(fn: (...args: unknown[]) => unknown): this {
    this._returnFn = fn;
    return this;
  }

  returnsSequence(values: unknown[]): this {
    this._sequentialReturns = values;
    return this;
  }

  raises(error: string): this {
    this._error = error;
    return this;
  }

  raisesAfter(nCalls: number, error: string): this {
    this._errorAfter = nCalls;
    this._error = error;
    return this;
  }

  withLatency(ms: number): this {
    this._latencyMs = ms;
    return this;
  }

  call(kwargs: Record<string, unknown> = {}): unknown {
    const start = Date.now();

    if (this._latencyMs > 0) {
      // Synchronous busy-wait (only used in tests with tiny values)
      const end = start + this._latencyMs;
      while (Date.now() < end) {
        /* spin */
      }
    }

    let error: string | null = null;
    if (
      this._errorAfter != null &&
      this._callCount >= this._errorAfter
    ) {
      error = this._error;
    } else if (this._error && this._errorAfter == null) {
      error = this._error;
    }

    let result: unknown = null;
    if (!error) {
      if (this._returnFn) {
        result = this._returnFn(kwargs);
      } else if (this._sequentialReturns.length > 0) {
        const idx = Math.min(this._callCount, this._sequentialReturns.length - 1);
        result = this._sequentialReturns[idx];
      } else {
        result = this._returnValue;
      }
    }

    const duration_ms = Date.now() - start;

    this._callHistory.push({ args: kwargs, result, error });
    this._callCount += 1;

    const ctx = getActiveContext();
    if (ctx) {
      ctx.recordToolCall({
        tool_name: this.name,
        args: kwargs,
        result,
        duration_ms,
        error,
      });
    }

    if (error) throw new ToolError(error);
    return result;
  }

  /** Allow calling as a function directly. */
  invoke(kwargs: Record<string, unknown> = {}): unknown {
    return this.call(kwargs);
  }

  get callCount(): number {
    return this._callCount;
  }

  get callHistory(): typeof this._callHistory {
    return this._callHistory;
  }

  get lastCall(): (typeof this._callHistory)[0] | null {
    return this._callHistory.length > 0
      ? this._callHistory[this._callHistory.length - 1]
      : null;
  }

  reset(): void {
    this._callHistory = [];
    this._callCount = 0;
  }

  assertCalled(times?: number): void {
    if (this._callCount === 0) {
      throw new Error(`MockTool '${this.name}' was never called`);
    }
    if (times != null && this._callCount !== times) {
      throw new Error(
        `MockTool '${this.name}' was called ${this._callCount} times, expected ${times}`,
      );
    }
  }

  assertCalledWith(expectedKwargs: Record<string, unknown>): void {
    const matched = this._callHistory.some((call) =>
      Object.entries(expectedKwargs).every(
        ([k, v]) => call.args[k] === v,
      ),
    );
    if (!matched) {
      throw new Error(
        `MockTool '${this.name}' was never called with args: ${JSON.stringify(expectedKwargs)}\n` +
          `Actual calls: ${JSON.stringify(this._callHistory.map((c) => c.args))}`,
      );
    }
  }

  assertNotCalled(): void {
    if (this._callCount > 0) {
      throw new Error(
        `MockTool '${this.name}' was called ${this._callCount} times, expected 0`,
      );
    }
  }
}
