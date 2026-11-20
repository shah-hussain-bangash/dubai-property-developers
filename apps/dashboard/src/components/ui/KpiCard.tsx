import { Sparkline } from '@/components/charts/Sparkline';
import { cx } from '@/lib/cx';
import styles from './KpiCard.module.css';

export interface KpiCardProps {
  label: string;
  value: string;
  delta?: string;
  deltaTone?: 'positive' | 'negative' | 'neutral';
  hint?: string;
  trend?: number[];
}

export function KpiCard({ label, value, delta, deltaTone = 'neutral', hint, trend }: KpiCardProps) {
  return (
    <article className={cx('panel', styles.card)}>
      <h2 className={styles.label}>{label}</h2>
      <p className={styles.value}>{value}</p>
      <div className={styles.footer}>
        <div className={styles.meta}>
          {delta ? <p className={cx(styles.delta, styles[deltaTone])}>{delta}</p> : null}
          {hint ? <p className={styles.hint}>{hint}</p> : null}
        </div>
        {trend && trend.length > 1 ? (
          <Sparkline values={trend} label={`${label} trend`} className={styles.sparkline} />
        ) : null}
      </div>
    </article>
  );
}
