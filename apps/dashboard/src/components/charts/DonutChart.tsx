import type { ChartDatum } from '@/types/domain';
import { ChartDataTable } from './ChartDataTable';
import styles from './charts.module.css';

export interface DonutChartProps {
  data: ChartDatum[];
  title: string;
  /** Small caption under the total in the centre. */
  centerLabel?: string;
  formatValue?: (value: number) => string;
}

/** Categorical colours in a fixed order (never cycled past the list). */
const SERIES_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)'];

const SIZE = 160;
const STROKE = 18;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const GAP = 2;

export function DonutChart({ data, title, centerLabel = 'Total', formatValue = (v) => String(v) }: DonutChartProps) {
  const visible = data.slice(0, SERIES_COLORS.length);
  const total = visible.reduce((sum, d) => sum + d.value, 0);
  let offset = 0;
  const segments = visible.map((d, i) => {
    const length = total > 0 ? (d.value / total) * CIRCUMFERENCE : 0;
    const segment = {
      ...d,
      color: SERIES_COLORS[i] ?? 'var(--color-neutral)',
      dash: Math.max(length - GAP, 0),
      offset,
      share: total > 0 ? d.value / total : 0,
    };
    offset += length;
    return segment;
  });

  return (
    <figure className={styles.figure}>
      <div className={styles.donutLayout}>
        <svg className={styles.donutSvg} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={title}>
          <circle cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} style={{ fill: 'none', stroke: 'var(--chart-track)', strokeWidth: STROKE }} />
          <g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
            {segments.map((s) => (
              <circle
                key={s.label}
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={RADIUS}
                strokeDasharray={`${s.dash} ${CIRCUMFERENCE - s.dash}`}
                strokeDashoffset={-s.offset}
                style={{ fill: 'none', stroke: s.color, strokeWidth: STROKE }}
              >
                <title>{`${s.label}: ${formatValue(s.value)} (${Math.round(s.share * 100)}%)`}</title>
              </circle>
            ))}
          </g>
          <text className={styles.donutTotal} x={SIZE / 2} y={SIZE / 2 + 4} textAnchor="middle">
            {formatValue(total)}
          </text>
          <text className={styles.donutCaption} x={SIZE / 2} y={SIZE / 2 + 22} textAnchor="middle">
            {centerLabel}
          </text>
        </svg>
        <ul className={styles.legend} aria-label={`${title} legend`}>
          {segments.map((s) => (
            <li key={s.label} className={styles.legendItem}>
              <span className={styles.swatch} style={{ background: s.color }} aria-hidden="true" />
              <span>{s.label}</span>
              <span className={styles.legendValue}>
                {formatValue(s.value)} · {Math.round(s.share * 100)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
      <ChartDataTable caption={title} data={visible} formatValue={formatValue} />
    </figure>
  );
}
