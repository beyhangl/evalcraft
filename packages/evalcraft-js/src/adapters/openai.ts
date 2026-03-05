/**
 * OpenAI Node SDK adapter — wraps OpenAI client calls to auto-record spans.
 *
 * Usage:
 *   import OpenAI from 'openai';
 *   import { wrapOpenAI } from 'evalcraft/adapters/openai';
 *
 *   const client = wrapOpenAI(new OpenAI());
 *   // All client.chat.completions.create calls now auto-record to active context.
 */

import { getActiveContext } from '../capture/recorder.js';

// We use a generic type so the adapter compiles without OpenAI installed.
type OpenAILike = {
  chat: {
    completions: {
      create: (params: Record<string, unknown>) => Promise<unknown>;
    };
  };
};

type CompletionResponse = {
  id?: string;
  model?: string;
  choices?: Array<{
    message?: { content?: string | null; role?: string };
    finish_reason?: string;
  }>;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
};

export function wrapOpenAI<T extends OpenAILike>(client: T): T {
  const originalCreate = client.chat.completions.create.bind(
    client.chat.completions,
  );

  client.chat.completions.create = async (
    params: Record<string, unknown>,
  ): Promise<unknown> => {
    const start = Date.now();
    const response = (await originalCreate(params)) as CompletionResponse;
    const duration_ms = Date.now() - start;

    const ctx = getActiveContext();
    if (ctx) {
      const model = (response.model as string) ?? (params['model'] as string) ?? 'unknown';
      const output =
        response.choices?.[0]?.message?.content ?? null;
      ctx.recordLlmCall({
        model,
        input: params['messages'],
        output,
        duration_ms,
        prompt_tokens: response.usage?.prompt_tokens ?? 0,
        completion_tokens: response.usage?.completion_tokens ?? 0,
      });
    }

    return response;
  };

  return client;
}
