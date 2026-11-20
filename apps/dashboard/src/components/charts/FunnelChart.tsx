import type { ChartDatum } from '@/types/domain';
import styles from './charts.module.css';

export interface FunnelChartProps {
  data: ChartDatum[];
  title: string;
}

/**
 * Pipeline funnel. Rendered with HTML bars (not SVG text) so stage labels stay
 * legible at every width; the list itself is the accessible representation.
 */
export function FunnelChart({ data, title }: FunnelChartProps) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <figure className={styles.figure}>
      <ol className={styles.funnel} aria-label={title}>
        {data.map((stage, i) => {
          const previous = i > 0 ? data[i - 1] : undefined;
          const conversion =
            previous && previous.value > 0 ? `${Math.round((stage.value / previous.value) * 100)}% of previous` : null;
          const widthPct = Math.max((stage.value / max) * 100, 8);
          return (
            <li key={stage.label} className={styles.funnelRow}>
              <span className={styles.funnelLabel} title={stage.label}>
                {stage.label}
              </span>
              <span className={styles.funnelTrack}>
                <span
                  className={styles.funnelBar}
                  style={{ width: `${widthPct}%`, opacity: 1 - i * 0.1 }}
                  title={conversion ? `${stage.label}: ${stage.value} (${conversion})` : `${stage.label}: ${stage.value}`}
                >
                  {stage.value}
                </span>
                {conversion ? <span className="visually-hidden">{`, ${conversion}`}</span> : null}
              </span>
            </li>
          );
        })}
      </ol>
    </figure>
  );
}
