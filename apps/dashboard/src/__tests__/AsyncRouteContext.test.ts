// @vitest-environment node
import {afterEach, expect, it, vi} from 'vitest';
import {portalProxy} from '@/lib/portalProxy';
import {propertyPhotoApi} from '@/lib/agentPortalApi';
import {GET as proxy} from '@/app/api/v1/[...path]/route';
import {GET as photo} from '@/app/api/agent-portal/properties/[id]/photos/[photoId]/route';

vi.mock('@/lib/portalProxy', () => ({portalProxy: vi.fn()}));
vi.mock('@/lib/agentPortalApi', () => ({propertyPhotoApi: vi.fn()}));
afterEach(() => vi.clearAllMocks());

it('awaits catch-all segments and preserves the request for the protected proxy', async () => {
  const request = new Request('https://example.com/api/v1/accounts/me');
  const denied = new Response('Sign in', {status: 401});
  vi.mocked(portalProxy).mockResolvedValue(denied);
  expect(await proxy(request, {params: Promise.resolve({path: ['accounts', 'me']})})).toBe(denied);
  expect(portalProxy).toHaveBeenCalledExactlyOnceWith(request, ['accounts', 'me']);
});

it('awaits both photo identifiers and preserves the authorization response', async () => {
  const request = new Request('https://example.com/api/agent-portal/properties/p/photos/f');
  const denied = new Response('Forbidden', {status: 403});
  vi.mocked(propertyPhotoApi).mockResolvedValue(denied);
  expect(await photo(request, {params: Promise.resolve({id: 'p', photoId: 'f'})})).toBe(denied);
  expect(propertyPhotoApi).toHaveBeenCalledExactlyOnceWith(request, 'p', 'f');
});
