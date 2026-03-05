import { getActiveContext } from '../capture/recorder.js';

export interface MockResponse {
  content: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  finish_reason: string;
  tool_calls: Record<string, unknown>[] | null;
  metadata: Record<string, unknown>;
}

function makeMockResponse(
  content: string,
  model: string,
  prompt_tokens = 10,
  completion_tokens = 20,
  tool_calls: Record<string, unknown>[] | null = null,
): MockResponse {
  return {
    content,
    model,
    prompt_tokens,
    completion_tokens,
    finish_reason: 'stop',
    tool_calls,
    metadata: {},
  };
}

export class MockLLM {
  model: string;
  defaultResponse: string;

  private _exactResponses: Map<string, MockResponse[]> = new Map();
  private _patternResponses: Array<[RegExp, MockResponse[]]> = [];
  private _wildcardResponses: MockResponse[] = [];
  private _responseFn: ((prompt: string) => MockResponse) | null = null;
  private _callHistory: Array<{
    prompt: string;
    response: string;
    kwargs: Record<string, unknown>;
  }> = [];
  private _callCount = 0;

  constructor(model = 'mock-llm', defaultResponse = '') {
    this.model = model;
    this.defaultResponse = defaultResponse;
  }

  addResponse(
    prompt: string,
    content: string,
    promptTokens = 10,
    completionTokens = 20,
    toolCalls: Record<string, unknown>[] | null = null,
  ): this {
    const response = makeMockResponse(
      content,
      this.model,
      promptTokens,
      completionTokens,
      toolCalls,
    );
    if (prompt === '*') {
      this._wildcardResponses.push(response);
    } else {
      if (!this._exactResponses.has(prompt)) {
        this._exactResponses.set(prompt, []);
      }
      this._exactResponses.get(prompt)!.push(response);
    }
    return this;
  }

  addPatternResponse(
    pattern: string,
    content: string,
    promptTokens = 10,
    completionTokens = 20,
  ): this {
    const response = makeMockResponse(
      content,
      this.model,
      promptTokens,
      completionTokens,
    );
    this._patternResponses.push([new RegExp(pattern, 'i'), [response]]);
    return this;
  }

  addSequentialResponses(prompt: string, contents: string[]): this {
    const responses = contents.map((c) =>
      makeMockResponse(c, this.model, 10, 20),
    );
    if (prompt === '*') {
      this._wildcardResponses.push(...responses);
    } else {
      this._exactResponses.set(prompt, responses);
    }
    return this;
  }

  setResponseFn(fn: (prompt: string) => MockResponse): this {
    this._responseFn = fn;
    return this;
  }

  complete(prompt: string, kwargs: Record<string, unknown> = {}): MockResponse {
    const start = Date.now();
    const response = this._resolveResponse(prompt);
    const duration_ms = Date.now() - start;

    this._callHistory.push({ prompt, response: response.content, kwargs });
    this._callCount += 1;

    const ctx = getActiveContext();
    if (ctx) {
      ctx.recordLlmCall({
        model: this.model,
        input: prompt,
        output: response.content,
        duration_ms,
        prompt_tokens: response.prompt_tokens,
        completion_tokens: response.completion_tokens,
      });
    }

    return response;
  }

  private _resolveResponse(prompt: string): MockResponse {
    if (this._responseFn) return this._responseFn(prompt);

    if (this._exactResponses.has(prompt)) {
      const responses = this._exactResponses.get(prompt)!;
      const idx = Math.min(this._callCount, responses.length - 1);
      return responses[idx];
    }

    for (const [pattern, responses] of this._patternResponses) {
      if (pattern.test(prompt)) {
        const idx = Math.min(this._callCount, responses.length - 1);
        return responses[idx];
      }
    }

    if (this._wildcardResponses.length > 0) {
      const idx = Math.min(
        this._callCount,
        this._wildcardResponses.length - 1,
      );
      return this._wildcardResponses[idx];
    }

    return makeMockResponse(this.defaultResponse, this.model, 10, 5);
  }

  get callCount(): number {
    return this._callCount;
  }

  get callHistory(): typeof this._callHistory {
    return this._callHistory;
  }

  reset(): void {
    this._callHistory = [];
    this._callCount = 0;
  }

  assertCalled(times?: number): void {
    if (this._callCount === 0) {
      throw new Error('MockLLM was never called');
    }
    if (times != null && this._callCount !== times) {
      throw new Error(
        `MockLLM was called ${this._callCount} times, expected ${times}`,
      );
    }
  }

  assertCalledWith(prompt: string): void {
    const prompts = this._callHistory.map((c) => c.prompt);
    if (!prompts.includes(prompt)) {
      throw new Error(
        `MockLLM was never called with prompt: ${JSON.stringify(prompt)}\nActual prompts: ${JSON.stringify(prompts)}`,
      );
    }
  }
}
