'use client';

import Link from 'next/link';
import { workflowDemoLink } from '@/services/workflowDemoLinks';
import { useRef, useState } from 'react';
import { filterWorkflows, type WorkflowStatusFilter } from '@/services/workflowFilters';
import { DataSourceIndicator } from '@/components/ui/DataSourceIndicator';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { LoadingState } from '@/components/ui/LoadingState';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useApiResource } from '@/hooks/useApiResource';
import { DEMO_WORKFLOWS_RESPONSE } from '@/lib/demo-data';
import { getWorkflows } from '@/services/api';
import { IMPLEMENTATION_STATUSES, type WorkflowListResponse } from '@/types/api';
import { DemoScenarioForm } from './DemoScenarioForm';
import { WorkflowPipeline } from './WorkflowPipeline';
import styles from './workflows.module.css';

const fetchWorkflows = (signal: AbortSignal): Promise<WorkflowListResponse> => getWorkflows({ signal });

export function WorkflowsView() {
  const { data, source, error, reload } = useApiResource(fetchWorkflows, DEMO_WORKFLOWS_RESPONSE);

  const searchInput = useRef<HTMLInputElement>(null);
  function resetFilters() { setQuery(''); setStatus('all'); searchInput.current?.focus(); }
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<WorkflowStatusFilter>('all');
  const visible = data ? filterWorkflows(data.items, query, status) : [];

  return (
    <>
      <PageHeader
        eyebrow="AI System"
        title="Workflows"
        description="Multi-agent workflows and the ordered steps each one executes."
        actions={
          <>
            <DataSourceIndicator source={source} />
            <button type="button" className="btn" onClick={reload} disabled={source === 'loading'}>
              Refresh
            </button>
          </>
        }
      />

      {source === 'loading' ? <LoadingState label="Loading workflows from the backend…" /> : null}

      {source === 'demo' ? (
        <>
          <ErrorState
            compact
            title="Backend unreachable — showing demo workflows"
            message={error ?? 'The workflow registry could not be loaded.'}
            onRetry={reload}
          />
          <DemoDataBanner>These workflow definitions are a local copy, not read from the backend.</DemoDataBanner>
        </>
      ) : null}

      {data && <section className={'panel ' + styles.filters} aria-labelledby="workflow-filters-title">
        <h2 id="workflow-filters-title">Find a workflow definition</h2>
        <p>Search workflow names, descriptions or step names. Filters apply to the definitions below; the guided demo remains available.</p>
        <div className={styles.filterFields}>
          <label htmlFor="workflow-query">Search workflows<input id="workflow-query" ref={searchInput} type="search" maxLength={200} value={query} onChange={event => setQuery(event.target.value)} placeholder="Workflow or step name" /></label>
          <label htmlFor="workflow-status-filter">Workflow implementation status<select id="workflow-status-filter" value={status} onChange={event => setStatus(event.target.value as WorkflowStatusFilter)}><option value="all">All statuses</option>{IMPLEMENTATION_STATUSES.map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
          <button className="btn" type="button" disabled={!query && status === 'all'} onClick={resetFilters}>Reset workflow filters</button>
        </div>
        <p role="status">{visible.length} of {data.items.length} workflow definitions shown</p>
        <a className="btn" href="#workflow-definitions">Jump to definitions</a>
      </section>}
      <DemoScenarioForm />

      {data && <h2 id="workflow-definitions" className={styles.registryTitle}>Workflow definitions</h2>}
      {data ? (
        data.items.length === 0 ? (
          <EmptyState title="No workflows registered" description="The backend returned an empty workflow registry." />
        ) : visible.length === 0 ? (
          <EmptyState title="No workflow definitions match" description="Try another search or reset the workflow filters." action={<button className="btn" type="button" onClick={resetFilters}>Show all workflow definitions</button>} />
        ) : (
          <ul className={styles.list} aria-label="Workflows">
            {visible.map((workflow) => {
              const demo = workflowDemoLink(workflow);
              return (
              <li key={workflow.workflow_id} className={`panel ${styles.card}`}>
                <div className={styles.header}>
                  <div>
                    <h2 className={styles.name}>{workflow.name}</h2>
                    <p className={styles.id}>
                      <code>{workflow.workflow_id}</code> · {workflow.steps.length} steps
                    </p>
                  </div>
                  <StatusBadge status={workflow.implementation_status} size="sm" />
                </div>
                <p className={styles.description}>{workflow.description}</p>
                <WorkflowPipeline steps={workflow.steps} label={`${workflow.name} steps`} />
                {demo && <div><p className={styles.description}>{demo.description}</p><Link className="btn" href={demo.href}>{demo.label}</Link></div>}
              </li>
              );
            })}
          </ul>
        )
      ) : null}
    </>
  );
}
