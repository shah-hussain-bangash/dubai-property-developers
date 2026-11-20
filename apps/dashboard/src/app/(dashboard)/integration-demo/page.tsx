import type { Metadata } from 'next';
import { DemoIntegrationGuide } from '@/features/integrations/DemoIntegrationGuide';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { DEMO_INTEGRATIONS } from '@/lib/demo-data';
import styles from '@/features/integrations/integrations.module.css';

export const metadata: Metadata = {
  title: 'Integrations',
};

export default function IntegrationsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Platform"
        title="Integrations"
        description="External systems the agents can use. Nothing is connected yet — connectors run in mock mode or await configuration."
      />
      <DemoDataBanner message="Placeholder statuses — no live connectors">
        This page collects no credentials and sends no messages, emails or calls.
      </DemoDataBanner>

      <DemoIntegrationGuide />

      <ul className={`grid-cards ${styles.list}`} aria-label="Integrations">
        {DEMO_INTEGRATIONS.map((integration) => (
          <li key={integration.id} className={`panel ${styles.card}`}>
            <div className={styles.header}>
              <div>
                <h2 className={styles.name}>{integration.name}</h2>
                <p className={styles.category}>{integration.category}</p>
              </div>
              <StatusBadge status={integration.mode} size="sm" />
            </div>
            <p className={styles.description}>{integration.description}</p>
            <p className={styles.note}>{integration.note}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
