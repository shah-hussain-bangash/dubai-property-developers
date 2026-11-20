'use client';

import { useEffect, useMemo, useState } from 'react';
import { createAccountClient, type AccountRecord } from '../../services/accounts';
import { createBrowserAccountTransport } from '../../services/browserAccounts';
import { AccountApprovalGate, OwnerApprovalPanel } from './AccountApproval';

/** Opt-in account controls. Every API operation still requires backend authorization. */
export function BrowserAccountSession({ enabled = false }: { enabled?: boolean }) {
  const request = useMemo(() => createBrowserAccountTransport(), []);
  const [account, setAccount] = useState<AccountRecord | null>(null);
  const [pending, setPending] = useState<AccountRecord[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setAccount(null);
    setPending(null);
    void (async () => {
      try {
        const response = await request('/api/v1/accounts/me', { method: 'GET', signal: controller.signal });
        if (response.status === 401) return;
        if (response.status !== 200) throw new Error('account unavailable');
        const body: unknown = await response.json();
        if (!body || typeof body !== 'object') throw new Error('invalid account');
        const identity = body as Record<string, unknown>;
        // The server selects the identity. The existing client validates UUIDs,
        // tenant consistency, account status, and the subsequent account response.
        if (typeof identity.account_id !== 'string' || typeof identity.organization_id !== 'string') {
          throw new Error('invalid account');
        }
        const client = createAccountClient({ request, userId: identity.account_id,
          organizationId: identity.organization_id });
        const checked = await client.getSelf(controller.signal);
        if (!controller.signal.aborted) setAccount(checked);
      } catch {
        if (!controller.signal.aborted) setError('Unable to check your account. Please try again.');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [enabled, request, revision]);

  if (!enabled) return <p role="status">Account sign-in is not enabled.</p>;
  const client = account ? createAccountClient({ request, userId: account.account_id,
    organizationId: account.organization_id }) : null;

  async function loadPending() {
    if (!client || busy) return;
    setBusy(true);
    setError('');
    try { setPending(await client.listPending()); }
    catch { setError('Account requests could not be loaded. Owner access is required.'); }
    finally { setBusy(false); }
  }

  async function logout() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const response = await request('/api/v1/auth/browser/logout', { method: 'POST' });
      if (response.status !== 204) throw new Error('logout unavailable');
      setAccount(null);
      setPending(null);
      // Cancel any in-flight identity refresh and check the revoked session.
      setRevision(value => value + 1);
    } catch { setError('Sign-out could not be confirmed. Please try again.'); }
    finally { setBusy(false); }
  }

  return (
    <section aria-label="Account session">
      {/* OAuth needs a full navigation; prefetch would start an unused login flow. */}
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
      {!account && !loading && <a href="/api/v1/auth/google/start">Sign in with Google</a>}
      {error && <p role="alert">{error}</p>}
      <AccountApprovalGate account={account} loading={loading} failed={!!error && !account}
        onRefresh={() => setRevision(value => value + 1)}>
        <p>Your account is approved.</p>
        <button type="button" disabled={busy} onClick={() => void loadPending()}>Review account requests</button>
        {pending && client && <OwnerApprovalPanel accounts={pending} onDecision={async (id, approve) => {
          await client.decide(id, approve);
        }} />}
      </AccountApprovalGate>
      {account && <button type="button" disabled={busy} onClick={() => void logout()}>Sign out</button>}
    </section>
  );
}
