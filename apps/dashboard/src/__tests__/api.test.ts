import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, buildApiUrl, getAgents, getHealth, getWorkflows } from '@/services/api';
import { DEMO_AGENTS_RESPONSE, DEMO_WORKFLOWS_RESPONSE } from '@/lib/demo-data';

const BASE = 'http://api.test';

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('buildApiUrl', () => {
  it('joins base and path with exactly one slash', () => {
    expect(buildApiUrl('/api/v1/agents', 'http://localhost:8000')).toBe('http://localhost:8000/api/v1/agents');
    expect(buildApiUrl('api/v1/agents', 'http://localhost:8000/')).toBe('http://localhost:8000/api/v1/agents');
    expect(buildApiUrl('/health', 'https://example.com/backend//')).toBe('https://example.com/backend/health');
  });
});

describe('api service', () => {
  it('fetches agents from /api/v1/agents', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(DEMO_AGENTS_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getAgents({ baseUrl: BASE });

    expect(result.total).toBe(13);
    expect(result.items).toHaveLength(13);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${BASE}/api/v1/agents`);
  });

  it('fetches workflows from /api/v1/workflows', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(DEMO_WORKFLOWS_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getWorkflows({ baseUrl: BASE });

    expect(result.items.map((w) => w.workflow_id)).toContain('lead_processing');
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${BASE}/api/v1/workflows`);
  });

  it('wraps network failures in an ApiError of kind "network"', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );

    await expect(getAgents({ baseUrl: BASE })).rejects.toMatchObject({ name: 'ApiError', kind: 'network' });
  });

  it('reports non-2xx responses as http errors with the status code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'boom' }, 503)));

    const error = await getHealth({ baseUrl: BASE }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe('http');
    expect((error as ApiError).status).toBe(503);
  });

  it('rejects responses with an unexpected shape', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ agents: [] })));

    await expect(getAgents({ baseUrl: BASE })).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it('times out slow requests via AbortController', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
          }),
      ),
    );

    await expect(getAgents({ baseUrl: BASE, timeoutMs: 20 })).rejects.toMatchObject({ kind: 'timeout' });
  });
});
