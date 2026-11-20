'use client';

import { useRef, useState } from 'react';
import { filterAgents, type AgentStatusFilter } from '@/services/agentFilters';
import { DataSourceIndicator } from '@/components/ui/DataSourceIndicator';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { LoadingState } from '@/components/ui/LoadingState';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useApiResource } from '@/hooks/useApiResource';
import { DEMO_AGENTS_RESPONSE } from '@/lib/demo-data';
import { getAgents } from '@/services/api';
import { IMPLEMENTATION_STATUSES, type AgentListResponse } from '@/types/api';
import { AgentCard } from './AgentCard';
import styles from './agents.module.css';

const fetchAgents = (signal: AbortSignal): Promise<AgentListResponse> => getAgents({ signal });

export function AgentsView() {
  const { data, source, error, reload } = useApiResource(fetchAgents, DEMO_AGENTS_RESPONSE);

  const searchInput = useRef<HTMLInputElement>(null);
  function resetFilters() { setQuery(''); setStatus('all'); searchInput.current?.focus(); }
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<AgentStatusFilter>('all');
  const visible = data ? filterAgents(data.items, query, status) : [];

  return (
    <>
      <PageHeader
        eyebrow="AI System"
        title="Agents"
        description="Registered agents, their implementation status and the tools each one is permitted to call."
        actions={
          <>
            <DataSourceIndicator source={source} />
            <button type="button" className="btn" onClick={reload} disabled={source === 'loading'}>
              Refresh
            </button>
          </>
        }
      />

      {source === 'loading' ? <LoadingState label="Loading agents from the backend…" /> : null}

      {source === 'demo' ? (
        <>
          <ErrorState
            compact
            title="Backend unreachable — showing demo agents"
            message={error ?? 'The agent registry could not be loaded.'}
            onRetry={reload}
          />
          <DemoDataBanner>This list mirrors the planned agent registry; it is not read from the backend.</DemoDataBanner>
        </>
      ) : null}

      {data ? (
        <>
          <section className={'panel ' + styles.filters} aria-labelledby="agent-filters-title">
            <h2 id="agent-filters-title">Find an agent</h2>
            <p>Search agent names, responsibilities or permitted tool names. Implementation status describes completeness; listed tool permissions do not confirm that live integrations are enabled.</p>
            <div className={styles.filterFields}>
              <label htmlFor="agent-query">Search agents<input id="agent-query" ref={searchInput} type="search" maxLength={200} value={query} onChange={event => setQuery(event.target.value)} placeholder="Name, responsibility or tool" /></label>
              <label htmlFor="agent-status-filter">Implementation status<select id="agent-status-filter" value={status} onChange={event => setStatus(event.target.value as AgentStatusFilter)}><option value="all">All statuses</option>{IMPLEMENTATION_STATUSES.map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
              <button className="btn" type="button" disabled={!query && status === 'all'} onClick={resetFilters}>Reset agent filters</button>
            </div>
            <p role="status">{visible.length} of {data.items.length} agents shown</p>
          </section>
          <ul className={styles.summary} aria-label="Agents by implementation status">
            <li>
              <StatusBadge status="info" tone="info" label={`${data.total} agents`} />
            </li>
            {IMPLEMENTATION_STATUSES.map((status) => {
              const count = data.items.filter((agent) => agent.implementation_status === status).length;
              return (
                <li key={status}>
                  <StatusBadge status={status} label={`${count} ${status.replace('_', ' ')}`} />
                </li>
              );
            })}
          </ul>

          {data.items.length === 0 ? (
            <EmptyState title="No agents registered" description="The backend returned an empty agent registry." />
          ) : visible.length === 0 ? (
            <EmptyState title="No agents match these filters" description="Try another search or reset the agent filters." action={<button className="btn" type="button" onClick={resetFilters}>Show all agents</button>} />
          ) : (
            <ul className={`grid-cards ${styles.list}`} aria-label="Agents">
              {visible.map((agent) => (
                <li key={agent.agent_id}>
                  <AgentCard agent={agent} />
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </>
  );
}
