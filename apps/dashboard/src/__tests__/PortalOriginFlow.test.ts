// @vitest-environment node
import {mkdtemp, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {beforeEach, afterEach, expect, it, vi} from 'vitest';
import {sameLocalOrigin} from '@/lib/portalAuth';
import {publicEnquiryApi} from '@/lib/enquiryApi';
import {adminEnquiryWorkspace, setAgentAccess, updatePortalEnquiry, convertPortalEnquiry, agentWorkspace} from '@/lib/agentPropertyStore';

let directory: string;
const origin = 'https://portal.example.test';
const admin = {kind: 'admin', id: 'admin'} as const;
const agent = {kind: 'member', id: 'a'.repeat(32)} as const;
beforeEach(async () => {
  directory = await mkdtemp(path.join(os.tmpdir(), 'dpd-origin-flow-'));
  vi.stubEnv('DUBAI_PORTAL_DATA_DIR', directory);
  vi.stubEnv('DUBAI_PORTAL_PUBLIC_ORIGIN', '');
});
afterEach(async () => {
  vi.unstubAllEnvs();
  if (!path.basename(directory).startsWith('dpd-origin-flow-')) throw Error('Unexpected test folder');
  await rm(directory, {recursive: true, force: true});
});
const request = (hostOrigin: string, headers: Record<string, string> = {}) =>
  new Request(hostOrigin + '/api/public/enquiries', {headers});

it('keeps local ticket requests working without an Origin header', async () => {
  const result = await publicEnquiryApi(request('http://localhost:3000'));
  expect(result.status).toBe(200);
  expect((await result.json()).ticket).toMatch(/^[A-Za-z0-9_-]{43}$/);
});

it('requires explicit configuration for a public hostname', async () => {
  expect((await publicEnquiryApi(request(origin))).status).toBe(403);
  vi.stubEnv('DUBAI_PORTAL_PUBLIC_ORIGIN', origin);
  expect((await publicEnquiryApi(request(origin))).status).toBe(200);
  expect(sameLocalOrigin(request(origin, {Origin: origin}))).toBe(true);
  expect(sameLocalOrigin(request(origin))).toBe(false);
});

it.each(['http://portal.example.test', 'https://portal.example.test/path',
  'https://user:password@portal.example.test', 'https://portal.example.test?x=1', 'invalid'])
('fails closed for invalid public configuration: %s', async value => {
  vi.stubEnv('DUBAI_PORTAL_PUBLIC_ORIGIN', value);
  expect((await publicEnquiryApi(request(origin))).status).toBe(403);
  expect(sameLocalOrigin(request(origin, {Origin: origin}))).toBe(false);
});

it('rejects cross-site tickets, insecure writes, other hosts and forwarded-header spoofing', async () => {
  vi.stubEnv('DUBAI_PORTAL_PUBLIC_ORIGIN', origin);
  for (const req of [request(origin, {Origin:'https://evil.test'}),
    request(origin, {'Sec-Fetch-Site':'cross-site'}),
    request('https://evil.test', {'X-Forwarded-Host':'portal.example.test', Origin:origin})]) {
    expect((await publicEnquiryApi(req)).status).toBe(403);
  }
  expect(sameLocalOrigin(request(origin, {Origin:'http://portal.example.test'}))).toBe(false);
  expect(sameLocalOrigin(request('https://other.example.test', {Origin:origin}))).toBe(false);
  expect(sameLocalOrigin(request(origin, {Host:'evil.test', Origin:origin}))).toBe(false);
});

it.each(['http://localhost:3000', origin])('collects and assigns a customer enquiry at %s', async base => {
  vi.stubEnv('DUBAI_PORTAL_PUBLIC_ORIGIN', origin);
  const ticketResponse = await publicEnquiryApi(request(base));
  const {ticket} = await ticketResponse.json();
  const lead = {name:'Fictional QA customer', email:'qa@example.com', phone:'',
    interest:'Dubai Marina', message:'Fictional enquiry for local verification only.',
    purpose:'Sale', budgetMax:2500000, preference:'Email', page:'enquire'};
  const post = () => publicEnquiryApi(new Request(base+'/api/public/enquiries', {
    method:'POST', headers:{Origin:base,'Content-Type':'application/json'},
    body:JSON.stringify({...lead,ticket,consent:true,website:''})}));
  expect((await post()).status).toBe(201);
  expect((await post()).status).toBe(200);
  const saved = (await adminEnquiryWorkspace(admin)).enquiries;
  expect(saved).toHaveLength(1);
  await setAgentAccess(admin, agent.id, 'approved');
  const assigned = await updatePortalEnquiry(admin, saved[0].id, saved[0].version,
    {assignedTo:agent.id,status:'Assigned',notes:'QA review'});
  const result = await convertPortalEnquiry(agent, assigned.id, assigned.version, {
    name:lead.name,email:lead.email,phone:'',purpose:'Sale',budgetMin:0,budgetMax:2500000,
    community:'Dubai Marina',type:'Apartment',minBeds:2,stage:'New',notes:'QA reviewed'});
  expect(result.enquiry.clientId).toBe(result.client.id);
  expect((await agentWorkspace(agent)).clients).toHaveLength(1);
  expect((await agentWorkspace({kind:'member',id:'b'.repeat(32)})).clients).toEqual([]);
});
