import { APP_NAME, APP_TAGLINE } from '@/lib/config';
import styles from './BrandMark.module.css';

export function BrandMark() {
  return (
    <span className={styles.brand}>
      <span className={styles.logo} aria-hidden="true">
        <svg viewBox="0 0 32 32" width="32" height="32">
          <rect width="32" height="32" rx="8" fill="#0e1f36" stroke="#d4af5a" strokeOpacity="0.6" />
          <path d="M16 5 L18 12 L18 26 L14 26 L14 12 Z" fill="#d4af5a" />
          <path d="M9 26 V16 L12 14 V26 Z M20 26 V14 L23 16 V26 Z" fill="#3d7bff" />
        </svg>
      </span>
      <span className={styles.text}>
        <span className={styles.name}>{APP_NAME}</span>
        <span className={styles.tagline}>{APP_TAGLINE}</span>
      </span>
    </span>
  );
}
