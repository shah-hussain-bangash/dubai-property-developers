import type { Metadata } from 'next';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { getApiBaseUrl } from '@/lib/config';

export const metadata: Metadata = {
  title: 'Settings',
};

const APPROVAL_POLICIES = [
  { action: 'Sending any outbound WhatsApp or email message', requirement: 'Human approval required' },
  { action: 'Quoting prices, payment plans or availability', requirement: 'Human approval required' },
  { action: 'Discussing contract or legal terms', requirement: 'Escalate to broker' },
  { action: 'Updating lead status in CRM', requirement: 'Automatic (logged)' },
  { action: 'Scoring and categorising leads', requirement: 'Automatic (logged)' },
];

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Platform"
        title="Settings"
        description="Read-only view of platform configuration. Editing will be enabled once authentication and the settings API exist."
      />
      <DemoDataBanner message="Read-only preview — settings are not editable or persisted">
        Values shown are placeholder defaults, not the deployed configuration.
      </DemoDataBanner>

      <div className="grid-2">
        <section className="panel" aria-labelledby="approval-title">
          <div className="panel-header">
            <h2 id="approval-title" className="panel-title">
              Approval policies
            </h2>
            <StatusBadge status="checking" label="Read-only" size="sm" />
          </div>
          <dl className="kv">
            {APPROVAL_POLICIES.map((policy) => (
              <div key={policy.action} style={{ display: 'contents' }}>
                <dt>{policy.action}</dt>
                <dd>{policy.requirement}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="panel" aria-labelledby="retention-title">
          <div className="panel-header">
            <h2 id="retention-title" className="panel-title">
              Data retention
            </h2>
            <StatusBadge status="checking" label="Read-only" size="sm" />
          </div>
          <form className="stack-sm" aria-label="Data retention (read-only)">
            <div className="field">
              <label className="field-label" htmlFor="retention-conversations">
                Conversation transcripts (days)
              </label>
              <input id="retention-conversations" className="input" type="number" defaultValue={365} disabled />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="retention-leads">
                Closed-lost lead records (days)
              </label>
              <input id="retention-leads" className="input" type="number" defaultValue={730} disabled />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="retention-logs">
                Agent execution logs (days)
              </label>
              <input id="retention-logs" className="input" type="number" defaultValue={90} disabled />
            </div>
          </form>
        </section>

        <section className="panel" aria-labelledby="model-title">
          <div className="panel-header">
            <h2 id="model-title" className="panel-title">
              Model provider
            </h2>
            <StatusBadge status="mock" size="sm" />
          </div>
          <form className="stack-sm" aria-label="Model provider (read-only)">
            <div className="field">
              <label className="field-label" htmlFor="model-provider">
                Provider
              </label>
              <select id="model-provider" className="select" defaultValue="mock" disabled>
                <option value="mock">mock</option>
              </select>
            </div>
            <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>
              Agents currently use a deterministic mock model. No prompts or lead data leave the system.
            </p>
          </form>
        </section>

        <section className="panel" aria-labelledby="env-title">
          <div className="panel-header">
            <h2 id="env-title" className="panel-title">
              Environment
            </h2>
          </div>
          <dl className="kv">
            <dt>API base URL</dt>
            <dd className="mono">{getApiBaseUrl()}</dd>
            <dt>Authentication</dt>
            <dd>Not configured</dd>
            <dt>Time zone</dt>
            <dd>Asia/Dubai (GST, UTC+4)</dd>
          </dl>
        </section>
      </div>
    </>
  );
}
