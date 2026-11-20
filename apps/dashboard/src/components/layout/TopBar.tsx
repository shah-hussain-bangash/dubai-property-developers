'use client';

import { PortalSignOut } from '@/features/auth/PortalSignOut';
import { cx } from '@/lib/cx';
import { ApiStatusIndicator } from './ApiStatusIndicator';
import { BrandMark } from './BrandMark';
import styles from './TopBar.module.css';

export interface TopBarProps {
  navId: string;
  navOpen: boolean;
  onToggleNav: () => void;
}

export function TopBar({ navId, navOpen, onToggleNav }: TopBarProps) {
  return (
    <header className={styles.topbar}>
      <div className={styles.left}>
        <button
          type="button"
          className={cx('btn btn-ghost', styles.menuButton)}
          aria-controls={navId}
          aria-expanded={navOpen}
          onClick={onToggleNav}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
          </svg>
          <span className="visually-hidden">{navOpen ? 'Close navigation' : 'Open navigation'}</span>
        </button>
        <span className={styles.mobileBrand}>
          <BrandMark />
        </span>
        <p className={styles.context}>
          Admin operations console <span className={styles.region}>· Dubai, UAE (GST)</span>
        </p>
      </div>
      <div className={styles.right}>
        <ApiStatusIndicator />
        <span className={styles.envBadge}>Admin</span>
        <PortalSignOut destination="/admin/login" />
      </div>
    </header>
  );
}
