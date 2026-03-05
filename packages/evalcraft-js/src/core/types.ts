/** Type of recorded span. */
export enum SpanKind {
  LLM_REQUEST = 'llm_request',
  LLM_RESPONSE = 'llm_response',
  TOOL_CALL = 'tool_call',
  TOOL_RESULT = 'tool_result',
  AGENT_STEP = 'agent_step',
  USER_INPUT = 'user_input',
  AGENT_OUTPUT = 'agent_output',
}

/** Token usage for an LLM call. */
export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export function makeTokenUsage(
  prompt_tokens = 0,
  completion_tokens = 0,
): TokenUsage {
  return {
    prompt_tokens,
    completion_tokens,
    total_tokens: prompt_tokens + completion_tokens,
  };
}

export function tokenUsageFromDict(data: Record<string, unknown>): TokenUsage {
  return {
    prompt_tokens: (data['prompt_tokens'] as number) ?? 0,
    completion_tokens: (data['completion_tokens'] as number) ?? 0,
    total_tokens: (data['total_tokens'] as number) ?? 0,
  };
}
