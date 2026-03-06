const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API = `${BASE_URL}/api/v1`;

let token: string | null = null;
let onUnauth: (() => void) | null = null;

export function setToken(t: string | null) {
  token = t;
}

export function setOnUnauth(cb: () => void) {
  onUnauth = cb;
}

async function _doFetch(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  return fetch(`${API}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res = await _doFetch(method, path, body);

  // Token refresh on 401
  if (res.status === 401 && token && path !== '/auth/refresh' && path !== '/auth/login') {
    try {
      const refreshRes = await _doFetch('POST', '/auth/refresh');
      if (refreshRes.ok) {
        const data = await refreshRes.json();
        token = data.access_token;
        localStorage.setItem('ec_token', data.access_token);
        res = await _doFetch(method, path, body);
      }
    } catch { /* fall through to logout */ }
    if (res.status === 401) {
      onUnauth?.();
      throw new Error('Unauthorized');
    }
  }

  if (res.status === 401) {
    onUnauth?.();
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

function get<T>(path: string) {
  return request<T>('GET', path);
}
function post<T>(path: string, body?: unknown) {
  return request<T>('POST', path, body);
}
function patch<T>(path: string, body?: unknown) {
  return request<T>('PATCH', path, body);
}
function del(path: string) {
  return request<void>('DELETE', path);
}

// ── Types (mirror backend schemas) ──

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  team_id: string;
  created_at: string;
}

export interface ProjectResponse {
  id: string;
  name: string;
  slug: string;
  description: string;
  team_id: string;
  created_at: string;
  updated_at: string;
}

export interface CassetteListItem {
  id: string;
  name: string;
  agent_name: string;
  framework: string;
  fingerprint: string;
  total_tokens: number;
  total_cost_usd: number;
  total_duration_ms: number;
  llm_call_count: number;
  tool_call_count: number;
  git_sha: string;
  branch: string;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface CassetteDetail extends CassetteListItem {
  input_text: string;
  output_text: string;
  raw_data: Record<string, unknown>;
  ci_run_url: string;
}

export interface GoldenSetResponse {
  id: string;
  project_id: string;
  name: string;
  description: string;
  version: number;
  thresholds: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface GoldenSetDetailResponse extends GoldenSetResponse {
  raw_data: Record<string, unknown>;
}

export interface RegressionEventResponse {
  id: string;
  project_id: string;
  cassette_id: string;
  golden_set_id: string | null;
  severity: string;
  category: string;
  message: string;
  details: Record<string, unknown>;
  resolved: boolean;
  created_at: string;
}

export interface TrendPoint {
  date: string;
  total_tokens: number;
  total_cost_usd: number;
  total_duration_ms: number;
  cassette_count: number;
}

export interface TrendsResponse {
  project_id: string;
  points: TrendPoint[];
}

export interface APIKeyResponse {
  id: string;
  key_prefix: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
}

export interface APIKeyCreatedResponse extends APIKeyResponse {
  full_key: string;
}

// ── API methods ──

export const api = {
  // Auth
  login: (email: string, password: string) =>
    post<TokenResponse>('/auth/login', { email, password }),
  signup: (email: string, password: string, full_name: string, team_name: string) =>
    post<TokenResponse>('/auth/signup', { email, password, full_name, team_name }),
  me: () => get<UserResponse>('/auth/me'),

  // Projects
  listProjects: () => get<ProjectResponse[]>('/projects'),
  createProject: (body: { name: string; description?: string }) =>
    post<ProjectResponse>('/projects', body),

  // Cassettes
  listCassettes: (projectId: string, params?: { date_from?: string; date_to?: string; agent_name?: string }) => {
    const qs = new URLSearchParams({ project_id: projectId });
    if (params?.date_from) qs.set('date_from', params.date_from);
    if (params?.date_to) qs.set('date_to', params.date_to);
    if (params?.agent_name) qs.set('agent_name', params.agent_name);
    return get<PaginatedResponse<CassetteListItem>>(`/cassettes?${qs}`);
  },
  getCassette: (id: string) => get<CassetteDetail>(`/cassettes/${id}`),
  uploadCassette: (projectId: string, data: Record<string, unknown>, meta?: { git_sha?: string; branch?: string; ci_run_url?: string }) => {
    const qs = new URLSearchParams({ project_id: projectId });
    if (meta?.git_sha) qs.set('git_sha', meta.git_sha);
    if (meta?.branch) qs.set('branch', meta.branch);
    if (meta?.ci_run_url) qs.set('ci_run_url', meta.ci_run_url);
    return post<CassetteListItem>(`/cassettes/upload?${qs}`, data);
  },

  // Golden Sets
  listGoldenSets: (projectId: string) =>
    get<PaginatedResponse<GoldenSetResponse>>(`/golden-sets?project_id=${projectId}`),
  getGoldenSet: (id: string) => get<GoldenSetDetailResponse>(`/golden-sets/${id}`),
  createGoldenSet: (projectId: string, body: { name: string; description?: string; cassette_ids?: string[]; thresholds?: Record<string, unknown> }) =>
    post<GoldenSetResponse>(`/golden-sets?project_id=${projectId}`, body),

  // Regressions
  listRegressions: (projectId: string, severity?: string) => {
    const qs = new URLSearchParams({ project_id: projectId });
    if (severity) qs.set('severity', severity);
    return get<PaginatedResponse<RegressionEventResponse>>(`/regressions?${qs}`);
  },
  resolveRegression: (id: string) =>
    patch<RegressionEventResponse>(`/regressions/${id}/resolve`),

  // Analytics
  getTrends: (projectId: string, days = 30) =>
    get<TrendsResponse>(`/analytics/trends?project_id=${projectId}&days=${days}`),

  // API Keys
  listApiKeys: () => get<APIKeyResponse[]>('/auth/api-keys'),
  createApiKey: (name: string) => post<APIKeyCreatedResponse>('/auth/api-keys', { name }),
  revokeApiKey: (id: string) => del(`/auth/api-keys/${id}`),
};
