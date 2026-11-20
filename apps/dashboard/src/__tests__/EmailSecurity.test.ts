// @vitest-environment node

import {mkdtemp,rm,readFile,writeFile} from 'node:fs/promises';import path from 'node:path';import os from 'node:os';import {scryptSync} from 'node:crypto';import {beforeEach,afterEach,it,expect,vi} from 'vitest';import {memberSignup,memberSignIn,memberSession,memberSecurityOverview,memberRevokeSessions,memberChangePassword,adminMemberSessionDirectory,prepareMemberEmail,finishMemberEmail,verifyMemberEmail,resetMemberPassword,memberEmailStatus,adminSetMemberAccess,MEMBER_COOKIE} from '@/lib/portalMembers';import {ownerSignIn,ownerSession,ownerSecurityOverview,ownerRevokeSessions,ownerReauthenticate,SESSION_COOKIE} from '@/lib/portalAuth';import {portalSecurityApi} from '@/lib/portalSecurityApi';import {emailSecurityApi} from '@/lib/emailSecurityApi';import {securityMailSettings,sendSecurityMail} from '@/lib/securityMail';import {createPortalBackup,decryptPortalBackup} from '@/lib/portalRecovery';

let dir:string;const old='FictionalCurrent-647',next='FictionalReplacement-647',salt=Buffer.from('ab'.repeat(16),'hex'),encoded='scrypt$32768$8$3$'+salt.toString('hex')+'$'+scryptSync(old,salt,64,{N:32768,r:8,p:3,maxmem:64*1024*1024}).toString('hex');

beforeEach(async()=>{dir=await mkdtemp(path.join(os.tmpdir(),'dpd-security-'));vi.stubEnv('DUBAI_PORTAL_DATA_DIR',dir);vi.stubEnv('DUBAI_PORTAL_ADMIN_EMAIL','owner@example.com');vi.stubEnv('DUBAI_PORTAL_PASSWORD_HASH',encoded);});afterEach(async()=>{vi.unstubAllEnvs();vi.unstubAllGlobals();vi.restoreAllMocks();expect(path.basename(dir)).toMatch(/^dpd-security-/);await rm(dir,{recursive:true,force:true});});

const signup=(email='agent@example.com')=>memberSignup({name:'Fictional Member',email,password:old,company:'QA only',role:'agent',interest:'Dubai',consent:true});

const request=(method='GET',body?:unknown,cookie='',origin='http://localhost:3000')=>new Request('http://localhost:3000/api/portal-auth/security/sessions',{method,headers:{Origin:origin,Cookie:cookie,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});



const mailConfig={from:'owner@example.com',clientId:'fictional-client-id',clientSecret:'fictional-client-secret',refreshToken:'fictional-refresh-token',origin:'http://localhost:3000'};

async function ticket(purpose:'verify'|'reset',email='agent@example.com',session?:string,now=Date.now()){const v=await prepareMemberEmail(purpose,email,session,now);expect(v).not.toBeNull();await finishMemberEmail(v!.digest,true,now);return v!;}

it('stores token digests only and requires a successful delivery checkpoint',async()=>{const a=await signup(),v=await prepareMemberEmail('verify','',a.token);expect(v).not.toBeNull();const raw=await readFile(path.join(dir,'members.json'),'utf8');expect(raw).not.toContain(v!.secret);await expect(verifyMemberEmail(v!.secret)).rejects.toThrow('EMAIL_INVALID');await finishMemberEmail(v!.digest,true);expect(await verifyMemberEmail(v!.secret)).toEqual({verified:true});expect((await memberEmailStatus(a.token)).verifiedAt).toBeTypeOf('number');await expect(verifyMemberEmail(v!.secret)).rejects.toThrow('EMAIL_INVALID');});

it('verification links cannot reset a password and reset links cannot verify directly',async()=>{const a=await signup(),v=await ticket('verify','',a.token,Date.now()-61000),reset=await ticket('reset');await expect(resetMemberPassword(v.secret,next,next)).rejects.toThrow('EMAIL_INVALID');await expect(verifyMemberEmail(reset.secret)).rejects.toThrow('EMAIL_INVALID');});

it('resets once, revokes all sessions, proves email ownership and requires sign-in',async()=>{const a=await signup();await memberSignIn(a.member.email,old);const v=await ticket('reset');expect(await resetMemberPassword(v.secret,next,next)).toEqual({reset:true});expect(await memberSession(a.token)).toBeNull();expect(await memberSignIn(a.member.email,old)).toBeNull();expect(await memberSignIn(a.member.email,next)).not.toBeNull();await expect(resetMemberPassword(v.secret,old,old)).rejects.toThrow('EMAIL_INVALID');const raw=JSON.parse(await readFile(path.join(dir,'members.json'),'utf8'));expect(raw.emailLinks).toEqual([]);expect(raw.members[0].emailVerifiedAt).toBeTypeOf('number');expect(raw.securityEvents[0].action).toBe('password_reset');});

it('rejects expired reset links and never changes the password',async()=>{const a=await signup(),v=await ticket('reset','agent@example.com',undefined,Date.now()-16*60000);await expect(resetMemberPassword(v.secret,next,next)).rejects.toThrow('EMAIL_INVALID');expect(await memberSignIn(a.member.email,old)).not.toBeNull();});

it('rejects expired verification links',async()=>{const a=await signup(),v=await ticket('verify','',a.token,Date.now()-25*3600000);await expect(verifyMemberEmail(v.secret)).rejects.toThrow('EMAIL_INVALID');});

it('suspension invalidates all email links and recovery cannot reactivate an account',async()=>{const a=await signup(),v=await ticket('reset');await adminSetMemberAccess(a.member.id,true,0,'Access investigation');await expect(resetMemberPassword(v.secret,next,next)).rejects.toThrow('EMAIL_INVALID');expect(await prepareMemberEmail('reset',a.member.email)).toBeNull();expect(await memberSignIn(a.member.email,old)).toBeNull();});

it('authenticated password changes invalidate outstanding links',async()=>{const a=await signup(),v=await ticket('reset');await memberChangePassword(a.token,old,next);await expect(resetMemberPassword(v.secret,old,old)).rejects.toThrow('EMAIL_INVALID');});

it('reissuing invalidates the old link and cooldown limits repeats',async()=>{await signup();const now=Date.now(),a=await ticket('reset','agent@example.com',undefined,now);expect(await prepareMemberEmail('reset','agent@example.com',undefined,now+1000)).toBeNull();const b=await ticket('reset','agent@example.com',undefined,now+61000);await expect(resetMemberPassword(a.secret,next,next)).rejects.toThrow('EMAIL_INVALID');expect(b.secret).not.toBe(a.secret);});

it('unknown and owner emails do not create recoverable accounts or links',async()=>{await signup();expect(await prepareMemberEmail('reset','unknown@example.com')).toBeNull();expect(await prepareMemberEmail('reset','owner@example.com')).toBeNull();vi.stubEnv('DUBAI_PORTAL_ADMIN_EMAIL','agent@example.com');expect(await prepareMemberEmail('reset','agent@example.com')).toBeNull();const raw=JSON.parse(await readFile(path.join(dir,'members.json'),'utf8'));expect(raw.emailLinks).toHaveLength(0);expect(raw.members).toHaveLength(1);});

it('isolates verification to the requesting member',async()=>{const a=await signup(),b=await signup('second@example.com'),v=await ticket('verify',b.member.email,a.token);expect(v.email).toBe(a.member.email);await verifyMemberEmail(v.secret);expect((await memberEmailStatus(a.token)).verifiedAt).not.toBeNull();expect((await memberEmailStatus(b.token)).verifiedAt).toBeNull();});

it('only one concurrent reset succeeds',async()=>{await signup();const v=await ticket('reset'),res=await Promise.allSettled([resetMemberPassword(v.secret,next,next),resetMemberPassword(v.secret,next,next)]);expect(res.filter(v=>v.status==='fulfilled')).toHaveLength(1);});

it('failed delivery invalidates a link without leaking its contents',async()=>{await signup();const v=await prepareMemberEmail('reset','agent@example.com');await finishMemberEmail(v!.digest,false);await expect(resetMemberPassword(v!.secret,next,next)).rejects.toThrow('EMAIL_INVALID');expect(await readFile(path.join(dir,'members.json'),'utf8')).not.toContain(v!.secret);});

it('excludes links, attempts and delivery metadata from backups but retains verification',async()=>{const a=await signup(),v=await ticket('verify','',a.token,Date.now()-61000);await verifyMemberEmail(v.secret);await ticket('reset');const archive=await decryptPortalBackup(await createPortalBackup('Fictional-backup-passphrase'),'Fictional-backup-passphrase');const raw=JSON.parse(archive.files.get('members.json')!.toString());expect(raw.emailLinks).toEqual([]);expect(raw.emailRequests).toEqual([]);expect(raw.emailConsumes).toEqual([]);expect(raw.mailLast).toBeUndefined();expect(raw.members[0].emailVerifiedAt).toBeTypeOf('number');});

it('rejects malformed persisted token metadata without resetting identities',async()=>{await signup();const file=path.join(dir,'members.json'),raw=JSON.parse(await readFile(file,'utf8'));raw.emailLinks=[{digest:'raw-secret'}];await writeFile(file,JSON.stringify(raw));await expect(prepareMemberEmail('reset','agent@example.com')).rejects.toThrow('MEMBER_STORE_INVALID');});

it('requires same-origin, authentication for status and verification requests, and strict payloads',async()=>{expect((await emailSecurityApi(request(),'status')).status).toBe(401);expect((await emailSecurityApi(request('POST',{}),'requestVerify')).status).toBe(401);expect((await emailSecurityApi(request('POST',{},'','https://other.example'),'requestReset')).status).toBe(403);expect((await emailSecurityApi(request('POST',{email:'a@example.com',token:'extra'}),'requestReset')).status).toBe(400);});

it('shows disconnected status without claiming delivery and fails requests safely until configured',async()=>{vi.stubEnv('DUBAI_SECURITY_MAIL_SETTINGS','');const owner=await ownerSignIn('owner@example.com',old),r=await emailSecurityApi(request('GET',undefined,SESSION_COOKIE+'='+owner!.token),'status');expect(await r.json()).toMatchObject({configured:false,sender:'owner@example.com'});expect((await emailSecurityApi(request('POST',{email:'agent@example.com'}),'requestReset')).status).toBe(503);});

it('does not return mail credentials in Admin status',async()=>{vi.stubEnv('DUBAI_SECURITY_MAIL_SETTINGS',JSON.stringify(mailConfig));const owner=await ownerSignIn('owner@example.com',old),r=await emailSecurityApi(request('GET',undefined,SESSION_COOKIE+'='+owner!.token),'status');const data=JSON.stringify(await r.json());expect(data).not.toContain(mailConfig.clientSecret);expect(data).not.toContain(mailConfig.refreshToken);expect(data).toContain('"configured":true');});

it('validates the fixed sender and trusted origin rather than request Host',()=>{vi.stubEnv('DUBAI_SECURITY_MAIL_SETTINGS',JSON.stringify(mailConfig));expect(securityMailSettings()).toEqual(mailConfig);for(const origin of ['http://external.example','https://example.com/path','https://user:password@example.com','https://example.com/']){vi.stubEnv('DUBAI_SECURITY_MAIL_SETTINGS',JSON.stringify({...mailConfig,origin}));expect(()=>securityMailSettings()).toThrow('EMAIL_CONFIG');}});

it('sends bounded MIME through Gmail only with a fragment token and checks receipt',async()=>{const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({access_token:'fictional-access-token'}))).mockResolvedValueOnce(new Response(JSON.stringify({id:'fictional-message-id'})));vi.stubGlobal('fetch',fetch);const token='a'.repeat(43);expect(await sendSecurityMail(mailConfig,'member@example.com','reset',token)).toBe(true);expect(fetch.mock.calls.map(c=>c[0])).toEqual(['https://oauth2.googleapis.com/token','https://gmail.googleapis.com/gmail/v1/users/me/messages/send']);const mime=Buffer.from(JSON.parse(fetch.mock.calls[1][1].body).raw,'base64url').toString();expect(mime).toContain('To: member@example.com\r\n');const body=Buffer.from(mime.split('\r\n\r\n')[1],'base64').toString();expect(body).toContain('/reset-password#token='+token);expect(body).not.toContain('?token=');expect(fetch.mock.calls[1][1].redirect).toBe('error');});

it('redacts provider errors and never automatically retries sends',async()=>{const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({access_token:'fictional-access-token'}))).mockResolvedValueOnce(new Response('private-provider-error',{status:403}));vi.stubGlobal('fetch',fetch);await expect(sendSecurityMail(mailConfig,'member@example.com','verify','a'.repeat(43))).rejects.toThrow('EMAIL_DELIVERY');expect(fetch).toHaveBeenCalledTimes(2);});



it('completes a requested email reset end-to-end without exposing tokens or account existence',async()=>{const a=await signup();vi.stubEnv('DUBAI_SECURITY_MAIL_SETTINGS',JSON.stringify(mailConfig));const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({access_token:'fictional-access-token'}))).mockResolvedValueOnce(new Response(JSON.stringify({id:'fictional-email-id'})));vi.stubGlobal('fetch',fetch);

 const issued=await emailSecurityApi(request('POST',{email:a.member.email}),'requestReset');expect(issued.status).toBe(200);const shown=await issued.json();

 const mime=Buffer.from(JSON.parse(fetch.mock.calls[1][1].body).raw,'base64url').toString(),message=Buffer.from(mime.split('\r\n\r\n')[1],'base64').toString(),token=message.match(/#token=([A-Za-z0-9_-]{43})/)![1];expect(JSON.stringify(shown)).not.toContain(token);

 const unknown=await emailSecurityApi(request('POST',{email:'unknown@example.com'}),'requestReset');expect(unknown.status).toBe(200);expect(await unknown.json()).toEqual(shown);expect(fetch).toHaveBeenCalledTimes(2);

 const reset=await emailSecurityApi(request('POST',{token,password:next,confirmation:next}),'reset');expect(await reset.json()).toEqual({reset:true});expect(reset.headers.get('set-cookie')).toBeNull();expect(await memberSession(a.token)).toBeNull();expect(await memberSignIn(a.member.email,next)).not.toBeNull();expect((await emailSecurityApi(request('POST',{token,password:old,confirmation:old}),'reset')).status).toBe(400);

},30000);

