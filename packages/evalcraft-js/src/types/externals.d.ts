// Type declarations for optional peer dependencies.
// These modules are dynamically imported at runtime — they are NOT required
// at install time. The declarations here suppress TS2307 during type-checking.

declare module 'openai' {
  interface ChatCompletionMessage {
    content?: string | null;
    role?: string;
  }
  interface Choice {
    message?: ChatCompletionMessage;
    finish_reason?: string;
  }
  interface CompletionResponse {
    choices?: Choice[];
    usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
    model?: string;
  }
  interface ChatCompletions {
    create(params: Record<string, unknown>): Promise<CompletionResponse>;
  }
  interface Chat {
    completions: ChatCompletions;
  }
  class OpenAI {
    constructor(opts?: Record<string, unknown>);
    chat: Chat;
  }
  export default OpenAI;
}

declare module '@anthropic-ai/sdk' {
  interface TextBlock {
    type: 'text';
    text: string;
  }
  interface MessageResponse {
    content: TextBlock[];
  }
  interface Messages {
    create(params: Record<string, unknown>): Promise<MessageResponse>;
  }
  class Anthropic {
    constructor(opts?: Record<string, unknown>);
    messages: Messages;
  }
  export default Anthropic;
}

declare module '@google/generative-ai' {
  export class GoogleGenerativeAI {
    constructor(apiKey: string);
    getGenerativeModel(params: { model: string }): GenerativeModel;
  }
  export class GenerativeModel {
    model?: string;
    generateContent(request: unknown): Promise<GenerateContentResult>;
    generateContentStream?(request: unknown): Promise<unknown>;
  }
  export interface GenerateContentResult {
    response: GenerateContentResponse;
  }
  export interface GenerateContentResponse {
    text(): string;
    candidates?: Array<{
      content?: { parts?: Array<{ text?: string; functionCall?: { name: string; args: Record<string, unknown> } }> };
      finishReason?: string;
    }>;
    usageMetadata?: {
      promptTokenCount?: number;
      candidatesTokenCount?: number;
      totalTokenCount?: number;
    };
  }
}
