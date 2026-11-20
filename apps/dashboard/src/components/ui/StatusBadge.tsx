import { cx } from '@/lib/cx';
import { humanize } from '@/lib/format';
import styles from './StatusBadge.module.css';

export type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'gold';

/** Default tone for known status identifiers used across the dashboard. */
const STATUS_TONES: Record<string, BadgeTone> = {
  // implementation status (backend contract)
  functional: 'success',
  partial: 'warning',
  interface_only: 'neutral',
  // lead category
  hot: 'danger',
  warm: 'gold',
  cold: 'info',
  // lead status
  new: 'info',
  qualifying: 'warning',
  qualified: 'success',
  nurturing: 'neutral',
  handed_off: 'gold',
  closed_lost: 'neutral',
  // activity outcome
  success: 'success',
  pending_approval: 'warning',
  failed: 'danger',
  skipped: 'neutral',
  // integrations
  mock: 'info',
  not_configured: 'neutral',
  pending_access: 'warning',
  // properties
  available: 'success',
  reserved: 'warning',
  off_plan: 'info',
  // knowledge
  fresh: 'success',
  stale: 'warning',
  public: 'success',
  internal: 'info',
  restricted: 'danger',
  // connectivity
  online: 'success',
  offline: 'danger',
  checking: 'neutral',
  live: 'success',
  demo: 'gold',
};

const CUSTOM_LABELS: Record<string, string> = {
  interface_only: 'Interface only',
  not_configured: 'Not configured',
  pending_access: 'Pending API access',
  mock: 'Mock mode',
  off_plan: 'Off-plan',
};

export function toneForStatus(status: string): BadgeTone {
  return STATUS_TONES[status] ?? 'neutral';
}

export function labelForStatus(status: string): string {
  return CUSTOM_LABELS[status] ?? humanize(status);
}

export interface StatusBadgeProps {
  /** Status identifier, e.g. "functional" or "pending_approval". */
  status: string;
  /** Override the displayed text (defaults to a humanised status). */
  label?: string;
  /** Override the colour tone (defaults to a mapping of known statuses). */
  tone?: BadgeTone;
  size?: 'sm' | 'md';
  className?: string;
}

export function StatusBadge({ status, label, tone, size = 'md', className }: StatusBadgeProps) {
  const resolvedTone = tone ?? toneForStatus(status);
  return (
    <span
      className={cx(styles.badge, styles[resolvedTone], size === 'sm' && styles.sm, className)}
      data-status={status}
      data-tone={resolvedTone}
    >
      <span className={styles.dot} aria-hidden="true" />
      {label ?? labelForStatus(status)}
    </span>
  );
}
