import Link from 'next/link';
import { agentDemoLink } from '@/services/agentDemoLinks';
import { StatusBadge } from '@/components/ui/StatusBadge';
import type { AgentDescriptor } from '@/types/api';
import styles from './agents.module.css';

export function AgentCard({ agent }: { agent: AgentDescriptor }) {
  const demo = agentDemoLink(agent);
  const headingId = `agent-${agent.agent_id}`;
  return (
    <article className={`panel ${styles.card}`} aria-labelledby={headingId} data-status={agent.implementation_status}>
      <header className={styles.header}>
        <span className={styles.indicator} data-status={agent.implementation_status} aria-hidden="true" />
        <div className={styles.titles}>
          <h2 id={headingId} className={styles.name}>
            {agent.name}
          </h2>
          <p className={styles.id}>
            <code>{agent.agent_id}</code> · v{agent.version}
          </p>
        </div>
        <StatusBadge status={agent.implementation_status} size="sm" />
      </header>

      <p className={styles.description}>{agent.description}</p>

      {agent.responsibilities.length > 0 ? (
        <div>
          <h3 className={styles.sectionTitle}>Responsibilities</h3>
          <ul className={styles.responsibilities}>
            {agent.responsibilities.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <h3 className={styles.sectionTitle}>Tool permissions ({agent.allowed_tools.length})</h3>
        {agent.allowed_tools.length > 0 ? (
          <ul className="chip-list" aria-label={`Tools allowed for ${agent.name}`}>
            {agent.allowed_tools.map((tool) => (
              <li key={tool} className="chip">
                {tool}
              </li>
            ))}
          </ul>
        ) : (
          <p className="subtle">No tools granted.</p>
        )}
      </div>

      {demo && <div>
        <h3 className={styles.sectionTitle}>Explore with fictional data</h3>
        <p className={styles.description}>{demo.description}</p>
        <Link href={demo.href} className="btn">{demo.label}</Link>
      </div>}
      <footer className={styles.footer}>
        <span>Timeout</span>
        <strong>{agent.timeout_seconds}s</strong>
      </footer>
    </article>
  );
}
