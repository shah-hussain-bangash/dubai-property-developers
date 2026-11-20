/**
 * Account API client awaiting an authenticated transport.
 * The transport must handle trusted API routing, authentication, cancellation,
 * and request timeouts. No tokens are stored and no transport is installed here.
 * Browser-side identity checks do not replace backend authorization.
 */
export interface AccountRecord {
  account_id: string;
  organization_id: string;
  full_name: string;
  approval_status: 'pending' | 'approved' | 'rejected' | null;
}

export interface AccountRequest {
  method: 'GET' | 'POST';
  body?: { approve: boolean };
  signal?: AbortSignal;
}

export type AccountTransport = (
  path: string,
  request: AccountRequest,
) => Promise<{ status: number; json: () => Promise<unknown> }>;

export class AccountApiError extends Error {
  constructor(message: string, public readonly status: number | null) {
    super(message);
    this.name = 'AccountApiError';
  }
}

function uuid(value: unknown): string {
  if (typeof value !== 'string' ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value) ||
      value === '00000000-0000-0000-0000-000000000000') {
    throw new AccountApiError('Invalid account identifier.', null);
  }
  return value.toLowerCase();
}

export function createAccountClient({
  request,
  userId,
  organizationId,
}: {
  request: AccountTransport;
  userId: string;
  organizationId: string;
}) {
  const user = uuid(userId);
  const organization = uuid(organizationId);

  function record(value: unknown, expectedId?: string): AccountRecord {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new AccountApiError('Invalid account response.', 502);
    }
    const data = value as Record<string, unknown>;
    const id = uuid(data.account_id);
    const org = uuid(data.organization_id);
    if (org !== organization || (expectedId !== undefined && id !== expectedId)) {
      throw new AccountApiError('Account response does not match this session.', 502);
    }
    const status = data.approval_status;
    if (typeof data.full_name !== 'string' || data.full_name.length > 200 ||
        (status !== null && status !== 'pending' &&
         status !== 'approved' && status !== 'rejected')) {
      throw new AccountApiError('Invalid account response.', 502);
    }
    return {
      account_id: id, organization_id: org,
      full_name: data.full_name, approval_status: status,
    };
  }

  async function send(path: string, options: AccountRequest): Promise<unknown> {
    let response: Awaited<ReturnType<AccountTransport>>;
    try {
      response = await request(path, options);
    } catch {
      throw new AccountApiError('Unable to contact the account service.', null);
    }
    if (!Number.isInteger(response.status) ||
        response.status < 100 || response.status > 599) {
      throw new AccountApiError('Invalid account service response.', 502);
    }
    if (response.status < 200 || response.status >= 300) {
      const message = response.status === 401 ? 'Please sign in again.' :
        response.status === 403 ? 'Account access denied.' :
        response.status === 409 ? 'Account status changed. Refresh the list.' :
        'The account service could not complete this request.';
      throw new AccountApiError(message, response.status);
    }
    try {
      return await response.json();
    } catch {
      throw new AccountApiError('Invalid account service response.', 502);
    }
  }

  return {
    async getSelf(signal?: AbortSignal): Promise<AccountRecord> {
      return record(await send('/api/v1/accounts/me', {
        method: 'GET', signal,
      }), user);
    },
    async listPending(signal?: AbortSignal): Promise<AccountRecord[]> {
      const data = await send('/api/v1/accounts/approvals/pending?limit=50', {
        method: 'GET', signal,
      });
      if (!Array.isArray(data) || data.length > 50) {
        throw new AccountApiError('Invalid pending accounts response.', 502);
      }
      const accounts = data.map(value => record(value));
      if (accounts.some(account => account.approval_status !== 'pending') ||
          new Set(accounts.map(account => account.account_id)).size !== accounts.length) {
        throw new AccountApiError('Invalid pending accounts response.', 502);
      }
      return accounts;
    },
    async decide(
      accountId: string, approve: boolean, signal?: AbortSignal,
    ): Promise<AccountRecord> {
      const target = uuid(accountId);
      if (typeof approve !== 'boolean' || target === user) {
        throw new AccountApiError('Invalid account decision.', null);
      }
      const account = record(await send(
        `/api/v1/accounts/${target}/approval`,
        { method: 'POST', body: { approve }, signal },
      ), target);
      if (account.approval_status !== (approve ? 'approved' : 'rejected')) {
        throw new AccountApiError('Account decision could not be confirmed.', 502);
      }
      return account;
    },
  };
}
