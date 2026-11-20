import type { ReactNode } from 'react';
import styles from './DemoDataBanner.module.css';

export const DEMO_BANNER_TEXT = 'Demo data — not live records';

export interface DemoDataBannerProps {
  /** Headline; defaults to "Demo data — not live records". */
  message?: string;
  /** Optional supporting detail shown after the headline. */
  children?: ReactNode;
}

/** Visible notice that the page shows fictional demo data. */
export function DemoDataBanner({ message = DEMO_BANNER_TEXT, children }: DemoDataBannerProps) {
  return (
    <div className={styles.banner} role="note" aria-label="Demo data notice" data-testid="demo-data-banner">
      <span className={styles.icon} aria-hidden="true">
        <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="10" cy="10" r="8" />
          <path d="M10 6v5" strokeLinecap="round" />
          <circle cx="10" cy="14" r="0.6" fill="currentColor" />
        </svg>
      </span>
      <p className={styles.text}>
        <strong className={styles.title}>{message}</strong>
        {children ? <span className={styles.detail}>{children}</span> : null}
      </p>
    </div>
  );
}
