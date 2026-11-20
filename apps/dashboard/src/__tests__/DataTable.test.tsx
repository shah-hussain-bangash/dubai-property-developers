import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DataTable, type DataTableColumn } from '@/components/ui/DataTable';

interface Row {
  id: string;
  name: string;
  score: number;
}

const columns: DataTableColumn<Row>[] = [
  { key: 'name', header: 'Name', render: (row) => row.name },
  { key: 'score', header: 'Score', render: (row) => row.score, align: 'right' },
];

describe('DataTable', () => {
  it('renders column headers and one row per item', () => {
    const rows: Row[] = [
      { id: 'a', name: 'Demo Lead 01', score: 80 },
      { id: 'b', name: 'Demo Lead 02', score: 55 },
    ];
    render(<DataTable columns={columns} rows={rows} getRowKey={(r) => r.id} caption="Test table" />);

    const table = screen.getByRole('table', { name: 'Test table' });
    expect(within(table).getByRole('columnheader', { name: 'Name' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Score' })).toBeInTheDocument();
    // header row + 2 body rows
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    expect(within(table).getByText('Demo Lead 02')).toBeInTheDocument();
    expect(within(table).getByText('80')).toBeInTheDocument();
  });

  it('renders the empty state when there are no rows', () => {
    render(
      <DataTable
        columns={columns}
        rows={[]}
        getRowKey={(r) => r.id}
        caption="Empty table"
        emptyTitle="Nothing here"
        emptyDescription="No rows yet."
      />,
    );
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
    expect(screen.getByText('No rows yet.')).toBeInTheDocument();
  });
});
