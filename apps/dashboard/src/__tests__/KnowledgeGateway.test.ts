// @vitest-environment node
import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {randomBytes} from 'node:crypto';
import {portalProxy} from '@/lib/portalProxy';
vi.mock('@/lib/portalAuth',()=>({ownerSession:vi.fn(async()=>({id:'owner'})),readSessionCookie:vi.fn(()=> 'fixture'),sameLocalOrigin:vi.fn(()=>true),privateJson:(data:unknown,status=200)=>new Response(JSON.stringify(data),{status})}));
import {ownerSession,sameLocalOrigin} from '@/lib/portalAuth';
let credential:string;
beforeEach(()=>{credential=randomBytes(32).toString('hex');vi.stubEnv('DUBAI_PORTAL_API_TOKEN',credential);vi.stubEnv('DUBAI_PORTAL_API_ORIGIN','http://api:8000');vi.mocked(ownerSession).mockResolvedValue({id:'owner'} as never);vi.mocked(sameLocalOrigin).mockReturnValue(true);vi.stubGlobal('fetch',vi.fn(async()=>new Response('{}')));});
afterEach(()=>{vi.unstubAllEnvs();vi.unstubAllGlobals();});
const request=(method='GET')=>new Request('https://example.com/api/v1/knowledge/agents/documents/sources',{method,...(method==='POST'?{body:'{"kind":"text"}',headers:{'Content-Type':'application/json'}}:{})});
it('keeps the service credential server-side and forwards only an owner-authenticated source write',async()=>{const response=await portalProxy(request('POST'),['knowledge','agents','documents','sources']);expect(response.status).toBe(200);const options=vi.mocked(fetch).mock.calls[0][1];expect((options?.headers as Record<string,string>).Authorization).toBe('Bearer '+credential);expect(await response.text()).not.toContain(credential);});
it('denies every unrelated write even for an owner',async()=>{for(const path of [['leads'],['workflows','execute'],['knowledge','demo-answer']])expect((await portalProxy(request('POST'),path)).status).toBe(403);expect(fetch).not.toHaveBeenCalled();});
it('requires a current owner session and same-origin request',async()=>{vi.mocked(sameLocalOrigin).mockReturnValue(false);expect((await portalProxy(request('POST'),['knowledge','agents','documents','sources'])).status).toBe(403);vi.mocked(ownerSession).mockResolvedValue(null);expect((await portalProxy(request(),['knowledge','agents'])).status).toBe(401);expect(fetch).not.toHaveBeenCalled();});
it('permits only exact source-removal paths',async()=>{expect((await portalProxy(request('DELETE'),['knowledge','agents','documents','sources','a'.repeat(64)])).status).toBe(200);expect((await portalProxy(request('DELETE'),['knowledge','agents','documents','sources','not-an-id'])).status).toBe(403);});
it('rejects malformed service configuration before sending any request',async()=>{vi.stubEnv('DUBAI_PORTAL_API_TOKEN','invalid');expect((await portalProxy(request(),['agents'])).status).toBe(503);expect(fetch).not.toHaveBeenCalled();});
