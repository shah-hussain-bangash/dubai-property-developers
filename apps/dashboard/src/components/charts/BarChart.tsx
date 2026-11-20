import type { ChartDatum } from '@/types/domain';
import { ChartDataTable } from './ChartDataTable';
import styles from './charts.module.css';

export interface BarChartProps {
  data: ChartDatum[];
  /** Accessible name describing what the chart shows. */
  title: string;
  height?: number;
  color?: string;
  formatValue?: (value: number) => string;
}

const WIDTH = 600;
const PAD = { top: 20, right: 8, bottom: 28, left: 36 };
const GRID_LINES = 4;

/** Path for a bar with 4px rounded top corners and a square baseline. */
function barPath(x: number, y: number, w: number, h: number, r: number): string {
  const radius = Math.min(r, w / 2, h);
  return [
    `M${x},${y + h}`,
    `V${y + radius}`,
    `Q${x},${y} ${x + radius},${y}`,
    `H${x + w - radius}`,
    `Q${x + w},${y} ${x + w},${y + radius}`,
    `V${y + h}`,
    'Z',
  ].join(' ');
}

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  const normalized = value / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

/** Single-series vertical bar chart (hand-written SVG). */
export function BarChart({
  data,
  title,
  height = 240,
  color = 'var(--chart-1)',
  formatValue = (v) => String(v),
}: BarChartProps) {
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = height - PAD.top - PAD.bottom;
  const max = niceMax(Math.max(0, ...data.map((d) => d.value)));
  const band = data.length > 0 ? plotWidth / data.length : plotWidth;
  const barWidth = Math.min(48, band * 0.56);
  const ticks = Array.from({ length: GRID_LINES + 1 }, (_, i) => (max / GRID_LINES) * i);

  return (
    <figure className={styles.figure}>
      <svg
        className={styles.svg}
        viewBox={`0 0 ${WIDTH} ${height}`}
        role="img"
        aria-label={title}
        preserveAspectRatio="xMidYMid meet"
      >
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
        {data.map((d, i) => {
          const h = max > 0 ? (d.value / max) * plotHeight : 0;
          const x = PAD.left + band * i + (band - barWidth) / 2;
          const y = PAD.top + plotHeight - h;
          return (
            <g key={d.label}>
              <path className={styles.bar} d={barPath(x, y, barWidth, Math.max(h, 0.5), 4)} style={{ fill: color }}>
                <title>{`${d.label}: ${formatValue(d.value)}`}</title>
              </path>
              <text className={styles.valueText} x={x + barWidth / 2} y={y - 6} textAnchor="middle">
                {formatValue(d.value)}
              </text>
              <text className={styles.axisText} x={x + barWidth / 2} y={height - 8} textAnchor="middle">
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>
      <ChartDataTable caption={title} data={data} formatValue={formatValue} />
    </figure>
  );
}
