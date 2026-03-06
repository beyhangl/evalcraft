import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { setToken, api } from '../services/api';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

beforeEach(() => {
  setToken(null);
  mockFetch.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('api', () => {
  it('setToken stores token for subsequent requests', async () => {
    setToken('test-jwt-token');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: '1', email: 'a@b.com', full_name: 'Test', team_id: 't1', created_at: '' }),
    });

    await api.me();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, opts] = mockFetch.mock.calls[0];
    expect(opts.headers.Authorization).toBe('Bearer test-jwt-token');
  });

  it('login sends email and password', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: 'tok', token_type: 'bearer' }),
    });

    const res = await api.login('a@b.com', 'pass123');
    expect(res.access_token).toBe('tok');
    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toContain('/auth/login');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({ email: 'a@b.com', password: 'pass123' });
  });

  it('throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: () => Promise.resolve({ detail: 'Invalid input' }),
    });

    await expect(api.login('a@b.com', 'bad')).rejects.toThrow('Invalid input');
  });

  it('listCassettes builds correct query string', async () => {
    setToken('tok');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ items: [], total: 0, page: 1, page_size: 50 }),
    });

    await api.listCassettes('proj-1', { agent_name: 'my-agent' });
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('project_id=proj-1');
    expect(url).toContain('agent_name=my-agent');
  });

  it('returns undefined for 204 responses', async () => {
    setToken('tok');
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });

    const result = await api.revokeApiKey('key-1');
    expect(result).toBeUndefined();
  });
});
