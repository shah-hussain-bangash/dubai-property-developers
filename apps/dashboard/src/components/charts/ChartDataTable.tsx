import type { ChartDatum } from '@/types/domain';

export interface ChartDataTableProps {
  caption: string;
  data: ChartDatum[];
  valueHeader?: string;
  formatValue?: (value: number) => string;
}

/** Visually hidden data table that gives screen readers the chart values. */
export function ChartDataTable({ caption, data, valueHeader = 'Value', formatValue = String }: ChartDataTableProps) {
  return (
    <table className="visually-hidden">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">Label</th>
          <th scope="col">{valueHeader}</th>
        </tr>
      </thead>
      <tbody>
        {data.map((d) => (
          <tr key={d.label}>
            <th scope="row">{d.label}</th>
            <td>{formatValue(d.value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
