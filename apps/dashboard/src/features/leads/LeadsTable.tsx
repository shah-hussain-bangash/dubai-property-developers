import { DataTable, type DataTableColumn } from '@/components/ui/DataTable';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatDate } from '@/lib/format';
import type { Lead } from '@/types/domain';
import { LEAD_SOURCE_LABELS } from './leadLabels';

function ScoreMeter({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <span className="meter">
      <span className="meter-track" aria-hidden="true">
        <span className="meter-fill" style={{ width: `${clamped}%` }} />
      </span>
      <span className="meter-value">{clamped}</span>
    </span>
  );
}

const columns: DataTableColumn<Lead>[] = [
  {
    key: 'name',
    header: 'Lead',
    render: (lead) => (
      <span className="stack-sm" style={{ gap: 2 }}>
        <strong>{lead.name}</strong>
        <span className="subtle mono">{lead.email}</span>
      </span>
    ),
  },
  { key: 'phone', header: 'Phone', render: (lead) => <span className="mono">{lead.phone}</span>, hideOnMobile: true },
  { key: 'score', header: 'Score', render: (lead) => <ScoreMeter score={lead.score} /> },
  { key: 'category', header: 'Category', render: (lead) => <StatusBadge status={lead.category} size="sm" /> },
  { key: 'source', header: 'Source', render: (lead) => LEAD_SOURCE_LABELS[lead.source], hideOnMobile: true },
  { key: 'status', header: 'Status', render: (lead) => <StatusBadge status={lead.status} size="sm" /> },
  { key: 'agent', header: 'Assigned agent', render: (lead) => lead.assignedAgent, hideOnMobile: true },
  { key: 'interest', header: 'Interest', render: (lead) => <span className="muted">{lead.interest}</span>, hideOnMobile: true },
  { key: 'created', header: 'Created', render: (lead) => <span className="muted">{formatDate(lead.createdAt)}</span>, hideOnMobile: true },
];

export function LeadsTable({ leads }: { leads: Lead[] }) {
  return (
    <DataTable
      columns={columns}
      rows={leads}
      getRowKey={(lead) => lead.id}
      caption="Leads (demo data)"
      emptyTitle="No leads yet"
      emptyDescription="New leads captured by the Lead Intake Agent will appear here."
    />
  );
}
