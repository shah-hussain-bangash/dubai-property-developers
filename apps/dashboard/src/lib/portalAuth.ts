/** Node-only local owner sessions. Never import into a client component. */
import {randomBytes,scrypt as derive,timingSafeEqual,createHash} from 'node:crypto';
import {mkdir,open,readFile,rename,stat,unlink} from 'node:fs/promises';
import path from 'node:path';
export const SESSION_COOKIE='dubai_portal_session';
export const SESSION_SECONDS=8*60*60;
type Session={digest:string;expires:number;account:string};
type Store={version:1;attempts:number[];sessions:Session[]};
const hash=(value:string)=>createHash('sha256').update(value).digest('hex');
function config(){
  const email=(process.env.DUBAI_PORTAL_ADMIN_EMAIL||'').trim().toLowerCase();
  const encoded=process.env.DUBAI_PORTAL_PASSWORD_HASH||'';
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>254||!/^scrypt\$32768\$8\$3\$[a-f0-9]{32}\$[a-f0-9]{128}$/.test(encoded))throw new Error('PORTAL_NOT_CONFIGURED');
  return {email,encoded,account:hash(email+'|'+encoded)};
}
const blank=():Store=>({version:1,attempts:[],sessions:[]});
async function storage<T>(action:(store:Store)=>Promise<T>|T,write=true):Promise<T>{
  const directory=process.env.DUBAI_PORTAL_DATA_DIR||'/app/portal-data';
  await mkdir(directory,{recursive:true,mode:0o700});
  const lock=path.join(directory,'sessions.lock');let handle;
  for(let attempt=0;attempt<80;attempt++){
    try{handle=await open(lock,'wx',0o600);break;}
    catch(e){if((e as NodeJS.ErrnoException).code!=='EEXIST')throw new Error('SESSION_STORE_UNAVAILABLE');
      // A crashed writer cannot hold the file lock indefinitely.
      try{if(Date.now()-(await stat(lock)).mtimeMs>60000)await unlink(lock);}catch{}
      await new Promise(resolve=>setTimeout(resolve,25));}
  }
  if(!handle)throw new Error('SESSION_STORE_BUSY');
  const file=path.join(directory,'sessions.json');
  try{
    let store:Store;
    try{const raw=await readFile(file,'utf8');if(raw.length>200000)throw new Error();store=JSON.parse(raw) as Store;
      if(store.version!==1||!Array.isArray(store.sessions)||store.sessions.length>50||!Array.isArray(store.attempts)||store.attempts.length>100)throw new Error();
      if(!store.sessions.every(row=>row&&/^[a-f0-9]{64}$/.test(row.digest)&&/^[a-f0-9]{64}$/.test(row.account)&&Number.isFinite(row.expires))||!store.attempts.every(value=>Number.isFinite(value)))throw new Error();
    }catch(e){if((e as NodeJS.ErrnoException).code==='ENOENT')store=blank();else throw new Error('SESSION_STORE_INVALID');}
    const value=await action(store);
    if(write){const temporary=file+'.'+randomBytes(8).toString('hex')+'.tmp';await (await open(temporary,'wx',0o600)).close();
      try{const writer=await open(temporary,'w',0o600);try{await writer.writeFile(JSON.stringify(store),'utf8');await writer.sync();}finally{await writer.close();}await rename(temporary,file);}finally{await unlink(temporary).catch(()=>undefined);}}
    return value;
  }finally{await handle.close();await unlink(lock).catch(()=>undefined);}
}
export async function ownerSignIn(email:unknown,password:unknown,now=Date.now()):Promise<{token:string;email:string}|null>{
  const owner=config();if(typeof email!=='string'||typeof password!=='string'||email.length>254||password.length<1||password.length>128)return null;
  // Reserve attempts durably before the expensive derivation, including bad emails.
  const allowed=await storage(store=>{store.attempts=store.attempts.filter(t=>now-t<15*60*1000);if(store.attempts.length>=10)return false;store.attempts.push(now);return true;});
  if(!allowed)throw new Error('SIGN_IN_LIMIT');
  const [, , , ,salt,expected]=owner.encoded.split('$');
  const actual=await new Promise<Buffer>((resolve,reject)=>derive(password,Buffer.from(salt,'hex'),64,{N:32768,r:8,p:3,maxmem:64*1024*1024},(error,result)=>error?reject(error):resolve(result)));
  const correct=timingSafeEqual(actual,Buffer.from(expected,'hex'))&&timingSafeEqual(Buffer.from(hash(email.trim().toLowerCase()),'hex'),Buffer.from(hash(owner.email),'hex'));
  if(!correct)return null;
  const token=randomBytes(32).toString('base64url');
  await storage(store=>{store.attempts=[];store.sessions=store.sessions.filter(row=>row.expires>now&&row.account===owner.account).slice(-49);store.sessions.push({digest:hash(token),account:owner.account,expires:now+SESSION_SECONDS*1000});});
  return {token,email:owner.email};
}
export async function ownerSession(token:string|undefined,now=Date.now()):Promise<{email:string}|null>{
  if(!token||!/^[A-Za-z0-9_-]{43}$/.test(token))return null;
  const owner=config();return storage(store=>store.sessions.some(row=>row.digest===hash(token)&&row.account===owner.account&&row.expires>now)?{email:owner.email}:null,false);
}
export async function ownerSignOut(token:string|undefined):Promise<void>{
  if(!token||!/^[A-Za-z0-9_-]{43}$/.test(token))return;
  await storage(store=>{store.sessions=store.sessions.filter(row=>row.digest!==hash(token));});
}
// Retain the existing export for all portal callers.
export {samePortalOrigin as sameLocalOrigin} from './portalOrigin';
export function readSessionCookie(request:Request):string|undefined{
  return request.headers.get('cookie')?.split(';').map(v=>v.trim()).find(v=>v.startsWith(SESSION_COOKIE+'='))?.slice(SESSION_COOKIE.length+1);
}
export function privateJson(value:unknown,status=200):Response{return Response.json(value,{status,headers:{'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'}});}

const ownerSessionReference=(value:string)=>hash('public-session-reference|'+value).slice(0,32);
function activeOwnerSession(store:Store,token:string|undefined,now:number){const owner=config();if(!token||!/^[A-Za-z0-9_-]{43}$/.test(token))throw new Error('SECURITY_AUTH');const row=store.sessions.find(v=>v.digest===hash(token)&&v.account===owner.account&&v.expires>now);if(!row)throw new Error('SECURITY_AUTH');return {owner,row};}
export async function ownerSecurityOverview(token:string|undefined,now=Date.now()){return storage(store=>{const {owner,row}=activeOwnerSession(store,token,now);return {kind:'admin' as const,sessions:store.sessions.filter(v=>v.account===owner.account&&v.expires>now).map(v=>({id:ownerSessionReference(v.digest),current:v.digest===row.digest,createdAt:v.expires-SESSION_SECONDS*1000,expiresAt:v.expires})),events:[]};},false);}
export async function ownerRevokeSessions(token:string|undefined,mode:unknown,id:unknown,now=Date.now()){if(!['one','others','all'].includes(String(mode))||mode==='one'&&(typeof id!=='string'||!/^[a-f0-9]{32}$/.test(id)))throw new Error('SECURITY_INPUT');return storage(store=>{const {owner,row}=activeOwnerSession(store,token,now);const remove=store.sessions.filter(v=>v.account===owner.account&&v.expires>now&&(mode==='all'||mode==='others'&&v.digest!==row.digest||mode==='one'&&ownerSessionReference(v.digest)===id));if(mode==='one'&&!remove.length)throw new Error('SECURITY_NOT_FOUND');const removed=new Set(remove.map(v=>v.digest));store.sessions=store.sessions.filter(v=>!removed.has(v.digest));return {revoked:remove.length,signedOut:removed.has(row.digest)};});}
export async function ownerReauthenticate(token:string|undefined,password:unknown,now=Date.now()){if(typeof password!=='string'||!password||password.length>128)throw new Error('PASSWORD_INCORRECT');const snapshot=await storage(store=>{const {owner}=activeOwnerSession(store,token,now);store.attempts=store.attempts.filter(v=>now-v<15*60000);if(store.attempts.length>=10)throw new Error('SECURITY_LIMIT');store.attempts.push(now);return owner;});const fields=snapshot.encoded.split('$');const actual=await new Promise<Buffer>((resolve,reject)=>derive(password,Buffer.from(fields[4],'hex'),64,{N:32768,r:8,p:3,maxmem:64*1024*1024},(error,value)=>error?reject(error):resolve(value)));if(!timingSafeEqual(actual,Buffer.from(fields[5],'hex')))throw new Error('PASSWORD_INCORRECT');return storage(store=>{const {owner}=activeOwnerSession(store,token,now);if(owner.account!==snapshot.account)throw new Error('SECURITY_AUTH');store.attempts=[];return true;});}
