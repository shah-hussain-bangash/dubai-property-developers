import { cx } from '@/lib/cx';
import styles from './States.module.css';

export interface ErrorStateProps {
  title?: string;
  message: string;
  /** When provided, a retry button is rendered. Only pass from client components. */
  onRetry?: () => void;
  retryLabel?: string;
  compact?: boolean;
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  retryLabel = 'Retry',
  compact = false,
}: ErrorStateProps) {
  return (
    <div className={cx(styles.state, styles.error, compact && styles.compact)} role="alert">
      <div className={styles.errorRow}>
        <div>
          <p className={styles.title}>{title}</p>
          <p className={styles.description}>{message}</p>
        </div>
        {onRetry ? (
          <button type="button" className="btn" onClick={onRetry}>
            {retryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
