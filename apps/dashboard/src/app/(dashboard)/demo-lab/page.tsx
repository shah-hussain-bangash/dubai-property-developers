import type { Metadata } from 'next';
import { DemoQuickStart } from '@/features/overview/DemoQuickStart';
import { BarChart } from '@/components/charts/BarChart';
import { FunnelChart } from '@/components/charts/FunnelChart';
import { DataTable, type DataTableColumn } from '@/components/ui/DataTable';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { KpiCard } from '@/components/ui/KpiCard';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusBadge } from '@/components/ui/StatusBadge';
import {
  DEMO_AGENT_ACTIVITY,
  DEMO_LEAD_SOURCES,
  DEMO_OVERVIEW_KPIS,
  DEMO_PIPELINE_FUNNEL,
} from '@/lib/demo-data';
import { formatDateTime } from '@/lib/format';
import type { AgentActivity } from '@/types/domain';

export const metadata: Metadata = {
  title: 'Demo Lab',
};

const activityColumns: DataTableColumn<AgentActivity>[] = [
  { key: 'at', header: 'Time (GST)', render: (row) => <span className="muted">{formatDateTime(row.at)}</span> },
  { key: 'agent', header: 'Agent', render: (row) => row.agentName },
  { key: 'action', header: 'Action', render: (row) => row.action },
  { key: 'subject', header: 'Subject', render: (row) => row.subject, hideOnMobile: true },
  { key: 'outcome', header: 'Outcome', render: (row) => <StatusBadge status={row.outcome} size="sm" /> },
];

export default function OverviewPage() {
  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Overview"
        description="Pipeline health, human-approval queue and recent agent activity across the multi-agent system."
      />
      <DemoDataBanner>Figures below are fictional and for layout purposes only.</DemoDataBanner>

      <DemoQuickStart />

      <section className="grid-kpi" aria-label="Key indicators">
        {DEMO_OVERVIEW_KPIS.map((kpi) => (
          <KpiCard
            key={kpi.id}
            label={kpi.label}
            value={kpi.value}
            delta={kpi.delta}
            deltaTone={kpi.deltaTone}
            hint={kpi.hint}
            trend={kpi.trend}
          />
        ))}
      </section>

      <div className="grid-2">
        <section className="panel" aria-labelledby="lead-sources-title">
          <div className="panel-header">
            <h2 id="lead-sources-title" className="panel-title">
              Leads by source
            </h2>
            <p className="panel-subtitle">This week · demo</p>
          </div>
          <BarChart data={DEMO_LEAD_SOURCES} title="Leads by source this week (demo data)" />
        </section>

        <section className="panel" aria-labelledby="pipeline-title">
          <div className="panel-header">
            <h2 id="pipeline-title" className="panel-title">
              Pipeline funnel
            </h2>
            <p className="panel-subtitle">Captured → handed to broker · demo</p>
          </div>
          <FunnelChart data={DEMO_PIPELINE_FUNNEL} title="Lead pipeline funnel (demo data)" />
        </section>
      </div>

      <section className="panel" aria-labelledby="activity-title">
        <div className="panel-header">
          <h2 id="activity-title" className="panel-title">
            Recent agent activity
          </h2>
          <p className="panel-subtitle">Latest actions by AI agents</p>
        </div>
        <DataTable
          columns={activityColumns}
          rows={DEMO_AGENT_ACTIVITY}
          getRowKey={(row) => row.id}
          caption="Recent agent activity (demo data)"
          emptyTitle="No recent activity"
        />
      </section>
    </>
  );
}
