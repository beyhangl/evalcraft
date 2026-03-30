/**
 * Google Gemini adapter — wraps GenerativeModel to auto-record spans.
 *
 * Usage:
 *   import { GoogleGenerativeAI } from '@google/generative-ai';
 *   import { wrapGemini } from 'evalcraft/adapters/gemini';
 *   import { CaptureContext } from 'evalcraft';
 *
 *   const genAI = new GoogleGenerativeAI('...');
 *   const model = wrapGemini(genAI.getGenerativeModel({ model: 'gemini-2.0-flash' }));
 *
 *   const ctx = new CaptureContext({ name: 'gemini_test' });
 *   await ctx.run(async () => {
 *     const result = await model.generateContent('What is the weather?');
 *     console.log(result.response.text());
 *   });
 *
 * Spans are silently dropped when no CaptureContext is active.
 */

import { getActiveContext } from '../capture/recorder.js';
import { Span } from '../core/models.js';
import { SpanKind, makeTokenUsage } from '../core/types.js';

// ---------------------------------------------------------------------------
// Pricing table — approximate cost per 1M tokens (input_usd, output_usd).
// ---------------------------------------------------------------------------
const MODEL_PRICING: Record<string, [number, number]> = {
  'gemini-2.5-pro': [1.25, 10.0],
  'gemini-2.5-flash': [0.15, 0.6],
  'gemini-2.0-flash': [0.1, 0.4],
  'gemini-2.0-flash-lite': [0.075, 0.3],
  'gemini-1.5-pro': [1.25, 5.0],
  'gemini-1.5-pro-latest': [1.25, 5.0],
  'gemini-1.5-flash': [0.075, 0.3],
  'gemini-1.5-flash-latest': [0.075, 0.3],
  'gemini-1.5-flash-8b': [0.0375, 0.15],
  'gemini-1.0-pro': [0.5, 1.5],
  'gemini-pro': [0.5, 1.5],
};

function estimateCost(
  modelId: string,
  promptTokens: number,
  completionTokens: number,
): number | null {
  let pricing: [number, number] | undefined = MODEL_PRICING[modelId];
  if (!pricing) {
    const entry = Object.entries(MODEL_PRICING).find(([key]) =>
      modelId.startsWith(key),
    );
    pricing = entry?.[1] as [number, number] | undefined;
  }
  if (!pricing) return null;
  return (promptTokens * pricing[0] + completionTokens * pricing[1]) / 1_000_000;
}

// ---------------------------------------------------------------------------
// Types for the Gemini SDK (generic to avoid hard dependency)
// ---------------------------------------------------------------------------

interface UsageMetadata {
  promptTokenCount?: number;
  candidatesTokenCount?: number;
  totalTokenCount?: number;
}

interface Part {
  text?: string;
  functionCall?: { name: string; args: Record<string, unknown> };
}

interface Candidate {
  content?: { parts?: Part[] };
  finishReason?: string;
}

interface GenerateContentResponse {
  text?: () => string;
  candidates?: Candidate[];
  usageMetadata?: UsageMetadata;
}

interface GenerateContentResult {
  response: GenerateContentResponse;
}

interface GeminiModelLike {
  model?: string;
  generateContent: (request: unknown) => Promise<GenerateContentResult>;
  generateContentStream?: (request: unknown) => Promise<unknown>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractModelName(model: GeminiModelLike): string {
  const name = model.model ?? 'unknown';
  // Strip "models/" prefix
  if (typeof name === 'string' && name.startsWith('models/')) {
    return name.slice(7);
  }
  return name;
}

function responseToStr(response: GenerateContentResponse): string {
  // Try the .text() convenience method
  try {
    const text = response.text?.();
    if (text) return text;
  } catch {
    // Fall through to candidate parsing
  }

  // Parse candidates
  const parts: string[] = [];
  for (const candidate of response.candidates ?? []) {
    for (const part of candidate.content?.parts ?? []) {
      if (part.text) {
        parts.push(part.text);
      } else if (part.functionCall) {
        parts.push(
          `[function_call:${part.functionCall.name}(${JSON.stringify(part.functionCall.args)})]`,
        );
      }
    }
  }
  return parts.join(' ');
}

function contentsToStr(contents: unknown): string {
  if (typeof contents === 'string') return contents;
  if (Array.isArray(contents)) {
    return contents
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          const obj = item as Record<string, unknown>;
          const role = (obj['role'] as string) ?? '';
          const parts = obj['parts'] as unknown[];
          if (Array.isArray(parts)) {
            const texts = parts
              .map((p) => {
                if (typeof p === 'string') return p;
                if (p && typeof p === 'object' && 'text' in p) return (p as { text: string }).text;
                return '';
              })
              .filter(Boolean);
            return role ? `${role}: ${texts.join(' ')}` : texts.join(' ');
          }
        }
        return String(item);
      })
      .join('\n');
  }
  return String(contents);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Wrap a Gemini `GenerativeModel` to auto-record all `generateContent()` calls.
 *
 * Returns the same model instance with patched methods — all existing API is preserved.
 */
export function wrapGemini<T extends GeminiModelLike>(model: T): T {
  const originalGenerate = model.generateContent.bind(model);
  const modelId = extractModelName(model);

  model.generateContent = async (request: unknown): Promise<GenerateContentResult> => {
    const start = performance.now();
    let result: GenerateContentResult;

    try {
      result = await originalGenerate(request);
    } catch (err) {
      const duration_ms = performance.now() - start;
      const ctx = getActiveContext();
      if (ctx) {
        ctx.recordSpan(
          new Span({
            kind: SpanKind.LLM_RESPONSE,
            name: `llm:${modelId}`,
            duration_ms,
            input: contentsToStr(request),
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
      const response = result.response;
      const promptTokens = response.usageMetadata?.promptTokenCount ?? 0;
      const completionTokens = response.usageMetadata?.candidatesTokenCount ?? 0;

      // Record function calls as separate tool spans
      for (const candidate of response.candidates ?? []) {
        for (const part of candidate.content?.parts ?? []) {
          if (part.functionCall) {
            ctx.recordToolCall({
              tool_name: part.functionCall.name,
              args: part.functionCall.args,
            });
          }
        }
      }

      ctx.recordLlmCall({
        model: modelId,
        input: contentsToStr(request),
        output: responseToStr(response),
        duration_ms,
        prompt_tokens: promptTokens,
        completion_tokens: completionTokens,
        cost_usd: estimateCost(modelId, promptTokens, completionTokens),
        metadata: {
          finish_reason: response.candidates?.[0]?.finishReason ?? '',
        },
      });
    }

    return result;
  };

  return model;
}
