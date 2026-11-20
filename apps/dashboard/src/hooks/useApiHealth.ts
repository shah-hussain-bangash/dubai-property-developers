'use client';

import { useEffect, useState } from 'react';
import { describeError, getHealth } from '@/services/api';
import type { HealthResponse } from '@/types/api';

export type HealthStatus = 'checking' | 'online' | 'offline';

export interface ApiHealthState {
  status: HealthStatus;
  health: HealthResponse | null;
  error: string | null;
}

const DEFAULT_POLL_MS = 30_000;

/** Polls GET /health. Failures are reported politely, never thrown. */
export function useApiHealth(pollIntervalMs: number = DEFAULT_POLL_MS): ApiHealthState {
  const [state, setState] = useState<ApiHealthState>({ status: 'checking', health: null, error: null });

  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;

    const check = () => {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      getHealth({ signal: current.signal, timeoutMs: 4000 }).then(
        (health) => {
          if (active && !current.signal.aborted) setState({ status: 'online', health, error: null });
        },
        (error: unknown) => {
          if (active && !current.signal.aborted) {
            setState({ status: 'offline', health: null, error: describeError(error) });
          }
        },
      );
    };

    check();
    const interval = window.setInterval(check, pollIntervalMs);

    return () => {
      active = false;
      window.clearInterval(interval);
      controller?.abort();
    };
  }, [pollIntervalMs]);

  return state;
}
