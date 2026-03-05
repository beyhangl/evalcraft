import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CaptureContext, getActiveContext } from '../src/capture/recorder';
import {
  trackedGenerateText,
  trackedStreamText,
} from '../src/adapters/vercel-ai';
import { SpanKind } from '../src/core/types';

// ---------------------------------------------------------------------------
// Mock the 'ai' package — hoisted before imports by vitest.
// ---------------------------------------------------------------------------

vi.mock('ai', () => ({
  generateText: vi.fn(),
  streamText: vi.fn(),
}));

import { generateText, streamText } from 'ai';

// Minimal mock model object matching the LanguageModelV1 shape.
const mockModel = {
  modelId: 'gpt-4o-mini',
  provider: 'openai.chat',
  specificationVersion: 'v1' as const,
};

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeGenerateResult(overrides: {
  text?: string;
  usage?: { promptTokens: number; completionTokens: number; totalTokens: number };
  toolCalls?: Array<{
    type: 'tool-call';
    toolCallId: string;
    toolName: string;
    args: unknown;
  }>;
  finishReason?: string;
} = {}) {
  return {
    text: overrides.text ?? 'Hello world',
    usage: overrides.usage ?? {
      promptTokens: 10,
      completionTokens: 5,
      totalTokens: 15,
    },
    toolCalls: overrides.toolCalls ?? [],
    finishReason: overrides.finishReason ?? 'stop',
    steps: [],
    response: { id: 'resp-1', modelId: 'gpt-4o-mini', timestamp: new Date() },
  };
}

// ---------------------------------------------------------------------------
// trackedGenerateText
// ---------------------------------------------------------------------------

describe('trackedGenerateText', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns the same result as generateText', async () => {
    const expected = makeGenerateResult({ text: 'The weather is sunny.' });
    vi.mocked(generateText).mockResolvedValueOnce(expected as any);

    const result = await trackedGenerateText({
      model: mockModel as any,
      messages: [{ role: 'user', content: 'What is the weather?' }],
    });

    expect(result.text).toBe('The weather is sunny.');
  });

  it('records an LLM span in the active CaptureContext', async () => {
    const mockResult = makeGenerateResult({
      text: 'Paris.',
      usage: { promptTokens: 20, completionTokens: 3, totalTokens: 23 },
    });
    vi.mocked(generateText).mockResolvedValueOnce(mockResult as any);

    const ctx = new CaptureContext({ name: 'test-run' });
    await ctx.run(async () => {
      await trackedGenerateText({
        model: mockModel as any,
        messages: [{ role: 'user', content: 'Capital of France?' }],
      });
    });

    const llmSpans = ctx.cassette.spans.filter(
      (s) => s.kind === SpanKind.LLM_RESPONSE,
    );
    expect(llmSpans).toHaveLength(1);

    const span = llmSpans[0];
    expect(span.model).toBe('gpt-4o-mini');
    expect(span.output).toBe('Paris.');
    expect(span.input).toBe('user: Capital of France?');
    expect(span.token_usage?.prompt_tokens).toBe(20);
    expect(span.token_usage?.completion_tokens).toBe(3);
    expect(span.token_usage?.total_tokens).toBe(23);
    expect(span.duration_ms).toBeGreaterThanOrEqual(0);
  });

  it('records tool call spans when tools are invoked', async () => {
    const mockResult = makeGenerateResult({
      text: '',
      toolCalls: [
        {
          type: 'tool-call',
          toolCallId: 'tc-1',
          toolName: 'get_weather',
          args: { city: 'London' },
        },
      ],
      finishReason: 'tool-calls',
    });
    vi.mocked(generateText).mockResolvedValueOnce(mockResult as any);

    const ctx = new CaptureContext({ name: 'tool-test' });
    await ctx.run(async () => {
      await trackedGenerateText({
        model: mockModel as any,
        messages: [{ role: 'user', content: 'Weather in London?' }],
      });
    });

    const toolSpans = ctx.cassette.spans.filter(
      (s) => s.kind === SpanKind.TOOL_CALL,
    );
    expect(toolSpans).toHaveLength(1);
    expect(toolSpans[0].tool_name).toBe('get_weather');
    expect(toolSpans[0].tool_args).toEqual({ city: 'London' });

    const llmSpan = ctx.cassette.spans.find(
      (s) => s.kind === SpanKind.LLM_RESPONSE,
    );
    expect(llmSpan?.output).toContain(
      '[tool_call:get_weather({"city":"London"})]',
    );
  });

  it('records multiple tool calls in order', async () => {
    const mockResult = makeGenerateResult({
      toolCalls: [
        { type: 'tool-call', toolCallId: 'tc-1', toolName: 'search', args: { q: 'news' } },
        { type: 'tool-call', toolCallId: 'tc-2', toolName: 'summarize', args: { text: '...' } },
      ],
      finishReason: 'tool-calls',
    });
    vi.mocked(generateText).mockResolvedValueOnce(mockResult as any);

    const ctx = new CaptureContext({ name: 'multi-tool-test' });
    await ctx.run(async () => {
      await trackedGenerateText({
        model: mockModel as any,
        messages: [{ role: 'user', content: 'Summarize news' }],
      });
    });

    const toolSpans = ctx.cassette.spans.filter(
      (s) => s.kind === SpanKind.TOOL_CALL,
    );
    expect(toolSpans).toHaveLength(2);
    expect(toolSpans[0].tool_name).toBe('search');
    expect(toolSpans[1].tool_name).toBe('summarize');
  });

  it('records error span and re-throws when generateText fails', async () => {
    vi.mocked(generateText).mockRejectedValueOnce(
      new Error('API rate limited'),
    );

    const ctx = new CaptureContext({ name: 'error-test' });
    await expect(
      ctx.run(async () => {
        await trackedGenerateText({
          model: mockModel as any,
          messages: [{ role: 'user', content: 'Hello' }],
        });
      }),
    ).rejects.toThrow('API rate limited');

    const errorSpans = ctx.cassette.spans.filter((s) => s.error != null);
    expect(errorSpans).toHaveLength(1);
    expect(errorSpans[0].error).toBe('API rate limited');
    expect(errorSpans[0].model).toBe('gpt-4o-mini');
  });

  it('does not throw when no CaptureContext is active', async () => {
    const mockResult = makeGenerateResult();
    vi.mocked(generateText).mockResolvedValueOnce(mockResult as any);

    await expect(
      trackedGenerateText({
        model: mockModel as any,
        messages: [{ role: 'user', content: 'Hello' }],
      }),
    ).resolves.toBeDefined();
  });

  it('estimates cost for known models', async () => {
    const mockResult = makeGenerateResult({
      usage: { promptTokens: 1000, completionTokens: 500, totalTokens: 1500 },
    });
    vi.mocked(generateText).mockResolvedValueOnce(mockResult as any);

    const ctx = new CaptureContext({ name: 'cost-test' });
    await ctx.run(async () => {
      await trackedGenerateText({
        model: mockModel as any,
        messages: [{ role: 'user', content: 'Hello' }],
      });
    });

    const span = ctx.cassette.spans.find(
      (s) => s.kind === SpanKind.LLM_RESPONSE,
    );
    // gpt-4o-mini: $0.15/$0.60 per 1M tokens
    // cost = (1000 * 0.15 + 500 * 0.60) / 1_000_000 = 0.00045
    expect(span?.cost_usd).toBeCloseTo(0.00045, 6);
  });

  it('handles multi-modal content in messages', async () => {
    const mockResult = makeGenerateResult({ text: 'I see a cat.' });
    vi.mocked(generateText).mockResolvedValueOnce(mockResult as any);

    const ctx = new CaptureContext();
    await ctx.run(async () => {
      await trackedGenerateText({
        model: mockModel as any,
        messages: [
          {
            role: 'user',
            content: [
              { type: 'text', text: 'What is in this image?' },
              { type: 'image', image: 'base64data' },
            ],
          },
        ],
      });
    });

    const span = ctx.cassette.spans.find(
      (s) => s.kind === SpanKind.LLM_RESPONSE,
    );
    expect(span?.input).toBe('user: What is in this image?');
  });

  it('works with Anthropic models via @ai-sdk/anthropic', async () => {
    const anthropicModel = {
      modelId: 'claude-3-5-sonnet-20241022',
      provider: 'anthropic.messages',
    };
    const mockResult = makeGenerateResult({
      text: 'Hello from Claude.',
      usage: { promptTokens: 50, completionTokens: 10, totalTokens: 60 },
    });
    vi.mocked(generateText).mockResolvedValueOnce(mockResult as any);

    const ctx = new CaptureContext({ name: 'anthropic-test' });
    await ctx.run(async () => {
      await trackedGenerateText({
        model: anthropicModel as any,
        messages: [{ role: 'user', content: 'Hi' }],
      });
    });

    const span = ctx.cassette.spans.find(
      (s) => s.kind === SpanKind.LLM_RESPONSE,
    );
    expect(span?.model).toBe('claude-3-5-sonnet-20241022');
    // Anthropic claude-3-5-sonnet: $3/$15 per 1M tokens
    expect(span?.cost_usd).toBeCloseTo(
      (50 * 3 + 10 * 15) / 1_000_000,
      6,
    );
  });

  it('records finish_reason in span metadata', async () => {
    const mockResult = makeGenerateResult({ finishReason: 'tool-calls' });
    vi.mocked(generateText).mockResolvedValueOnce(mockResult as any);

    const ctx = new CaptureContext({ name: 'finish-reason-test' });
    await ctx.run(async () => {
      await trackedGenerateText({
        model: mockModel as any,
        messages: [{ role: 'user', content: 'Hello' }],
      });
    });

    const span = ctx.cassette.spans.find(
      (s) => s.kind === SpanKind.LLM_RESPONSE,
    );
    expect(span?.metadata?.finish_reason).toBe('tool-calls');
  });
});

// ---------------------------------------------------------------------------
// trackedStreamText
// ---------------------------------------------------------------------------

describe('trackedStreamText', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('records an LLM span after stream completes', async () => {
    const textPromise = Promise.resolve('Streaming response here.');
    const usagePromise = Promise.resolve({
      promptTokens: 15,
      completionTokens: 8,
      totalTokens: 23,
    });
    vi.mocked(streamText).mockReturnValueOnce({
      text: textPromise,
      usage: usagePromise,
      textStream: (async function* () {
        yield 'Streaming response here.';
      })(),
    } as any);

    const ctx = new CaptureContext({ name: 'stream-test' });
    await ctx.run(async () => {
      const result = trackedStreamText({
        model: mockModel as any,
        messages: [{ role: 'user', content: 'Tell me something.' }],
      });
      await result.text;
    });

    const llmSpans = ctx.cassette.spans.filter(
      (s) => s.kind === SpanKind.LLM_RESPONSE,
    );
    expect(llmSpans).toHaveLength(1);

    const span = llmSpans[0];
    expect(span.model).toBe('gpt-4o-mini');
    expect(span.output).toBe('Streaming response here.');
    expect(span.token_usage?.prompt_tokens).toBe(15);
    expect(span.token_usage?.completion_tokens).toBe(8);
    expect(span.metadata).toMatchObject({ streaming: true });
  });

  it('passes through all original stream properties', () => {
    const textStream = (async function* () {
      yield 'chunk1';
      yield 'chunk2';
    })();
    vi.mocked(streamText).mockReturnValueOnce({
      text: Promise.resolve('chunk1chunk2'),
      usage: Promise.resolve({
        promptTokens: 5,
        completionTokens: 5,
        totalTokens: 10,
      }),
      textStream,
      fullStream: (async function* () {})(),
    } as any);

    const result = trackedStreamText({
      model: mockModel as any,
      messages: [{ role: 'user', content: 'Hello' }],
    });

    // Original stream properties should be accessible via the Proxy.
    expect(result).toHaveProperty('textStream');
    expect(result).toHaveProperty('fullStream');
  });

  it('does not throw when no CaptureContext is active', async () => {
    vi.mocked(streamText).mockReturnValueOnce({
      text: Promise.resolve('ok'),
      usage: Promise.resolve({
        promptTokens: 1,
        completionTokens: 1,
        totalTokens: 2,
      }),
    } as any);

    const result = trackedStreamText({
      model: mockModel as any,
      messages: [{ role: 'user', content: 'Hello' }],
    });
    await expect(result.text).resolves.toBe('ok');
  });

  it('memoizes the text promise — records exactly once even if accessed twice', async () => {
    const textPromise = Promise.resolve('hello');
    const usagePromise = Promise.resolve({
      promptTokens: 5,
      completionTokens: 3,
      totalTokens: 8,
    });
    vi.mocked(streamText).mockReturnValueOnce({
      text: textPromise,
      usage: usagePromise,
    } as any);

    const ctx = new CaptureContext({ name: 'memoize-test' });
    await ctx.run(async () => {
      const result = trackedStreamText({
        model: mockModel as any,
        messages: [{ role: 'user', content: 'Hi' }],
      });
      // Access .text twice; both should resolve to the same value.
      const [t1, t2] = await Promise.all([result.text, result.text]);
      expect(t1).toBe('hello');
      expect(t2).toBe('hello');
    });

    const llmSpans = ctx.cassette.spans.filter(
      (s) => s.kind === SpanKind.LLM_RESPONSE,
    );
    // Should only have ONE span despite two .text accesses.
    expect(llmSpans).toHaveLength(1);
  });

  it('records streaming flag in span metadata', async () => {
    vi.mocked(streamText).mockReturnValueOnce({
      text: Promise.resolve('streamed'),
      usage: Promise.resolve({ promptTokens: 2, completionTokens: 2, totalTokens: 4 }),
    } as any);

    const ctx = new CaptureContext({ name: 'streaming-meta-test' });
    await ctx.run(async () => {
      const result = trackedStreamText({
        model: mockModel as any,
        messages: [{ role: 'user', content: 'Hello' }],
      });
      await result.text;
    });

    const span = ctx.cassette.spans.find(
      (s) => s.kind === SpanKind.LLM_RESPONSE,
    );
    expect(span?.metadata?.streaming).toBe(true);
  });
});
