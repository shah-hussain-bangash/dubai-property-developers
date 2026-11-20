import {NextResponse} from 'next/server';import {sameLocalOrigin} from './portalAuth';import {portalActor} from './agentPortalApi';import {memberCookie,memberEmailStatus,securityMailDeliveryStatus,prepareMemberEmail,finishMemberEmail,verifyMemberEmail,resetMemberPassword} from './portalMembers';import {securityMailSettings,sendSecurityMail} from './securityMail';
const response=(data:unknown,status=200)=>NextResponse.json(data,{status,headers:{'Cache-Control':'no-store, private','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}});
async function body(r:Request){if(!sameLocalOrigin(r))throw Error('EMAIL_ORIGIN');if(!r.headers.get('content-type')?.startsWith('application/json'))throw Error('EMAIL_INPUT');const reader=r.body?.getReader();if(!reader)throw Error('EMAIL_INPUT');let n=0;const chunks:Uint8Array[]=[];while(true){const {done,value}=await reader.read();if(done)break;n+=value.length;if(n>4096){await reader.cancel();throw Error('EMAIL_INPUT');}chunks.push(value);}try{const b=JSON.parse(Buffer.concat(chunks).toString('utf8'));if(!b||typeof b!=='object'||Array.isArray(b))throw Error();return b as Record<string,unknown>;}catch{throw Error('EMAIL_INPUT');}}
function only(b:Record<string,unknown>,keys:string[]){if(Object.keys(b).some(k=>!keys.includes(k)))throw Error('EMAIL_INPUT');}
export async function emailSecurityApi(r:Request,action:'status'|'requestReset'|'requestVerify'|'reset'|'verify'){
 try{if(action==='status'){const actor=await portalActor(r),c=securityMailSettings();return response({configured:!!c,sender:c?.from??'owner@example.com',localLinks:!!c&&c.origin.startsWith('http://'),...(actor.kind==='admin'?await securityMailDeliveryStatus():await memberEmailStatus(memberCookie(r)))});}
 const b=await body(r);
 if(action==='reset'){only(b,['token','password','confirmation']);return response(await resetMemberPassword(b.token,b.password,b.confirmation));}
 if(action==='verify'){only(b,['token']);return response(await verifyMemberEmail(b.token));}
 only(b,action==='requestReset'?['email']:[]);
 if(action==='requestReset'&&(typeof b.email!=='string'||b.email.length>254||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(b.email.trim())))throw Error('EMAIL_INPUT');
 if(action==='requestVerify'){const actor=await portalActor(r);if(actor.kind!=='member')throw Error('EMAIL_MEMBER');}
 const c=securityMailSettings();if(!c)throw Error('EMAIL_DISABLED');
 const started=Date.now();let limited=false;
 try{const ticket=await prepareMemberEmail(action==='requestReset'?'reset':'verify',b.email,memberCookie(r));if(ticket){let accepted=false;try{accepted=await sendSecurityMail(c,ticket.email,ticket.purpose,ticket.secret);}catch{}await finishMemberEmail(ticket.digest,accepted);}}
 catch(e){if((e as Error).message==='EMAIL_LIMIT')limited=true;else throw e;}
 finally{if(action==='requestReset')await new Promise(resolve=>setTimeout(resolve,Math.max(0,9000-(Date.now()-started))));}
 if(limited)throw Error('EMAIL_LIMIT');
 return response({message:action==='requestReset'?'If an eligible member account exists, a reset link will be emailed. Check your inbox and spam folder.':'If verification is needed and delivery is available, a link will be emailed. Check your inbox and spam folder.'});
 }catch(e){const code=(e as Error).message;const errors:Record<string,[number,string]>={EMAIL_ORIGIN:[403,'Request origin is not allowed.'],EMAIL_INPUT:[400,'Check the request fields.'],EMAIL_INVALID:[400,'This link is invalid, expired or already used. Request a new link.'],EMAIL_LIMIT:[429,'Too many requests. Try again in 15 minutes.'],EMAIL_DISABLED:[503,'Security email delivery is not configured. Contact Admin.'],EMAIL_CONFIG:[503,'Security email delivery is unavailable. Contact Admin.'],EMAIL_MEMBER:[403,'Use your member account to verify its email.'],SECURITY_AUTH:[401,'Sign in again.'],PASSWORD_INPUT:[400,'Use matching passwords of 12 to 128 characters.']};const match=errors[code];return response({error:match?.[1]??'Account recovery is temporarily unavailable.'},match?.[0]??((e as {status?:number}).status===401?401:503));}
}
