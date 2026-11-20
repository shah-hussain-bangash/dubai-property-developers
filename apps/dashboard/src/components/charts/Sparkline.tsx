export interface SparklineProps {
  values: number[];
  /** Accessible label, e.g. "Leads this week trend". */
  label: string;
  color?: string;
  className?: string;
}

const W = 100;
const H = 32;
const PAD = 3;

/** Tiny trend line for KPI cards. */
export function Sparkline({ values, label, color = 'var(--color-gold)', className }: SparklineProps) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = (W - PAD * 2) / (values.length - 1);
  const points = values.map((v, i) => ({
    x: PAD + i * step,
    y: PAD + (H - PAD * 2) * (1 - (v - min) / range),
  }));
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ');
  const last = points[points.length - 1];

  return (
    <svg className={className} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} preserveAspectRatio="none">
      <path
        d={path}
        style={{ fill: 'none', stroke: color, strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' }}
        vectorEffect="non-scaling-stroke"
      />
      {last ? <circle cx={last.x} cy={last.y} r={2.5} style={{ fill: color }} /> : null}
    </svg>
  );
}
