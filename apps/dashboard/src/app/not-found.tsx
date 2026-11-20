import Link from 'next/link';
import type { Metadata } from 'next';
import styles from './status-page.module.css';

export const metadata: Metadata = {
  title: 'Page not found',
};

export default function NotFound() {
  return (
    <main className={styles.page}>
      <div className={`panel ${styles.card}`}>
        <p className={styles.code}>404</p>
        <h1 className={styles.title}>Page not found</h1>
        <p className={styles.text}>The page you requested does not exist in this dashboard.</p>
        <Link href="/" className="btn btn-primary">
          Back to overview
        </Link>
      </div>
    </main>
  );
}
