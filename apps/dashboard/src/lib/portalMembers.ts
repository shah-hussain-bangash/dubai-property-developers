/** Separate local member identity. A member token never authorizes the owner gateway. */
import {randomBytes,scrypt,timingSafeEqual,createHash} from 'node:crypto';
import {mkdir,open,readFile,rename,stat,unlink} from 'node:fs/promises';import path from 'node:path';
export const MEMBER_COOKIE='dubai_member_session';
type Member={id:string;name:string;email:string;company:string;role:string;interest:string;encoded:string;created:number;emailVerifiedAt?:number;accessState?:{suspended:boolean;version:number;reason:string;changedAt:number}};
type EmailLink={digest:string;memberId:string;purpose:'verify'|'reset';expires:number;credential:string;ready:boolean};
type Session={digest:string;memberId:string;expires:number};type Store={version:1;emailLinks?:EmailLink[];emailRequests?:{key:string;at:number}[];emailConsumes?:number[];mailLast?:{at:number;accepted:boolean};members:Member[];sessions:Session[];signupAttempts:number[];loginAttempts:number[];securityAttempts?:{memberId:string;at:number}[];securityEvents?:{id:string;memberId:string;actor:string;action:string;at:number;count:number}[]};
type Profile=Omit<Member,'encoded'|'accessState'>;
const digest=(s:string)=>createHash('sha256').update(s).digest('hex');
const roles=['buyer','investor','developer','broker','agent'];
const validEmail=(s:string)=>s.length<=254&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
const clean=(s:unknown,max:number)=>typeof s==='string'&&s.trim().length<=max&&!/[\x00-\x1f\x7f]/.test(s)?s.trim():null;
const encodedPattern=/^scrypt\$32768\$8\$3\$[a-f0-9]{32}\$[a-f0-9]{128}$/;
const profile=({encoded,accessState,...rest}:Member):Profile=>rest;
async function store<T>(action:(s:Store)=>T|Promise<T>,write=true):Promise<T>{
 const directory=process.env.DUBAI_PORTAL_DATA_DIR||'/app/portal-data';await mkdir(directory,{recursive:true,mode:0o700});const lock=path.join(directory,'members.lock');let handle;
 for(let i=0;i<80;i++){try{handle=await open(lock,'wx',0o600);break;}catch(e){if((e as NodeJS.ErrnoException).code!=='EEXIST')throw new Error('MEMBER_STORE_UNAVAILABLE');try{if(Date.now()-(await stat(lock)).mtimeMs>60000)await unlink(lock);}catch{}await new Promise(r=>setTimeout(r,25));}}
 if(!handle)throw new Error('MEMBER_STORE_BUSY');
 const file=path.join(directory,'members.json');
 try{let s:Store;try{s=decodeMembers(await readFile(file,'utf8'));
 }catch(e){if((e as NodeJS.ErrnoException).code==='ENOENT')s={version:1,members:[],sessions:[],signupAttempts:[],loginAttempts:[]};else throw new Error('MEMBER_STORE_INVALID');}
 const result=await action(s);if(write){const temp=file+'.'+randomBytes(8).toString('hex')+'.tmp';const writer=await open(temp,'wx',0o600);try{await writer.writeFile(JSON.stringify(s),'utf8');await writer.sync();}finally{await writer.close();}try{await rename(temp,file);}finally{await unlink(temp).catch(()=>undefined);}}return result;
 }finally{await handle.close();await unlink(lock).catch(()=>undefined);}
}

function decodeMembers(raw:string):Store{if(raw.length>1500000)throw new Error();const s=JSON.parse(raw) as Store;
 if(s.version!==1||!Array.isArray(s.members)||s.members.length>200||!Array.isArray(s.sessions)||s.sessions.length>2000||!Array.isArray(s.signupAttempts)||s.signupAttempts.length>100||!Array.isArray(s.loginAttempts)||s.loginAttempts.length>100)throw new Error();
 if(!s.members.every(m=>m&&/^[a-f0-9]{32}$/.test(m.id)&&clean(m.name,100)&&typeof m.email==='string'&&validEmail(m.email)&&clean(m.company,120)!==null&&clean(m.interest,160)!==null&&roles.includes(m.role)&&encodedPattern.test(m.encoded)&&Number.isFinite(m.created)))throw new Error();
 if(!s.sessions.every(v=>v&&/^[a-f0-9]{64}$/.test(v.digest)&&/^[a-f0-9]{32}$/.test(v.memberId)&&Number.isFinite(v.expires))||!s.loginAttempts.every(Number.isFinite)||!s.signupAttempts.every(Number.isFinite))throw new Error();
 if(new Set(s.members.map(m=>m.id)).size!==s.members.length||new Set(s.members.map(m=>m.email)).size!==s.members.length)throw new Error();
 if(s.securityAttempts!==undefined&&(!Array.isArray(s.securityAttempts)||s.securityAttempts.length>2000||!s.securityAttempts.every(a=>/^[a-f0-9]{32}$/.test(a.memberId)&&Number.isFinite(a.at))))throw new Error();
 if(s.securityEvents!==undefined&&(!Array.isArray(s.securityEvents)||s.securityEvents.length>500||!s.securityEvents.every(e=>/^[a-f0-9]{32}$/.test(e.id)&&/^[a-f0-9]{32}$/.test(e.memberId)&&(e.actor==='admin'||/^[a-f0-9]{32}$/.test(e.actor))&&['password_changed','sessions_revoked','account_suspended','account_reactivated','email_verified','password_reset'].includes(e.action)&&Number.isFinite(e.at)&&Number.isSafeInteger(e.count)&&e.count>=0)))throw new Error();
 if(!s.members.every(m=>m.accessState===undefined||(m.accessState&&typeof m.accessState.suspended==='boolean'&&Number.isSafeInteger(m.accessState.version)&&m.accessState.version>=1&&clean(m.accessState.reason,300)&&Number.isFinite(m.accessState.changedAt))))throw new Error();
 if(!s.members.every(m=>m.emailVerifiedAt===undefined||Number.isFinite(m.emailVerifiedAt)&&m.emailVerifiedAt>=0))throw Error();
 if(s.emailLinks!==undefined&&(!Array.isArray(s.emailLinks)||s.emailLinks.length>400||!s.emailLinks.every(v=>v&&/^[a-f0-9]{64}$/.test(v.digest)&&/^[a-f0-9]{32}$/.test(v.memberId)&&['verify','reset'].includes(v.purpose)&&Number.isFinite(v.expires)&&/^[a-f0-9]{64}$/.test(v.credential)&&typeof v.ready==='boolean')))throw Error();
 if(s.emailRequests!==undefined&&(!Array.isArray(s.emailRequests)||s.emailRequests.length>100||!s.emailRequests.every(v=>v&&/^[a-f0-9]{64}$/.test(v.key)&&Number.isFinite(v.at))))throw Error();
 if(s.emailConsumes!==undefined&&(!Array.isArray(s.emailConsumes)||s.emailConsumes.length>100||!s.emailConsumes.every(Number.isFinite)))throw Error();
 if(s.mailLast!==undefined&&(!s.mailLast||!Number.isFinite(s.mailLast.at)||typeof s.mailLast.accepted!=='boolean'))throw Error();
 return s;}
export function validateMemberRecoveryState(raw:string){return {members:decodeMembers(raw).members.length};}
async function derive(password:string,salt:string){return new Promise<Buffer>((resolve,reject)=>scrypt(password,Buffer.from(salt,'hex'),64,{N:32768,r:8,p:3,maxmem:64*1024*1024},(err,value)=>err?reject(err):resolve(value)));}
async function attempt(kind:'signupAttempts'|'loginAttempts',now:number){const allowed=await store(s=>{s[kind]=s[kind].filter(t=>now-t<15*60000);if(s[kind].length>=10)return false;s[kind].push(now);return true;});if(!allowed)throw new Error('MEMBER_LIMIT');}
function session(s:Store,id:string,now:number){const token=randomBytes(32).toString('base64url');s.sessions=s.sessions.filter(v=>v.expires>now).slice(-1999);s.sessions.push({digest:digest(token),memberId:id,expires:now+8*3600000});return token;}
export async function memberSignup(input:Record<string,unknown>,now=Date.now()){
 const name=clean(input.name,100),company=clean(input.company??'',120),interest=clean(input.interest??'',160),email=clean(input.email,254)?.toLowerCase(),role=clean(input.role,30),password=input.password;
 if(!name||company===null||interest===null||!email||!validEmail(email)||!role||!roles.includes(role)||typeof password!=='string'||password.length<12||password.length>128||input.consent!==true)throw new Error('MEMBER_INPUT');
 const owner=(process.env.DUBAI_PORTAL_ADMIN_EMAIL||'').trim().toLowerCase();if(!owner)throw new Error('MEMBER_UNAVAILABLE');
 await attempt('signupAttempts',now);if(email===owner)throw new Error('MEMBER_EXISTS');
 const salt=randomBytes(16).toString('hex'),encoded='scrypt$32768$8$3$'+salt+'$'+(await derive(password,salt)).toString('hex');
 return store(s=>{if(s.members.some(m=>m.email===email))throw new Error('MEMBER_EXISTS');if(s.members.length>=200)throw new Error('MEMBER_CAPACITY');const member:Member={id:randomBytes(16).toString('hex'),name,email,company,role,interest,encoded,created:now};s.members.push(member);return {token:session(s,member.id,now),member:profile(member)};});
}
export async function memberSignIn(email:unknown,password:unknown,now=Date.now()){
 if(typeof email!=='string'||!validEmail(email.trim())||typeof password!=='string'||!password||password.length>128)return null;
 await attempt('loginAttempts',now);const normalized=email.trim().toLowerCase();const member=await store(s=>s.members.find(m=>m.email===normalized),false);
 // Derive a dummy key for unknown accounts to avoid a fast account-existence check.
 const encoded=member?.encoded||'scrypt$32768$8$3$'+'00'.repeat(16)+'$'+'00'.repeat(64);const fields=encoded.split('$');const actual=await derive(password,fields[4]);if(!timingSafeEqual(actual,Buffer.from(fields[5],'hex'))||!member)return null;
 return store(s=>{const current=s.members.find(m=>m.id===member.id&&m.encoded===member.encoded);if(!current||current.accessState?.suspended||(current.accessState?.version??0)!==(member.accessState?.version??0))return null;s.loginAttempts=[];return {token:session(s,member.id,now),member:profile(current)};});
}
export async function memberSession(token:string|undefined,now=Date.now()):Promise<Profile|null>{if(!token||!/^[A-Za-z0-9_-]{43}$/.test(token))return null;return store(s=>{const row=s.sessions.find(v=>v.digest===digest(token)&&v.expires>now);const member=row&&s.members.find(m=>m.id===row.memberId);return member&&!member.accessState?.suspended?profile(member):null;},false);}
export async function memberSignOut(token:string|undefined){if(!token||!/^[A-Za-z0-9_-]{43}$/.test(token))return;await store(s=>{s.sessions=s.sessions.filter(v=>v.digest!==digest(token));});}
export function memberCookie(request:Request){return request.headers.get('cookie')?.split(';').map(v=>v.trim()).find(v=>v.startsWith(MEMBER_COOKIE+'='))?.slice(MEMBER_COOKIE.length+1);}

/** Server-only directory, returned only by the authenticated Admin route. */
export async function listMemberProfiles(){return store(s=>s.members.map(profile),false);}

// Re-check the live session inside each locked security mutation.
function securitySession(s:Store,token:string|undefined,now:number){if(!token||!/^[A-Za-z0-9_-]{43}$/.test(token))throw new Error('SECURITY_AUTH');const row=s.sessions.find(v=>v.digest===digest(token)&&v.expires>now);const member=row&&s.members.find(m=>m.id===row.memberId);if(!row||!member||member.accessState?.suspended)throw new Error('SECURITY_AUTH');return {row,member};}
const sessionReference=(value:string)=>digest('public-session-reference|'+value).slice(0,32);
function securityEvent(s:Store,memberId:string,actor:string,action:string,count:number,now:number){s.securityEvents=[...(s.securityEvents||[]),{id:randomBytes(16).toString('hex'),memberId,actor,action,count,at:now}].slice(-500);}
export async function memberSecurityOverview(token:string|undefined,now=Date.now()){return store(s=>{const {row,member}=securitySession(s,token,now);return {kind:'member' as const,sessions:s.sessions.filter(v=>v.memberId===member.id&&v.expires>now).map(v=>({id:sessionReference(v.digest),current:v.digest===row.digest,createdAt:v.expires-8*3600000,expiresAt:v.expires})),events:(s.securityEvents||[]).filter(e=>e.memberId===member.id).slice(-10).reverse().map(({id,action,at,count,actor})=>({id,action,at,count,byAdmin:actor==='admin'}))};},false);}
export async function memberRevokeSessions(token:string|undefined,mode:unknown,id:unknown,now=Date.now()){if(!['one','others','all'].includes(String(mode))||mode==='one'&&(typeof id!=='string'||!/^[a-f0-9]{32}$/.test(id)))throw new Error('SECURITY_INPUT');return store(s=>{const {row,member}=securitySession(s,token,now);const remove=s.sessions.filter(v=>v.memberId===member.id&&v.expires>now&&(mode==='all'||mode==='others'&&v.digest!==row.digest||mode==='one'&&sessionReference(v.digest)===id));if(mode==='one'&&!remove.length)throw new Error('SECURITY_NOT_FOUND');const removed=new Set(remove.map(v=>v.digest));s.sessions=s.sessions.filter(v=>!removed.has(v.digest));securityEvent(s,member.id,member.id,'sessions_revoked',remove.length,now);return {revoked:remove.length,signedOut:removed.has(row.digest)};});}
export async function memberChangePassword(token:string|undefined,current:unknown,next:unknown,now=Date.now()){if(typeof current!=='string'||!current||current.length>128||typeof next!=='string'||next.length<12||next.length>128||current===next)throw new Error('PASSWORD_INPUT');const snapshot=await store(s=>{const {member}=securitySession(s,token,now);s.securityAttempts=(s.securityAttempts||[]).filter(a=>a.at>now-15*60000);if(s.securityAttempts.filter(a=>a.memberId===member.id).length>=5)throw new Error('SECURITY_LIMIT');s.securityAttempts.push({memberId:member.id,at:now});return {id:member.id,encoded:member.encoded};});const fields=snapshot.encoded.split('$');const actual=await derive(current,fields[4]);if(!timingSafeEqual(actual,Buffer.from(fields[5],'hex')))throw new Error('PASSWORD_INCORRECT');const salt=randomBytes(16).toString('hex'),encoded='scrypt$32768$8$3$'+salt+'$'+(await derive(next,salt)).toString('hex');return store(s=>{const {member}=securitySession(s,token,now);if(member.id!==snapshot.id||member.encoded!==snapshot.encoded)throw new Error('SECURITY_CONFLICT');const revoked=s.sessions.filter(v=>v.memberId===member.id&&v.expires>now).length;s.sessions=s.sessions.filter(v=>v.memberId!==member.id);member.encoded=encoded;s.emailLinks=(s.emailLinks||[]).filter(v=>v.memberId!==member.id);s.securityAttempts=(s.securityAttempts||[]).filter(a=>a.memberId!==member.id);securityEvent(s,member.id,member.id,'password_changed',revoked,now);return {token:session(s,member.id,now),revoked};});}
/** Called only after fresh owner reauthentication by the server security API. */
export async function adminRevokeMemberSessions(memberId:string,now=Date.now()){if(!/^[a-f0-9]{32}$/.test(memberId))throw new Error('SECURITY_NOT_FOUND');return store(s=>{if(!s.members.some(m=>m.id===memberId))throw new Error('SECURITY_NOT_FOUND');const revoked=s.sessions.filter(v=>v.memberId===memberId&&v.expires>now).length;s.sessions=s.sessions.filter(v=>v.memberId!==memberId);securityEvent(s,memberId,'admin','sessions_revoked',revoked,now);return {revoked};});}

export async function adminMemberSessionDirectory(now=Date.now()){return store(s=>s.members.map(m=>({id:m.id,name:m.name,email:m.email,suspended:m.accessState?.suspended??false,accessVersion:m.accessState?.version??0,accessReason:m.accessState?.reason??'',accessChangedAt:m.accessState?.changedAt??null,activeSessions:s.sessions.filter(v=>v.memberId===m.id&&v.expires>now).length})),false);}

/** Admin API must freshly reauthenticate the owner before this locked mutation. */
export async function adminSetMemberAccess(memberId:string,suspended:unknown,version:unknown,reason:unknown,now=Date.now()){
 const note=clean(reason,300);
 if(!/^[a-f0-9]{32}$/.test(memberId))throw Error('SECURITY_NOT_FOUND');
 if(typeof suspended!=='boolean'||!Number.isSafeInteger(version)||(version as number)<0||!note||note.length<5)throw Error('SECURITY_INPUT');
 return store(s=>{const member=s.members.find(m=>m.id===memberId);if(!member)throw Error('SECURITY_NOT_FOUND');
 if((member.accessState?.version??0)!==version)throw Error('SECURITY_CONFLICT');
 if((member.accessState?.suspended??false)===suspended)throw Error('SECURITY_CONFLICT');
 const revoked=s.sessions.filter(v=>v.memberId===memberId&&v.expires>now).length;
 s.sessions=s.sessions.filter(v=>v.memberId!==memberId);
 s.emailLinks=(s.emailLinks||[]).filter(v=>v.memberId!==memberId);
 member.accessState={suspended,version:(version as number)+1,reason:note,changedAt:now};
 securityEvent(s,memberId,'admin',suspended?'account_suspended':'account_reactivated',revoked,now);
 return {suspended,accessVersion:member.accessState.version,revoked};});
}

const emailCredential=(member:Member)=>digest(member.encoded+'|'+(member.accessState?.version??0));
/** Returns secrets only to the server-side delivery adapter, never a route response. */
export async function prepareMemberEmail(purpose:'reset'|'verify',email:unknown,token?:string,now=Date.now()){
 return store(s=>{const member=purpose==='verify'?securitySession(s,token,now).member:s.members.find(m=>typeof email==='string'&&m.email===email.trim().toLowerCase());
 const normalized=purpose==='verify'?member!.email:String(email||'').trim().toLowerCase(),key=digest('email-request|'+normalized);
 s.emailRequests=(s.emailRequests||[]).filter(v=>v.at>now-15*60000);
 if(s.emailRequests.length>=20)throw Error('EMAIL_LIMIT');
 const recent=s.emailRequests.filter(v=>v.key===key);if(recent.length>=3||recent.some(v=>v.at>now-60000))return null;
 s.emailRequests.push({key,at:now});
 s.emailLinks=(s.emailLinks||[]).filter(v=>v.expires>now);
 if(normalized===(process.env.DUBAI_PORTAL_ADMIN_EMAIL||'').trim().toLowerCase()||!member||member.accessState?.suspended||purpose==='verify'&&member.emailVerifiedAt!==undefined)return null;
 const secret=randomBytes(32).toString('base64url'),hash=digest(secret);
 s.emailLinks=s.emailLinks.filter(v=>v.memberId!==member.id||v.purpose!==purpose);
 s.emailLinks.push({digest:hash,memberId:member.id,purpose,expires:now+(purpose==='reset'?15*60000:24*3600000),credential:emailCredential(member),ready:false});
 return {secret,digest:hash,email:member.email,purpose};});
}
export async function finishMemberEmail(hash:string,accepted:boolean,now=Date.now()){await store(s=>{const v=(s.emailLinks||[]).find(v=>v.digest===hash);if(v){if(accepted)v.ready=true;else s.emailLinks=s.emailLinks!.filter(v=>v.digest!==hash);}s.mailLast={at:now,accepted};});}
function emailLink(s:Store,secret:unknown,purpose:'reset'|'verify',now:number){
 if(typeof secret!=='string'||!/^[A-Za-z0-9_-]{43}$/.test(secret))throw Error('EMAIL_INVALID');
 const link=(s.emailLinks||[]).find(v=>v.digest===digest(secret)&&v.ready&&v.purpose===purpose&&v.expires>now);
 const member=link&&s.members.find(m=>m.id===link.memberId&&!m.accessState?.suspended);
 if(!link||!member||link.credential!==emailCredential(member))throw Error('EMAIL_INVALID');return {link,member};
}
async function consumeAttempt(now:number){const allowed=await store(s=>{s.emailConsumes=(s.emailConsumes||[]).filter(v=>v>now-15*60000);if(s.emailConsumes.length>=30)return false;s.emailConsumes.push(now);return true;});if(!allowed)throw Error('EMAIL_LIMIT');}
export async function verifyMemberEmail(secret:unknown,now=Date.now()){await consumeAttempt(now);return store(s=>{const {link,member}=emailLink(s,secret,'verify',now);member.emailVerifiedAt=now;s.emailLinks=s.emailLinks!.filter(v=>v.digest!==link.digest);securityEvent(s,member.id,member.id,'email_verified',0,now);return {verified:true};});}
export async function resetMemberPassword(secret:unknown,password:unknown,confirmation:unknown,now=Date.now()){
 if(typeof password!=='string'||password.length<12||password.length>128||confirmation!==password)throw Error('PASSWORD_INPUT');await consumeAttempt(now);
 const snapshot=await store(s=>{const {member}=emailLink(s,secret,'reset',now);return emailCredential(member);},false);
 const salt=randomBytes(16).toString('hex'),encoded='scrypt$32768$8$3$'+salt+'$'+(await derive(password,salt)).toString('hex');
 return store(s=>{const {member}=emailLink(s,secret,'reset',Date.now());if(emailCredential(member)!==snapshot)throw Error('EMAIL_INVALID');
 const revoked=s.sessions.filter(v=>v.memberId===member.id&&v.expires>Date.now()).length;
 s.sessions=s.sessions.filter(v=>v.memberId!==member.id);s.emailLinks=s.emailLinks!.filter(v=>v.memberId!==member.id);
 member.encoded=encoded;member.emailVerifiedAt=Date.now();securityEvent(s,member.id,member.id,'password_reset',revoked,Date.now());return {reset:true};});
}
export async function memberEmailStatus(token?:string){return store(s=>{const {member}=securitySession(s,token,Date.now());return {email:member.email,verifiedAt:member.emailVerifiedAt??null};},false);}
export async function securityMailDeliveryStatus(){return store(s=>({lastAttempt:s.mailLast??null}),false);}
