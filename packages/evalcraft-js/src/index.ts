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

// LLM-as-Judge scorers
export {
  assertOutputSemantic,
  assertFactualConsistency,
  assertTone,
  assertCustomCriteria,
} from './eval/llm-judge.js';
export type { JudgeOptions } from './eval/llm-judge.js';

// RAG scorers
export {
  assertFaithfulness,
  assertContextRelevance,
  assertAnswerRelevance,
  assertContextRecall,
} from './eval/rag-scorers.js';
export type { RagJudgeOptions } from './eval/rag-scorers.js';

// Adapters
export { wrapOpenAI } from './adapters/openai.js';
