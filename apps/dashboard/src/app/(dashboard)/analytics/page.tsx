import type { Metadata } from 'next';
import { BarChart } from '@/components/charts/BarChart';
import { DonutChart } from '@/components/charts/DonutChart';
import { FunnelChart } from '@/components/charts/FunnelChart';
import { LineChart } from '@/components/charts/LineChart';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import {
  DEMO_CHANNEL_MIX,
  DEMO_LEAD_CATEGORIES,
  DEMO_PIPELINE_FUNNEL,
  DEMO_RESPONSE_TIME_MINUTES,
  DEMO_WEEKLY_LEADS,
} from '@/lib/demo-data';

export const metadata: Metadata = {
  title: 'Analytics',
};

export default function AnalyticsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Platform"
        title="Analytics"
        description="Lead volume, channel mix, agent response times and pipeline conversion."
      />
      <DemoDataBanner>Charts are rendered from fictional sample series, not production metrics.</DemoDataBanner>

      <div className="grid-2">
        <section className="panel" aria-labelledby="weekly-title">
          <div className="panel-header">
            <h2 id="weekly-title" className="panel-title">
              Weekly leads
            </h2>
            <p className="panel-subtitle">Last 8 weeks</p>
          </div>
          <LineChart data={DEMO_WEEKLY_LEADS} title="Weekly lead volume, last 8 weeks (demo data)" />
        </section>

        <section className="panel" aria-labelledby="response-title">
          <div className="panel-header">
            <h2 id="response-title" className="panel-title">
              Median first-response time
            </h2>
            <p className="panel-subtitle">Minutes, by weekday</p>
          </div>
          <BarChart
            data={DEMO_RESPONSE_TIME_MINUTES}
            title="Median first-response time in minutes by weekday (demo data)"
            color="var(--chart-5)"
            formatValue={(v) => v.toFixed(1)}
          />
        </section>

        <section className="panel" aria-labelledby="channel-title">
          <div className="panel-header">
            <h2 id="channel-title" className="panel-title">
              Conversation channel mix
            </h2>
            <p className="panel-subtitle">Share of conversations</p>
          </div>
          <DonutChart data={DEMO_CHANNEL_MIX} title="Conversation channel mix (demo data)" centerLabel="Convos" />
        </section>

        <section className="panel" aria-labelledby="category-title">
          <div className="panel-header">
            <h2 id="category-title" className="panel-title">
              Lead categories
            </h2>
            <p className="panel-subtitle">Current demo leads</p>
          </div>
          <DonutChart data={DEMO_LEAD_CATEGORIES} title="Lead categories (demo data)" centerLabel="Leads" />
        </section>
      </div>

      <section className="panel" aria-labelledby="funnel-title">
        <div className="panel-header">
          <h2 id="funnel-title" className="panel-title">
            Conversion funnel
          </h2>
          <p className="panel-subtitle">Stage-to-stage conversion</p>
        </div>
        <FunnelChart data={DEMO_PIPELINE_FUNNEL} title="Pipeline conversion funnel (demo data)" />
      </section>
    </>
  );
}
