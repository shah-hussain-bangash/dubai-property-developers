import type { Metadata } from 'next';
import { DataTable, type DataTableColumn } from '@/components/ui/DataTable';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { LocalKnowledgePanel } from '@/features/knowledge/LocalKnowledgePanel';
import { DemoKnowledgeForm } from '@/features/knowledge/DemoKnowledgeForm';
import { getFreshness, type KnowledgeRow } from '@/features/knowledge/freshness';
import { DEMO_KNOWLEDGE_DOCUMENTS, DEMO_REFERENCE_DATE } from '@/lib/demo-data';
import { formatDate } from '@/lib/format';

export const metadata: Metadata = {
  title: 'Knowledge',
};

const columns: DataTableColumn<KnowledgeRow>[] = [
  {
    key: 'title',
    header: 'Document',
    render: (doc) => (
      <span className="stack-sm" style={{ gap: 2 }}>
        <strong>{doc.title}</strong>
        <span className="subtle">{doc.category}</span>
      </span>
    ),
  },
  { key: 'version', header: 'Version', render: (doc) => <span className="chip">{doc.version}</span> },
  { key: 'updated', header: 'Last updated', render: (doc) => formatDate(doc.updatedAt), hideOnMobile: true },
  {
    key: 'freshness',
    header: 'Freshness',
    render: (doc) =>
      doc.stale ? (
        <span title={`Review interval is ${doc.reviewIntervalDays} days`}>
          <StatusBadge status="stale" label={`Stale Â· ${doc.ageDays}d old`} size="sm" />
        </span>
      ) : (
        <StatusBadge status="fresh" label={`Fresh Â· ${doc.ageDays}d old`} size="sm" />
      ),
  },
  { key: 'access', header: 'Access', render: (doc) => <StatusBadge status={doc.access} size="sm" /> },
  { key: 'owner', header: 'Owner', render: (doc) => <span className="muted">{doc.owner}</span>, hideOnMobile: true },
];

export default function KnowledgePage() {
  const rows = DEMO_KNOWLEDGE_DOCUMENTS.map((doc) => getFreshness(doc, DEMO_REFERENCE_DATE));
  const staleCount = rows.filter((row) => row.stale).length;

  return (
    <>
      <PageHeader
        eyebrow="AI System"
        title="Knowledge"
        description="Versioned documents agents may cite. Stale documents should be reviewed before agents rely on them."
      />
      <DemoDataBanner>Document titles and owners are placeholders. Freshness is computed against a fixed demo date.</DemoDataBanner>

      <LocalKnowledgePanel />
      <DemoKnowledgeForm />

      {staleCount > 0 ? (
        <div className="panel" role="status">
          <p>
            <StatusBadge status="stale" label={`${staleCount} stale document${staleCount === 1 ? '' : 's'}`} />{' '}
            <span className="muted">Past their review interval â€” schedule a content review.</span>
          </p>
        </div>
      ) : null}

      <section className="panel" aria-labelledby="kb-title">
        <div className="panel-header">
          <h2 id="kb-title" className="panel-title">
            Documents
          </h2>
          <p className="panel-subtitle">As of {formatDate(DEMO_REFERENCE_DATE)}</p>
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(doc) => doc.id}
          caption="Knowledge documents (demo data)"
          emptyTitle="No documents"
        />
      </section>
    </>
  );
}
