import { getApiBaseUrl } from '@/lib/config';
import type {
  AgentListResponse,
  HealthResponse,
  ListResponse,
  WorkflowListResponse,
} from '@/types/api';

export const DEFAULT_TIMEOUT_MS = 5000;

export const API_PATHS = {
  health: '/health',
  agents: '/api/v1/agents',
  workflows: '/api/v1/workflows',
} as const;

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'aborted' | 'invalid_response';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly url: string;
  readonly status: number | null;

  constructor(message: string, kind: ApiErrorKind, url: string, status: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.url = url;
    this.status = status;
  }
}

export interface RequestOptions {
  /** Caller-owned signal (e.g. from a React effect cleanup). */
  signal?: AbortSignal;
  /** Request timeout in milliseconds. Defaults to DEFAULT_TIMEOUT_MS. */
  timeoutMs?: number;
  /** Override the configured base URL (mainly for tests). */
  baseUrl?: string;
}

/** Joins the base URL and path with exactly one slash between them. */
export function buildApiUrl(path: string, baseUrl: string = getApiBaseUrl()): string {
  const base = baseUrl.trim().replace(/\/+$/, '');
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

/**
 * GETs JSON with a timeout (AbortController). Every failure is normalised to
 * an ApiError so callers can render a consistent message.
 */
export async function fetchJson(path: string, options: RequestOptions = {}): Promise<unknown> {
  const url = buildApiUrl(path, options.baseUrl);
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  let timedOut = false;

  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  const externalSignal = options.signal;
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener('abort', onExternalAbort, { once: true });
    }
  }

  try {
    let response: Response;
    try {
      response = await fetch(url, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal: controller.signal,
      });
    } catch {
      if (timedOut) {
        throw new ApiError(`Request timed out after ${timeoutMs} ms`, 'timeout', url);
      }
      if (externalSignal?.aborted) {
        throw new ApiError('Request was cancelled', 'aborted', url);
      }
      throw new ApiError('Backend unreachable (network error)', 'network', url);
    }

    if (!response.ok) {
      throw new ApiError(`Backend responded with HTTP ${response.status}`, 'http', url, response.status);
    }

    try {
      return (await response.json()) as unknown;
    } catch {
      throw new ApiError('Backend returned a non-JSON response', 'invalid_response', url, response.status);
    }
  } finally {
    clearTimeout(timer);
    externalSignal?.removeEventListener('abort', onExternalAbort);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Minimal runtime guard: `{ items: [{ [idKey]: string, ... }], total: number }`. */
export function isListResponse(value: unknown, idKey: string): value is ListResponse<Record<string, unknown>> {
  if (!isRecord(value)) return false;
  const { items, total } = value;
  if (!Array.isArray(items) || typeof total !== 'number') return false;
  return items.every((item) => isRecord(item) && typeof item[idKey] === 'string');
}

export function isHealthResponse(value: unknown): value is HealthResponse {
  return isRecord(value) && value.status === 'ok' && typeof value.service === 'string';
}

export async function getAgents(options: RequestOptions = {}): Promise<AgentListResponse> {
  const body = await fetchJson(API_PATHS.agents, options);
  if (!isListResponse(body, 'agent_id')) {
    throw new ApiError('Unexpected agents response shape', 'invalid_response', buildApiUrl(API_PATHS.agents, options.baseUrl));
  }
  return body as unknown as AgentListResponse;
}

export async function getWorkflows(options: RequestOptions = {}): Promise<WorkflowListResponse> {
  const body = await fetchJson(API_PATHS.workflows, options);
  if (!isListResponse(body, 'workflow_id')) {
    throw new ApiError(
      'Unexpected workflows response shape',
      'invalid_response',
      buildApiUrl(API_PATHS.workflows, options.baseUrl),
    );
  }
  return body as unknown as WorkflowListResponse;
}

export async function getHealth(options: RequestOptions = {}): Promise<HealthResponse> {
  const body = await fetchJson(API_PATHS.health, options);
  if (!isHealthResponse(body)) {
    throw new ApiError('Unexpected health response shape', 'invalid_response', buildApiUrl(API_PATHS.health, options.baseUrl));
  }
  return body;
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Unknown error';
}
