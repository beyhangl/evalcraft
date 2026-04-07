/**
 * LLM-as-Judge scorers — semantic evaluation of agent outputs using an LLM.
 *
 * Usage:
 *   import { assertOutputSemantic, assertFactualConsistency, assertTone } from 'evalcraft';
 *
 *   const run = replay('tests/cassettes/weather.json');
 *   const result = await assertOutputSemantic(run, 'Mentions temperature and city');
 *   assert(result.passed);
 *
 * By default uses `gpt-4o-mini` via the OpenAI SDK. Pass `provider: 'anthropic'`
 * to use Claude instead.
 */

import { Cassette, AgentRun, AssertionResult } from '../core/models.js';

function getCassette(obj: Cassette | AgentRun): Cassette {
  if (obj instanceof AgentRun) return obj.cassette;
  return obj;
}

export interface JudgeOptions {
  provider?: 'openai' | 'anthropic';
  model?: string;
  apiKey?: string;
}

interface JudgeResult {
  pass: boolean;
  reason: string;
  score: number;
}

async function callJudge(
  prompt: string,
  options: JudgeOptions = {},
): Promise<JudgeResult> {
  const provider = options.provider ?? 'openai';
  const temperature = 0;

  let raw: string;

  if (provider === 'openai') {
    // Dynamic import to avoid hard dependency
    const { default: OpenAI } = await import('openai');
    const model = options.model ?? 'gpt-5.4-nano';
    const clientOpts: Record<string, unknown> = {};
    if (options.apiKey) clientOpts['apiKey'] = options.apiKey;
    const client = new OpenAI(clientOpts);

    const response = await client.chat.completions.create({
      model,
      temperature,
      messages: [
        {
          role: 'system',
          content:
            'You are an evaluation judge. You receive an agent output and ' +
            'a set of criteria. Respond ONLY with a JSON object: ' +
            '{"pass": true/false, "reason": "brief explanation", "score": 0.0-1.0}',
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
      max_tokens: 512,
      temperature,
      system:
        'You are an evaluation judge. You receive an agent output and ' +
        'a set of criteria. Respond ONLY with a JSON object: ' +
        '{"pass": true/false, "reason": "brief explanation", "score": 0.0-1.0}',
      messages: [{ role: 'user', content: prompt }],
    });
    const block = response.content?.[0];
    raw = block && 'text' in block ? block.text : '{}';
  } else {
    throw new Error(`Unsupported judge provider: '${provider}' (use 'openai' or 'anthropic')`);
  }

  let result: Record<string, unknown>;
  try {
    result = JSON.parse(raw);
  } catch {
    return { pass: false, reason: `Judge returned invalid JSON: ${raw.slice(0, 200)}`, score: 0 };
  }

  // Normalise alternate keys
  let pass = result['pass'] as boolean | undefined;
  if (pass == null) {
    for (const alt of ['passed', 'result', 'verdict']) {
      if (alt in result) {
        pass = Boolean(result[alt]);
        break;
      }
    }
    if (pass == null) pass = false;
  }

  return {
    pass: Boolean(pass),
    reason: (result['reason'] as string) ?? '',
    score: (result['score'] as number) ?? (pass ? 1.0 : 0.0),
  };
}

// ── Public scorers ───────────────────────────────────────────────────────────

/**
 * Assert that the agent output satisfies semantic criteria judged by an LLM.
 */
export async function assertOutputSemantic(
  cassette: Cassette | AgentRun,
  criteria: string,
  options: JudgeOptions = {},
): Promise<AssertionResult> {
  const c = getCassette(cassette);
  const output = c.output_text;

  if (!output) {
    return new AssertionResult({
      name: `assertOutputSemantic(${JSON.stringify(criteria)})`,
      passed: false,
      expected: criteria,
      actual: '<empty output>',
      message: 'Agent produced no output to evaluate.',
    });
  }

  const prompt =
    `## Agent output\n${output}\n\n` +
    `## Criteria\n${criteria}\n\n` +
    'Does the agent output satisfy ALL of the above criteria?';

  const result = await callJudge(prompt, options);

  return new AssertionResult({
    name: `assertOutputSemantic(${JSON.stringify(criteria)})`,
    passed: result.pass,
    expected: criteria,
    actual: output.slice(0, 200),
    message: result.pass ? '' : result.reason,
  });
}

/**
 * Assert that the agent output is factually consistent with ground truth.
 */
export async function assertFactualConsistency(
  cassette: Cassette | AgentRun,
  groundTruth: string,
  options: JudgeOptions = {},
): Promise<AssertionResult> {
  const c = getCassette(cassette);
  const output = c.output_text;

  if (!output) {
    return new AssertionResult({
      name: 'assertFactualConsistency',
      passed: false,
      expected: groundTruth.slice(0, 100),
      actual: '<empty output>',
      message: 'Agent produced no output to evaluate.',
    });
  }

  const prompt =
    `## Agent output\n${output}\n\n` +
    `## Ground truth\n${groundTruth}\n\n` +
    'Is the agent output factually consistent with the ground truth? ' +
    'Minor rephrasings are acceptable. Contradictions, fabricated details, ' +
    'or missing critical facts should cause a failure.';

  const result = await callJudge(prompt, options);

  return new AssertionResult({
    name: 'assertFactualConsistency',
    passed: result.pass,
    expected: groundTruth.slice(0, 200),
    actual: output.slice(0, 200),
    message: result.pass ? '' : result.reason,
  });
}

/**
 * Assert that the agent output has the expected tone.
 */
export async function assertTone(
  cassette: Cassette | AgentRun,
  expected: string,
  options: JudgeOptions = {},
): Promise<AssertionResult> {
  const c = getCassette(cassette);
  const output = c.output_text;

  if (!output) {
    return new AssertionResult({
      name: `assertTone(${JSON.stringify(expected)})`,
      passed: false,
      expected,
      actual: '<empty output>',
      message: 'Agent produced no output to evaluate.',
    });
  }

  const prompt =
    `## Agent output\n${output}\n\n` +
    `## Expected tone\n${expected}\n\n` +
    'Does the agent output match the expected tone?';

  const result = await callJudge(prompt, options);

  return new AssertionResult({
    name: `assertTone(${JSON.stringify(expected)})`,
    passed: result.pass,
    expected,
    actual: output.slice(0, 200),
    message: result.pass ? '' : result.reason,
  });
}

/**
 * Assert that the agent output meets a list of custom evaluation criteria.
 */
export async function assertCustomCriteria(
  cassette: Cassette | AgentRun,
  criteria: string[],
  options: JudgeOptions & { requireAll?: boolean } = {},
): Promise<AssertionResult> {
  const c = getCassette(cassette);
  const output = c.output_text;
  const requireAll = options.requireAll ?? true;

  if (!output) {
    return new AssertionResult({
      name: 'assertCustomCriteria',
      passed: false,
      expected: criteria,
      actual: '<empty output>',
      message: 'Agent produced no output to evaluate.',
    });
  }

  const criteriaBlock = criteria.map((crit, i) => `  ${i + 1}. ${crit}`).join('\n');
  const modeInstruction = requireAll
    ? 'ALL criteria must be satisfied for a pass.'
    : 'At least ONE criterion must be satisfied for a pass.';

  const prompt =
    `## Agent output\n${output}\n\n` +
    `## Criteria\n${criteriaBlock}\n\n` +
    `${modeInstruction}\n\n` +
    'Evaluate each criterion and determine an overall pass/fail.';

  const result = await callJudge(prompt, options);

  return new AssertionResult({
    name: 'assertCustomCriteria',
    passed: result.pass,
    expected: criteria,
    actual: output.slice(0, 200),
    message: result.pass ? '' : result.reason,
  });
}
