'use client';

import { useApiHealth } from '@/hooks/useApiHealth';
import { getApiBaseUrl } from '@/lib/config';
import { StatusBadge } from '@/components/ui/StatusBadge';

/** Top-bar connectivity indicator backed by GET /health. Fails politely. */
export function ApiStatusIndicator() {
  const { status, health } = useApiHealth();
  const baseUrl = getApiBaseUrl();

  let label = 'Checking API…';
  let title = `Checking ${baseUrl}/health`;
  if (status === 'online' && health) {
    label = `API online · v${health.version}`;
    title = `${health.service} (${health.environment}) at ${baseUrl}`;
  } else if (status === 'offline') {
    label = 'API offline';
    title = `Could not reach ${baseUrl}/health — pages fall back to demo data.`;
  }

  return (
    <span role="status" aria-live="polite" title={title}>
      <StatusBadge status={status} label={label} size="sm" />
    </span>
  );
}
