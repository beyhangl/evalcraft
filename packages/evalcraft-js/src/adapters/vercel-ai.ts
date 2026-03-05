/**
 * Vercel AI SDK adapter — auto-captures generateText / streamText calls.
 *
 * Wraps `generateText()` and `streamText()` from the `ai` package so every
 * call is automatically recorded into the active CaptureContext.
 *
 * Works with any provider (OpenAI, Anthropic, Google, etc.) because the
 * Vercel AI SDK abstracts providers behind a common LanguageModel interface.
 *
 * Usage:
 *
 *   import { trackedGenerateText, trackedStreamText } from 'evalcraft/adapters/vercel-ai'
 *   import { CaptureContext } from 'evalcraft'
 *   import { openai } from '@ai-sdk/openai'
 *
 *   const ctx = new CaptureContext({ name: 'weather_agent_test' })
 *   await ctx.run(async () => {
 *     const result = await trackedGenerateText({
 *       model: openai('gpt-4o-mini'),
 *       messages: [{ role: 'user', content: 'What is the weather?' }],
 *       tools: { get_weather: { ... } },
 *     })
 *   })
 *   console.log(ctx.cassette.spans)
 *
 * Spans are silently dropped when no CaptureContext is active — the adapter
 * is safe to leave in place during non-test code paths.
 */

import { generateText, streamText } from 'ai';
import { getActiveContext } from '../capture/recorder';
import { Span } from '../core/models';
import { SpanKind } from '../core/types';

// ---------------------------------------------------------------------------
// Pricing table — approximate cost per 1M tokens (input_usd, output_usd).
// Prices reflect public rates as of early 2026; update as needed.
// ---------------------------------------------------------------------------
const MODEL_PRICING: Record<string, [number, number]> = {
  // OpenAI
  'gpt-4o': [2.5, 10.0],
  'gpt-4o-mini': [0.15, 0.6],
  'gpt-4-turbo': [10.0, 30.0],
  'gpt-4': [30.0, 60.0],
  'gpt-3.5-turbo': [0.5, 1.5],
  o1: [15.0, 60.0],
  'o1-mini': [3.0, 12.0],
  'o3-mini': [1.1, 4.4],
  'o4-mini': [1.1, 4.4],
  // Anthropic (via @ai-sdk/anthropic)
  'claude-opus-4-6': [15.0, 75.0],
  'claude-sonnet-4-6': [3.0, 15.0],
  'claude-haiku-4-5-20251001': [0.8, 4.0],
  'claude-3-5-sonnet-20241022': [3.0, 15.0],
  'claude-3-5-haiku-20241022': [0.8, 4.0],
  'claude-3-opus-20240229': [15.0, 75.0],
  'claude-3-haiku-20240307': [0.25, 1.25],
  // Google (via @ai-sdk/google)
  'gemini-1.5-pro': [1.25, 5.0],
  'gemini-1.5-flash': [0.075, 0.3],
  'gemini-2.0-flash': [0.1, 0.4],
};

function estimateCost(
  modelId: string,
  promptTokens: number,
  completionTokens: number,
): number | null {
  let pricing = MODEL_PRICING[modelId];
  if (!pricing) {
    const entry = Object.entries(MODEL_PRICING).find(([key]) =>
      modelId.startsWith(key),
    );
    pricing = entry?.[1];
  }
  if (!pricing) return null;
  return (
    (promptTokens * pricing[0] + completionTokens * pricing[1]) / 1_000_000
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type MessageLike = { role: string; content: unknown };

function messagesToStr(
  messages: MessageLike[] | undefined,
  prompt: string | undefined,
): string {
  if (prompt) return prompt;
  if (!messages?.length) return '';
  return messages
    .map((msg) => {
      const role = msg.role;
      let content: string;
      if (typeof msg.content === 'string') {
        content = msg.content;
      } else if (Array.isArray(msg.content)) {
        content = (msg.content as Array<{ type: string; text?: string }>)
          .filter((p) => p.type === 'text')
          .map((p) => p.text ?? '')
          .join(' ');
      } else {
        content = String(msg.content ?? '');
      }
      return `${role}: ${content}`;
    })
    .join('\n');
}

function getModelId(model: unknown): string {
  if (model && typeof model === 'object') {
    const m = model as Record<string, unknown>;
    if (typeof m['modelId'] === 'string') return m['modelId'];
    if (typeof m['model'] === 'string') return m['model'];
  }
  return 'unknown';
}

type ToolCallLike = { toolName: string; args: unknown };

function toolCallsToOutputStr(toolCalls: ToolCallLike[]): string {
  return toolCalls
    .map((tc) => `[tool_call:${tc.toolName}(${JSON.stringify(tc.args)})]`)
    .join(' ');
}

// ---------------------------------------------------------------------------
// trackedGenerateText
// ---------------------------------------------------------------------------

export type GenerateTextParams = Parameters<typeof generateText>[0];
export type GenerateTextResult = Awaited<ReturnType<typeof generateText>>;

/**
 * Drop-in replacement for Vercel AI SDK's `generateText()`.
 *
 * Captures the model, messages, response text, token usage, tool calls, and
 * estimated cost into the active CaptureContext as a single LLM_RESPONSE span.
 * Each tool invocation is also recorded as a separate TOOL_CALL span.
 */
export async function trackedGenerateText(
  params: GenerateTextParams,
): Promise<GenerateTextResult> {
  const start = performance.now();
  const modelId = getModelId(params.model);
  const input = messagesToStr(
    params.messages as MessageLike[] | undefined,
    'prompt' in params ? (params as { prompt?: string }).prompt : undefined,
  );

  let result: GenerateTextResult;
  try {
    result = await generateText(params);
  } catch (err) {
    const duration_ms = performance.now() - start;
    const ctx = getActiveContext();
    if (ctx) {
      ctx.recordSpan(
        new Span({
          kind: SpanKind.LLM_RESPONSE,
          name: `llm:${modelId}`,
          duration_ms,
          input,
          model: modelId,
          error: err instanceof Error ? err.message : String(err),
        }),
      );
    }
    throw err;
  }

  const duration_ms = performance.now() - start;
  const ctx = getActiveContext();
  if (ctx) {
    const prompt_tokens = result.usage?.promptTokens ?? 0;
    const completion_tokens = result.usage?.completionTokens ?? 0;
    const toolCalls = (result.toolCalls as ToolCallLike[] | undefined) ?? [];

    // Record each tool invocation as an individual TOOL_CALL span.
    for (const tc of toolCalls) {
      ctx.recordToolCall({
        tool_name: tc.toolName,
        args: tc.args as Record<string, unknown>,
      });
    }

    // Append tool-call summaries to the LLM output string.
    let output: string = result.text ?? '';
    if (toolCalls.length > 0) {
      const toolStr = toolCallsToOutputStr(toolCalls);
      output = [output, toolStr].filter(Boolean).join(' ');
    }

    ctx.recordLlmCall({
      model: modelId,
      input,
      output,
      duration_ms,
      prompt_tokens,
      completion_tokens,
      cost_usd: estimateCost(modelId, prompt_tokens, completion_tokens),
      metadata: { finish_reason: result.finishReason },
    });
  }

  return result;
}

// ---------------------------------------------------------------------------
// trackedStreamText
// ---------------------------------------------------------------------------

export type StreamTextParams = Parameters<typeof streamText>[0];
export type StreamTextResult = ReturnType<typeof streamText>;

/**
 * Drop-in replacement for Vercel AI SDK's `streamText()`.
 *
 * Records the completed call into the active CaptureContext after the stream
 * finishes — specifically when the returned `result.text` promise resolves.
 *
 * The recording is lazy and memoized: it triggers the first time `result.text`
 * is awaited and is guaranteed to run at most once regardless of how many
 * times `result.text` is accessed.
 */
export function trackedStreamText(params: StreamTextParams): StreamTextResult {
  const start = performance.now();
  const modelId = getModelId(params.model);
  const input = messagesToStr(
    params.messages as MessageLike[] | undefined,
    'prompt' in params ? (params as { prompt?: string }).prompt : undefined,
  );

  const result = streamText(params);

  // Memoize the tracked text promise so recording happens exactly once.
  let memoizedText: Promise<string> | undefined;

  return new Proxy(result, {
    get(target, prop, receiver) {
      if (prop === 'text') {
        if (!memoizedText) {
          memoizedText = (target.text as Promise<string>).then(
            async (text: string) => {
              const duration_ms = performance.now() - start;
              const ctx = getActiveContext();
              if (ctx) {
                try {
                  const usage = await (
                    target.usage as Promise<
                      | {
                          promptTokens: number;
                          completionTokens: number;
                        }
                      | undefined
                    >
                  );
                  const prompt_tokens = usage?.promptTokens ?? 0;
                  const completion_tokens = usage?.completionTokens ?? 0;
                  ctx.recordLlmCall({
                    model: modelId,
                    input,
                    output: text,
                    duration_ms,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd: estimateCost(
                      modelId,
                      prompt_tokens,
                      completion_tokens,
                    ),
                    metadata: { streaming: true },
                  });
                } catch {
                  // Recording errors must never surface to the caller.
                }
              }
              return text;
            },
          );
        }
        return memoizedText;
      }
      const val = Reflect.get(target, prop, receiver);
      return typeof val === 'function'
        ? (val as (...args: unknown[]) => unknown).bind(target)
        : val;
    },
  }) as StreamTextResult;
}
