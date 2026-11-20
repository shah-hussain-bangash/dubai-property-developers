'use client';

import { useRef, useState, type ReactNode } from 'react';

export interface ApprovalAccount {
  account_id: string;
  organization_id: string;
  full_name: string;
  approval_status: 'pending' | 'approved' | 'rejected' | null;
}

/**
 * Presentation only. Backend authentication and authorization must protect
 * every data endpoint. Do not pass protected data to an unauthorized browser.
 */
export function AccountApprovalGate({
  account,
  loading = false,
  failed = false,
  onRefresh,
  children,
}: {
  account: ApprovalAccount | null;
  loading?: boolean;
  failed?: boolean;
  onRefresh?: () => void;
  children: ReactNode;
}) {
  if (loading) return <p role="status">Checking your account?</p>;
  if (failed) {
    return (
      <section aria-label="Account access">
        <h1>Unable to check your account</h1>
        <p>Please try again.</p>
        {onRefresh && <button type="button" onClick={onRefresh}>Try again</button>}
      </section>
    );
  }
  if (!account) {
    return (
      <section aria-label="Account access">
        <h1>Sign in to continue</h1>
        <a href="/login">Go to sign in</a>
      </section>
    );
  }
  if (account.approval_status === 'approved') return <>{children}</>;

  const pending = account.approval_status === 'pending';
  const rejected = account.approval_status === 'rejected';
  return (
    <section aria-label="Account approval" aria-live="polite">
      <h1>{pending ? 'Waiting for owner approval' :
        rejected ? 'Account request declined' : 'Account review required'}</h1>
      <p>{pending
        ? 'Your dashboard will become available after the owner approves your account.'
        : 'Contact the owner for help with your account.'}</p>
      {onRefresh && (
        <button type="button" className="btn btn-primary" onClick={onRefresh}>
          Check account status
        </button>
      )}
    </section>
  );
}

/** Callbacks must use authenticated backend APIs; this panel grants no authority. */
export function OwnerApprovalPanel({
  accounts,
  onDecision,
}: {
  accounts: ApprovalAccount[];
  onDecision: (accountId: string, approve: boolean) => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [completed, setCompleted] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const inFlight = useRef(false);
  const pending = accounts.filter(
    account => account.approval_status === 'pending' && !completed.has(account.account_id),
  );

  async function decide(account: ApprovalAccount, approve: boolean) {
    if (inFlight.current || completed.has(account.account_id)) return;
    inFlight.current = true;
    setBusy(account.account_id);
    setError('');
    setMessage('');
    try {
      await onDecision(account.account_id, approve);
      setCompleted(previous => new Set([...previous, account.account_id]));
      setMessage(approve ? 'Account approved.' : 'Account request declined.');
    } catch {
      setError('The decision could not be confirmed. Refresh the list before trying again.');
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="account-approvals-title">
      <h1 id="account-approvals-title">Account approvals</h1>
      <p>Review requests for access to your organization.</p>
      {error && <p role="alert">{error}</p>}
      <p role="status" aria-live="polite">{message}</p>
      {pending.length === 0 ? <p>No pending account requests.</p> : (
        <ul>
          {pending.map(account => (
            <li key={account.account_id}>
              <p>{account.full_name}</p>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy !== null}
                aria-label={`Approve ${account.full_name}`}
                onClick={() => void decide(account, true)}
              >Approve</button>
              <button
                type="button"
                className="btn"
                disabled={busy !== null}
                aria-label={`Reject ${account.full_name}`}
                onClick={() => void decide(account, false)}
              >Reject</button>
              {busy === account.account_id && <span role="status">Saving decision?</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
