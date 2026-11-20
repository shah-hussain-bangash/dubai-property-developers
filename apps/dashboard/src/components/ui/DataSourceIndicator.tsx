import type { ResourceSource } from '@/hooks/useApiResource';
import { StatusBadge } from './StatusBadge';

export interface DataSourceIndicatorProps {
  source: ResourceSource;
}

/** Tells the user whether the data on screen is live or a demo fallback. */
export function DataSourceIndicator({ source }: DataSourceIndicatorProps) {
  if (source === 'live') {
    return <StatusBadge status="live" label="Live from API" />;
  }
  if (source === 'demo') {
    return <StatusBadge status="demo" label="Demo fallback — backend unavailable" />;
  }
  return <StatusBadge status="checking" label="Contacting backend…" />;
}
