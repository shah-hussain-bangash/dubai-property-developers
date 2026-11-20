/** Same-origin browser transport. Creating this transport performs no requests. */
import { AccountApiError, type AccountRequest, type AccountTransport } from './accounts';

export function createBrowserAccountTransport({
  fetchImpl = globalThis.fetch,
  timeoutMs = 10000,
}: { fetchImpl?: typeof fetch; timeoutMs?: number } = {}): AccountTransport {
  if (typeof fetchImpl !== 'function' || !Number.isInteger(timeoutMs) ||
      timeoutMs < 1 || timeoutMs > 60000) {
    throw new AccountApiError('Invalid browser transport configuration.', null);
  }

  return async (path: string, request: AccountRequest) => {
    const read = path === '/api/v1/accounts/me' ||
      path === '/api/v1/accounts/approvals/pending?limit=50';
    const decision = /^\/api\/v1\/accounts\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/approval$/i.test(path);
    const logout = path === '/api/v1/auth/browser/logout';
    if ((!read && !decision && !logout) ||
        (read && (request.method !== 'GET' || request.body !== undefined)) ||
        ((decision || logout) && request.method !== 'POST') ||
        (decision && (typeof request.body?.approve !== 'boolean' ||
          Object.keys(request.body).length !== 1)) ||
        (logout && request.body !== undefined)) {
      throw new AccountApiError('Invalid browser account request.', null);
    }
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (request.signal?.aborted) controller.abort();
    request.signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(abort, timeoutMs);
    const options: RequestInit = {
      credentials: 'same-origin', mode: 'same-origin', redirect: 'error',
      cache: 'no-store', signal: controller.signal,
    };
    try {
      if (controller.signal.aborted) throw new Error('aborted');
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (request.method === 'POST') {
        const response = await fetchImpl('/api/v1/auth/browser/csrf', {
          ...options, method: 'GET', headers,
        });
        if (!response.ok) return { status: response.status, json: async () => null };
        const csrf: unknown = await response.json();
        if (!csrf || typeof csrf !== 'object' ||
            typeof (csrf as Record<string, unknown>).csrf_token !== 'string' ||
            !/^[0-9a-f]{64}$/.test((csrf as Record<string, string>).csrf_token)) {
          throw new Error('invalid csrf response');
        }
        headers['X-CSRF-Token'] = (csrf as Record<string, string>).csrf_token;
      }
      if (controller.signal.aborted) throw new Error('aborted');
      if (request.body) headers['Content-Type'] = 'application/json';
      const response = await fetchImpl(path, {
        ...options, method: request.method, headers,
        body: request.body === undefined ? undefined : JSON.stringify(request.body),
      });
      // Read successful JSON while the timeout and caller cancellation are active.
      const body: unknown = response.ok && response.status !== 204 ? await response.json() : null;
      return { status: response.status, json: async () => body };
    } catch {
      throw new AccountApiError('Unable to complete the browser account request.', null);
    } finally {
      clearTimeout(timer);
      request.signal?.removeEventListener('abort', abort);
    }
  };
}
