import type { Metadata } from 'next';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { DemoLeadForm } from '@/features/leads/DemoLeadForm';
import { LeadsTable } from '@/features/leads/LeadsTable';
import { DEMO_LEADS } from '@/lib/demo-data';
import type { LeadCategory } from '@/types/domain';

export const metadata: Metadata = {
  title: 'Leads',
};

const CATEGORIES: LeadCategory[] = ['hot', 'warm', 'cold'];

export default function LeadsPage() {
  const counts = CATEGORIES.map((category) => ({
    category,
    count: DEMO_LEADS.filter((lead) => lead.category === category).length,
  }));

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Leads"
        description="Leads captured and scored by the Lead Intake and Qualification agents."
      />
      <DemoDataBanner>All leads, phone numbers and emails are fictional.</DemoDataBanner>

      <DemoLeadForm />

      <section className="panel" aria-labelledby="leads-title">
        <div className="panel-header">
          <h2 id="leads-title" className="panel-title">
            All leads <span className="subtle">({DEMO_LEADS.length})</span>
          </h2>
          <ul className="chip-list" aria-label="Leads by category">
            {counts.map(({ category, count }) => (
              <li key={category}>
                <StatusBadge status={category} label={`${category.charAt(0).toUpperCase()}${category.slice(1)} · ${count}`} size="sm" />
              </li>
            ))}
          </ul>
        </div>
        <LeadsTable leads={DEMO_LEADS} />
      </section>
    </>
  );
}
