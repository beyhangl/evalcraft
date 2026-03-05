// Mock data for Evalcraft Dashboard

export const mockUser = {
  name: 'Alex Rivera',
  email: 'alex@acme.ai',
  avatar: 'AR',
  plan: 'Pro',
  apiKey: 'ec_live_sk_1a2b3c4d5e6f7g8h9i0j',
};

export const mockRuns = [
  { id: 'r1', cassette: 'checkout-flow-v2', status: 'pass', duration: '1.2s', tokens: 3842, cost: 0.058, ts: '2 min ago', model: 'claude-sonnet-4-6' },
  { id: 'r2', cassette: 'support-agent-triage', status: 'fail', duration: '2.7s', tokens: 6210, cost: 0.094, ts: '8 min ago', model: 'claude-sonnet-4-6' },
  { id: 'r3', cassette: 'rag-pipeline-prod', status: 'pass', duration: '0.9s', tokens: 2100, cost: 0.031, ts: '15 min ago', model: 'claude-haiku-4-5' },
  { id: 'r4', cassette: 'email-responder', status: 'running', duration: '—', tokens: 1422, cost: 0.021, ts: 'just now', model: 'claude-opus-4-6' },
  { id: 'r5', cassette: 'data-extractor-v3', status: 'pass', duration: '1.8s', tokens: 4510, cost: 0.068, ts: '22 min ago', model: 'claude-sonnet-4-6' },
  { id: 'r6', cassette: 'onboarding-agent', status: 'fail', duration: '3.1s', tokens: 7800, cost: 0.117, ts: '1 hr ago', model: 'claude-sonnet-4-6' },
  { id: 'r7', cassette: 'code-review-bot', status: 'pass', duration: '2.2s', tokens: 5120, cost: 0.077, ts: '1 hr ago', model: 'claude-opus-4-6' },
  { id: 'r8', cassette: 'lead-qualifier', status: 'pending', duration: '—', tokens: 0, cost: 0, ts: '2 hr ago', model: 'claude-haiku-4-5' },
];

export const mockPassRateSeries = Array.from({ length: 30 }, (_, i) => ({
  day: `${i + 1}`,
  rate: Math.round(72 + Math.random() * 22 + Math.sin(i / 3) * 6),
  runs: Math.round(18 + Math.random() * 30),
}));

export const mockCassettes = [
  { id: 'c1', name: 'checkout-flow-v2', status: 'pass', date: '2026-03-04', tokens: 3842, cost: 0.058, runs: 47, model: 'claude-sonnet-4-6' },
  { id: 'c2', name: 'support-agent-triage', status: 'fail', date: '2026-03-04', tokens: 6210, cost: 0.094, runs: 23, model: 'claude-sonnet-4-6' },
  { id: 'c3', name: 'rag-pipeline-prod', status: 'pass', date: '2026-03-03', tokens: 2100, cost: 0.031, runs: 89, model: 'claude-haiku-4-5' },
  { id: 'c4', name: 'email-responder', status: 'running', date: '2026-03-03', tokens: 1422, cost: 0.021, runs: 12, model: 'claude-opus-4-6' },
  { id: 'c5', name: 'data-extractor-v3', status: 'pass', date: '2026-03-02', tokens: 4510, cost: 0.068, runs: 61, model: 'claude-sonnet-4-6' },
  { id: 'c6', name: 'onboarding-agent', status: 'fail', date: '2026-03-02', tokens: 7800, cost: 0.117, runs: 18, model: 'claude-sonnet-4-6' },
  { id: 'c7', name: 'code-review-bot', status: 'pass', date: '2026-03-01', tokens: 5120, cost: 0.077, runs: 34, model: 'claude-opus-4-6' },
  { id: 'c8', name: 'lead-qualifier', status: 'pending', date: '2026-03-01', tokens: 0, cost: 0, runs: 0, model: 'claude-haiku-4-5' },
  { id: 'c9', name: 'inventory-monitor', status: 'pass', date: '2026-02-28', tokens: 2890, cost: 0.043, runs: 55, model: 'claude-sonnet-4-6' },
  { id: 'c10', name: 'sentiment-analyzer', status: 'pass', date: '2026-02-27', tokens: 1760, cost: 0.026, runs: 72, model: 'claude-haiku-4-5' },
];

export const mockCassetteDetail = {
  id: 'c2',
  name: 'support-agent-triage',
  status: 'fail',
  date: '2026-03-04',
  totalSpans: 12,
  duration: '2.71s',
  tokens: 6210,
  cost: 0.094,
  model: 'claude-sonnet-4-6',
  spans: [
    { id: 's1', name: 'agent.run', start: 0, end: 2710, depth: 0, type: 'agent' },
    { id: 's2', name: 'llm.invoke', start: 10, end: 890, depth: 1, type: 'llm' },
    { id: 's3', name: 'tool.search_kb', start: 920, end: 1340, depth: 1, type: 'tool' },
    { id: 's4', name: 'llm.invoke', start: 1360, end: 2100, depth: 1, type: 'llm' },
    { id: 's5', name: 'tool.create_ticket', start: 2120, end: 2500, depth: 1, type: 'tool' },
    { id: 's6', name: 'llm.invoke', start: 2520, end: 2700, depth: 1, type: 'llm' },
    { id: 's7', name: 'embed.query', start: 930, end: 1010, depth: 2, type: 'embed' },
    { id: 's8', name: 'db.vector_search', start: 1020, end: 1330, depth: 2, type: 'db' },
  ],
  toolCalls: [
    { id: 't1', name: 'search_kb', input: '{"query": "password reset flow", "limit": 5}', output: '[{"id": "kb-123", "title": "Password Reset Guide"...}]', latency: '420ms', status: 'ok' },
    { id: 't2', name: 'create_ticket', input: '{"priority": "high", "category": "auth", "summary": "User locked out"}', output: '{"ticket_id": "SUP-4821", "status": "open"}', latency: '380ms', status: 'ok' },
  ],
  expectedOutput: `{
  "action": "escalate",
  "ticket_id": "SUP-4821",
  "priority": "high",
  "assigned_to": "tier2_support",
  "message": "Your issue has been escalated to our Tier 2 team. Ticket #SUP-4821 created."
}`,
  actualOutput: `{
  "action": "resolve",
  "ticket_id": "SUP-4821",
  "priority": "medium",
  "assigned_to": "tier1_support",
  "message": "Your issue has been logged. Ticket #SUP-4821 created."
}`,
};

export const mockGoldenSets = [
  { id: 'gs1', name: 'checkout-flow-golden', cassettes: 8, updated: '2026-03-03', passRate: 96, version: 'v4', description: 'End-to-end checkout flow with payment edge cases' },
  { id: 'gs2', name: 'support-triage-golden', cassettes: 15, updated: '2026-03-02', passRate: 81, version: 'v2', description: 'Customer support escalation and categorization flows' },
  { id: 'gs3', name: 'rag-retrieval-golden', cassettes: 22, updated: '2026-03-01', passRate: 94, version: 'v6', description: 'RAG pipeline accuracy across diverse query types' },
  { id: 'gs4', name: 'email-composer-golden', cassettes: 6, updated: '2026-02-28', passRate: 100, version: 'v1', description: 'Email drafting quality and tone consistency' },
  { id: 'gs5', name: 'data-extraction-golden', cassettes: 18, updated: '2026-02-26', passRate: 89, version: 'v3', description: 'Structured data extraction from unstructured text' },
  { id: 'gs6', name: 'code-review-golden', cassettes: 11, updated: '2026-02-24', passRate: 91, version: 'v2', description: 'Code review feedback quality and accuracy checks' },
];

export const mockRegressions = [
  { id: 'reg1', severity: 'critical', cassette: 'support-agent-triage', change: 'action changed from "escalate" to "resolve"', ts: '8 min ago', model: 'claude-sonnet-4-6', passRate: 62 },
  { id: 'reg2', severity: 'high', cassette: 'onboarding-agent', change: 'missing required field "user_id" in tool call', ts: '1 hr ago', model: 'claude-sonnet-4-6', passRate: 71 },
  { id: 'reg3', severity: 'medium', cassette: 'rag-pipeline-prod', change: 'latency increased 340ms above baseline', ts: '3 hr ago', model: 'claude-haiku-4-5', passRate: 88 },
  { id: 'reg4', severity: 'low', cassette: 'email-responder', change: 'tone score dropped from 0.92 to 0.87', ts: '5 hr ago', model: 'claude-opus-4-6', passRate: 91 },
  { id: 'reg5', severity: 'high', cassette: 'data-extractor-v3', change: 'extraction accuracy dropped 8.4% on table data', ts: '1 day ago', model: 'claude-sonnet-4-6', passRate: 76 },
  { id: 'reg6', severity: 'critical', cassette: 'checkout-flow-v2', change: 'payment intent not created in 3/10 test cases', ts: '2 days ago', model: 'claude-sonnet-4-6', passRate: 69 },
  { id: 'reg7', severity: 'medium', cassette: 'code-review-bot', change: 'false positive rate increased by 12%', ts: '3 days ago', model: 'claude-opus-4-6', passRate: 84 },
];

export const mockRegressionTrend = Array.from({ length: 14 }, (_, i) => ({
  day: `Mar ${i + 1}`,
  critical: Math.round(Math.random() * 3),
  high: Math.round(Math.random() * 5 + 1),
  medium: Math.round(Math.random() * 7 + 2),
  low: Math.round(Math.random() * 10 + 3),
}));

const tools = ['search_kb', 'create_ticket', 'send_email', 'vector_search', 'db_query', 'api_call', 'file_read', 'web_fetch'];
const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const mockHeatmap = tools.map(tool => ({
  tool,
  values: days.map(day => ({ day, count: Math.round(Math.random() * 60) })),
}));

export const mockAnalytics = {
  range: '30d',
  tokens: Array.from({ length: 30 }, (_, i) => ({
    day: `${i + 1}`,
    value: Math.round(15000 + Math.random() * 30000 + Math.sin(i / 4) * 8000),
  })),
  cost: Array.from({ length: 30 }, (_, i) => ({
    day: `${i + 1}`,
    value: parseFloat((0.22 + Math.random() * 0.45 + Math.sin(i / 4) * 0.12).toFixed(3)),
  })),
  latency: Array.from({ length: 30 }, (_, i) => ({
    day: `${i + 1}`,
    value: Math.round(800 + Math.random() * 1200 + Math.cos(i / 5) * 300),
  })),
};

export const mockApiKeys = [
  { id: 'k1', name: 'Production CI', key: 'ec_live_sk_1a2b...9i0j', created: '2026-01-15', lastUsed: '2 min ago', scopes: ['runs:write', 'cassettes:read'] },
  { id: 'k2', name: 'Dev Laptop', key: 'ec_live_sk_3c4d...7k2l', created: '2026-02-01', lastUsed: '1 day ago', scopes: ['runs:write', 'cassettes:write', 'golden-sets:read'] },
  { id: 'k3', name: 'Staging Deploy', key: 'ec_live_sk_5e6f...8m3n', created: '2026-02-20', lastUsed: '3 hr ago', scopes: ['runs:read'] },
];

export const mockTeam = [
  { id: 'u1', name: 'Alex Rivera', email: 'alex@acme.ai', role: 'owner', avatar: 'AR', joined: '2025-12-01' },
  { id: 'u2', name: 'Sam Chen', email: 'sam@acme.ai', role: 'admin', avatar: 'SC', joined: '2026-01-08' },
  { id: 'u3', name: 'Jordan Kim', email: 'jordan@acme.ai', role: 'member', avatar: 'JK', joined: '2026-02-14' },
  { id: 'u4', name: 'Taylor Moss', email: 'taylor@acme.ai', role: 'member', avatar: 'TM', joined: '2026-02-22' },
];
