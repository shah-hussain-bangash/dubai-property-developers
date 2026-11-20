'use client';

import Link from 'next/link';
import { cx } from '@/lib/cx';
import { NAV_SECTIONS, isNavItemActive } from '@/lib/navigation';
import { BrandMark } from './BrandMark';
import { NavIcon } from './NavIcon';
import styles from './Sidebar.module.css';

export interface SidebarProps {
  id: string;
  pathname: string;
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ id, pathname, open, onClose }: SidebarProps) {
  return (
    <aside id={id} className={cx(styles.sidebar, open && styles.open)} aria-label="Primary">
      <div className={styles.brandRow}>
        <Link href="/overview" className={styles.brandLink} aria-label="Dubai Real Estate AI — Overview">
          <BrandMark />
        </Link>
        <button type="button" className={cx('btn btn-ghost', styles.closeButton)} onClick={onClose} aria-label="Close navigation">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <nav className={styles.nav} aria-label="Main navigation">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title} className={styles.section}>
            <p className={styles.sectionTitle}>{section.title}</p>
            <ul className={styles.list}>
              {section.items.map((item) => {
                const active = !item.planned && isNavItemActive(item.href, pathname);
                return (
                  <li key={item.href}>
                    {item.planned ? (
                      <span className={cx(styles.link, styles.planned)} aria-disabled="true" title="Planned feature — development coming later">
                        <NavIcon name={item.icon} />
                        <span className={styles.plannedLabel}>{item.label}</span>
                        <span className={styles.plannedBadge}>Planned</span>
                      </span>
                    ) : (
                    <Link
                      href={item.href}
                      className={cx(styles.link, active && styles.active)}
                      aria-current={active ? 'page' : undefined}
                    >
                      <NavIcon name={item.icon} />
                      <span>{item.label}</span>
                    </Link>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className={styles.footer}>
        <p className={styles.footerTitle}>Admin workspace</p>
        <p className={styles.footerText}>Saved research. Human review.</p>
      </div>
    </aside>
  );
}
