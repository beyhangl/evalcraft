/**
 * RAG evaluation scorers — specialized metrics for Retrieval-Augmented Generation.
 *
 * Evaluates:
 *  - Faithfulness: Does the output contradict or fabricate beyond retrieved context?
 *  - Context Relevance: Are the retrieved chunks relevant to the query?
 *  - Answer Relevance: Does the answer address the original question?
 *  - Context Recall: Do the contexts contain the info needed for a correct answer?
 *
 * Usage:
 *   import { assertFaithfulness, assertContextRelevance, assertAnswerRelevance } from 'evalcraft';
 *
 *   const run = replay('tests/cassettes/rag.json');
 *   const contexts = ['Paris has 2.1 million people...', 'The Eiffel Tower...'];
 *   const result = await assertFaithfulness(run, contexts);
 *   assert(result.passed);
 */

import { Cassette, AgentRun, AssertionResult } from '../core/models.js';

function getCassette(obj: Cassette | AgentRun): Cassette {
  if (obj instanceof AgentRun) return obj.cassette;
  return obj;
}

export interface RagJudgeOptions {
  provider?: 'openai' | 'anthropic';
  model?: string;
  apiKey?: string;
}

interface RagJudgeResult {
  pass: boolean;
  score: number;
  reason: string;
  claims: Array<{ claim: string; supported: boolean }>;
}

async function callRagJudge(
  prompt: string,
  options: RagJudgeOptions = {},
): Promise<RagJudgeResult> {
  const provider = options.provider ?? 'openai';

  let raw: string;

  if (provider === 'openai') {
    const { default: OpenAI } = await import('openai');
    const model = options.model ?? 'gpt-4.1-nano';
    const clientOpts: Record<string, unknown> = {};
    if (options.apiKey) clientOpts['apiKey'] = options.apiKey;
    const client = new OpenAI(clientOpts);

    const response = await client.chat.completions.create({
      model,
      temperature: 0,
      messages: [
        {
          role: 'system',
          content:
            'You are a RAG evaluation judge. You evaluate retrieval-augmented ' +
            'generation quality. Respond ONLY with a JSON object: ' +
            '{"pass": true/false, "score": 0.0-1.0, "reason": "brief explanation", ' +
            '"claims": [{"claim": "...", "supported": true/false}]}',
        },
        { role: 'user', content: prompt },
      ],
      response_format: { type: 'json_object' },
    });
    raw = response.choices?.[0]?.message?.content ?? '{}';
  } else if (provider === 'anthropic') {
    const Anthropic = (await import('@anthropic-ai/sdk')).default;
    const model = options.model ?? 'claude-haiku-4-5-20251001';
    const clientOpts: Record<string, unknown> = {};
    if (options.apiKey) clientOpts['apiKey'] = options.apiKey;
    const client = new Anthropic(clientOpts);

    const response = await client.messages.create({
      model,
      max_tokens: 1024,
      temperature: 0,
      system:
        'You are a RAG evaluation judge. You evaluate retrieval-augmented ' +
        'generation quality. Respond ONLY with a JSON object: ' +
        '{"pass": true/false, "score": 0.0-1.0, "reason": "brief explanation", ' +
        '"claims": [{"claim": "...", "supported": true/false}]}',
      messages: [{ role: 'user', content: prompt }],
    });
    const block = response.content?.[0];
    raw = block && 'text' in block ? block.text : '{}';
  } else {
    throw new Error(`Unsupported provider: '${provider}'`);
  }

  let result: Record<string, unknown>;
  try {
    result = JSON.parse(raw);
  } catch {
    return { pass: false, score: 0, reason: `Judge returned invalid JSON: ${raw.slice(0, 200)}`, claims: [] };
  }

  let pass = result['pass'] as boolean | undefined;
  if (pass == null) {
    for (const alt of ['passed', 'result', 'verdict']) {
      if (alt in result) { pass = Boolean(result[alt]); break; }
    }
    if (pass == null) pass = false;
  }

  return {
    pass: Boolean(pass),
    score: (result['score'] as number) ?? (pass ? 1.0 : 0.0),
    reason: (result['reason'] as string) ?? '',
    claims: (result['claims'] as Array<{ claim: string; supported: boolean }>) ?? [],
  };
}

// ── Public scorers ───────────────────────────────────────────────────────────

/**
 * Assert that the agent output is faithful to the retrieved contexts.
 */
export async function assertFaithfulness(
  cassette: Cassette | AgentRun,
  contexts: string[],
  options: RagJudgeOptions & { threshold?: number } = {},
): Promise<AssertionResult> {
  const c = getCassette(cassette);
  const output = c.output_text;
  const threshold = options.threshold ?? 0.8;

  if (!output) {
    return new AssertionResult({
      name: 'assertFaithfulness',
      passed: false,
      expected: `faithfulness >= ${threshold}`,
      actual: '<empty output>',
      message: 'Agent produced no output to evaluate.',
    });
  }

  if (!contexts.length) {
    return new AssertionResult({
      name: 'assertFaithfulness',
      passed: false,
      expected: 'contexts provided',
      actual: '<no contexts>',
      message: 'No contexts provided for faithfulness evaluation.',
    });
  }

  const contextBlock = contexts.map((ctx, i) => `Context ${i + 1}:\n${ctx}`).join('\n\n---\n\n');

  const prompt =
    `## Retrieved Contexts\n${contextBlock}\n\n` +
    `## Agent Output\n${output}\n\n` +
    '## Task\n' +
    '1. Extract all factual claims from the agent output.\n' +
    '2. For each claim, determine if it is supported by the retrieved contexts.\n' +
    '3. Calculate the faithfulness score as: (supported claims) / (total claims).\n' +
    `4. Pass if the score is >= ${threshold}.`;

  const result = await callRagJudge(prompt, options);
  const score = result.score;
  const passed = score >= threshold;

  const supported = result.claims.filter((cl) => cl.supported).length;
  const total = result.claims.length;
  const detail = total > 0 ? ` (${supported}/${total} claims supported)` : '';

  return new AssertionResult({
    name: 'assertFaithfulness',
    passed,
    expected: `faithfulness >= ${threshold}`,
    actual: `${score.toFixed(2)}${detail}`,
    message: passed ? '' : result.reason,
  });
}

/**
 * Assert that the retrieved contexts are relevant to the query.
 */
export async function assertContextRelevance(
  cassette: Cassette | AgentRun,
  query: string,
  contexts: string[],
  options: RagJudgeOptions & { threshold?: number } = {},
): Promise<AssertionResult> {
  getCassette(cassette); // validate type
  const threshold = options.threshold ?? 0.7;

  if (!contexts.length) {
    return new AssertionResult({
      name: 'assertContextRelevance',
      passed: false,
      expected: 'contexts provided',
      actual: '<no contexts>',
      message: 'No contexts provided for relevance evaluation.',
    });
  }

  const contextBlock = contexts.map((ctx, i) => `Context ${i + 1}:\n${ctx}`).join('\n\n---\n\n');

  const prompt =
    `## User Query\n${query}\n\n` +
    `## Retrieved Contexts\n${contextBlock}\n\n` +
    '## Task\n' +
    '1. For each context, determine if it is relevant to answering the user query.\n' +
    '2. Calculate the score as: (relevant contexts) / (total contexts).\n' +
    `3. Pass if the score is >= ${threshold}.\n` +
    '4. In the "claims" array, list each context with "supported" as whether it is relevant.';

  const result = await callRagJudge(prompt, options);
  const score = result.score;
  const passed = score >= threshold;

  const relevant = result.claims.filter((cl) => cl.supported).length;
  const total = result.claims.length || contexts.length;

  return new AssertionResult({
    name: 'assertContextRelevance',
    passed,
    expected: `context_relevance >= ${threshold}`,
    actual: `${score.toFixed(2)} (${relevant}/${total} contexts relevant)`,
    message: passed ? '' : result.reason,
  });
}

/**
 * Assert that the agent output is relevant to the original query.
 */
export async function assertAnswerRelevance(
  cassette: Cassette | AgentRun,
  query: string,
  options: RagJudgeOptions & { threshold?: number } = {},
): Promise<AssertionResult> {
  const c = getCassette(cassette);
  const output = c.output_text;
  const threshold = options.threshold ?? 0.7;

  if (!output) {
    return new AssertionResult({
      name: 'assertAnswerRelevance',
      passed: false,
      expected: `answer_relevance >= ${threshold}`,
      actual: '<empty output>',
      message: 'Agent produced no output to evaluate.',
    });
  }

  const prompt =
    `## User Query\n${query}\n\n` +
    `## Agent Output\n${output}\n\n` +
    '## Task\n' +
    '1. Determine how well the agent output answers the user query.\n' +
    '2. Score from 0.0 (completely irrelevant) to 1.0 (perfectly relevant).\n' +
    `3. Pass if the score is >= ${threshold}.`;

  const result = await callRagJudge(prompt, options);
  const score = result.score;
  const passed = score >= threshold;

  return new AssertionResult({
    name: 'assertAnswerRelevance',
    passed,
    expected: `answer_relevance >= ${threshold}`,
    actual: score.toFixed(2),
    message: passed ? '' : result.reason,
  });
}

/**
 * Assert that the retrieved contexts contain the information needed to answer correctly.
 */
export async function assertContextRecall(
  cassette: Cassette | AgentRun,
  query: string,
  contexts: string[],
  groundTruth: string,
  options: RagJudgeOptions & { threshold?: number } = {},
): Promise<AssertionResult> {
  getCassette(cassette); // validate type
  const threshold = options.threshold ?? 0.7;

  if (!contexts.length) {
    return new AssertionResult({
      name: 'assertContextRecall',
      passed: false,
      expected: 'contexts provided',
      actual: '<no contexts>',
      message: 'No contexts provided for recall evaluation.',
    });
  }

  const contextBlock = contexts.map((ctx, i) => `Context ${i + 1}:\n${ctx}`).join('\n\n---\n\n');

  const prompt =
    `## User Query\n${query}\n\n` +
    `## Ground Truth Answer\n${groundTruth}\n\n` +
    `## Retrieved Contexts\n${contextBlock}\n\n` +
    '## Task\n' +
    '1. Extract the key facts from the ground truth answer.\n' +
    '2. For each fact, check if it can be found in the retrieved contexts.\n' +
    '3. Calculate the recall score as: (facts found) / (total facts).\n' +
    `4. Pass if the score is >= ${threshold}.`;

  const result = await callRagJudge(prompt, options);
  const score = result.score;
  const passed = score >= threshold;

  const found = result.claims.filter((cl) => cl.supported).length;
  const total = result.claims.length;
  const detail = total > 0 ? ` (${found}/${total} facts recalled)` : '';

  return new AssertionResult({
    name: 'assertContextRecall',
    passed,
    expected: `context_recall >= ${threshold}`,
    actual: `${score.toFixed(2)}${detail}`,
    message: passed ? '' : result.reason,
  });
}
