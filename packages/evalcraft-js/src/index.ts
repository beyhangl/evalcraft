// Core models and types
export {
  Span,
  Cassette,
  AgentRun,
  EvalResult,
  AssertionResult,
} from './core/models.js';
export type { SpanData, CassetteData } from './core/models.js';
export { SpanKind, makeTokenUsage } from './core/types.js';
export type { TokenUsage } from './core/types.js';

// Capture
export {
  CaptureContext,
  capture,
  getActiveContext,
  recordSpan,
  recordLlmCall,
  recordToolCall,
} from './capture/recorder.js';
export type { CaptureOptions } from './capture/recorder.js';

// Replay
export { ReplayEngine, ReplayDiff, replay } from './replay/engine.js';

// Mocks
export { MockLLM } from './mock/llm.js';
export type { MockResponse } from './mock/llm.js';
export { MockTool, ToolError } from './mock/tool.js';

// Scorers
export {
  assertToolCalled,
  assertToolOrder,
  assertNoToolCalled,
  assertOutputContains,
  assertOutputMatches,
  assertCostUnder,
  assertLatencyUnder,
  assertTokenCountUnder,
  Evaluator,
} from './eval/scorers.js';

// Adapters
export { wrapOpenAI } from './adapters/openai.js';
