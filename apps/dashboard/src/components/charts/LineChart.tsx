import type { ChartDatum } from '@/types/domain';
import { ChartDataTable } from './ChartDataTable';
import styles from './charts.module.css';

export interface LineChartProps {
  data: ChartDatum[];
  title: string;
  height?: number;
  color?: string;
  formatValue?: (value: number) => string;
}

const WIDTH = 600;
const PAD = { top: 20, right: 16, bottom: 28, left: 36 };
const GRID_LINES = 4;

/** Single-series line chart with point markers and native hover tooltips. */
export function LineChart({
  data,
  title,
  height = 220,
  color = 'var(--chart-2)',
  formatValue = (v) => String(v),
}: LineChartProps) {
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = height - PAD.top - PAD.bottom;
  const rawMax = Math.max(0, ...data.map((d) => d.value));
  const max = rawMax > 0 ? Math.ceil(rawMax * 1.15) : 1;
  const step = data.length > 1 ? plotWidth / (data.length - 1) : 0;

  const points = data.map((d, i) => ({
    ...d,
    x: PAD.left + step * i,
    y: PAD.top + plotHeight - (d.value / max) * plotHeight,
  }));
  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  const first = points[0];
  const last = points[points.length - 1];
  const areaPath =
    first && last ? `${linePath} L${last.x},${PAD.top + plotHeight} L${first.x},${PAD.top + plotHeight} Z` : '';
  const ticks = Array.from({ length: GRID_LINES + 1 }, (_, i) => (max / GRID_LINES) * i);

  return (
    <figure className={styles.figure}>
      <svg className={styles.svg} viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label={title}>
        {ticks.map((tick) => {
          const y = PAD.top + plotHeight - (tick / max) * plotHeight;
          return (
            <g key={tick}>
              <line className={tick === 0 ? styles.baseline : styles.gridLine} x1={PAD.left} x2={WIDTH - PAD.right} y1={y} y2={y} />
              <text className={styles.axisText} x={PAD.left - 8} y={y + 4} textAnchor="end">
                {formatValue(Math.round(tick * 10) / 10)}
              </text>
            </g>
          );
        })}
        {areaPath ? <path d={areaPath} style={{ fill: color, opacity: 0.08 }} /> : null}
        <path d={linePath} style={{ fill: 'none', stroke: color, strokeWidth: 2, strokeLinejoin: 'round', strokeLinecap: 'round' }} />
        {points.map((p, i) => (
          <g key={p.label}>
            <circle className={styles.point} cx={p.x} cy={p.y} r={4} style={{ fill: color }}>
              <title>{`${p.label}: ${formatValue(p.value)}`}</title>
            </circle>
            {/* Invisible, larger hit target for hover tooltips */}
            <circle cx={p.x} cy={p.y} r={12} style={{ fill: 'transparent' }}>
              <title>{`${p.label}: ${formatValue(p.value)}`}</title>
            </circle>
            <text className={styles.axisText} x={p.x} y={height - 8} textAnchor="middle">
              {p.label}
            </text>
            {i === points.length - 1 ? (
              <text className={styles.valueText} x={p.x} y={p.y - 10} textAnchor="end">
                {formatValue(p.value)}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
      <ChartDataTable caption={title} data={data} formatValue={formatValue} />
    </figure>
  );
}
