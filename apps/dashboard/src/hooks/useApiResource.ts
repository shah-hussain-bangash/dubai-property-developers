'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { describeError } from '@/services/api';

/**
 * - `loading`: request in flight, no data yet
 * - `live`: data came from the backend
 * - `demo`: backend failed; `data` is the demo fallback and `error` explains why
 */
export type ResourceSource = 'loading' | 'live' | 'demo';

export interface ApiResourceState<T> {
  data: T | null;
  source: ResourceSource;
  error: string | null;
  reload: () => void;
}

interface InternalState<T> {
  data: T | null;
  source: ResourceSource;
  error: string | null;
}

/**
 * Fetches a resource from the live backend first and falls back to demo data
 * when the request fails (network error, timeout, non-2xx, bad shape).
 */
export function useApiResource<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  fallback: T,
): ApiResourceState<T> {
  const fetcherRef = useRef(fetcher);
  const fallbackRef = useRef(fallback);
  fetcherRef.current = fetcher;
  fallbackRef.current = fallback;

  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<InternalState<T>>({
    data: null,
    source: 'loading',
    error: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    setState({ data: null, source: 'loading', error: null });

    fetcherRef.current(controller.signal).then(
      (data) => {
        if (controller.signal.aborted) return;
        setState({ data, source: 'live', error: null });
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ data: fallbackRef.current, source: 'demo', error: describeError(error) });
      },
    );

    return () => controller.abort();
  }, [attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  return { data: state.data, source: state.source, error: state.error, reload };
}
