/** Fixed Gmail endpoints. No arbitrary provider URL or caller-supplied sender. */

export type SecurityMailSettings={from:string;clientId:string;clientSecret:string;refreshToken:string;origin:string};

export function securityMailSettings():SecurityMailSettings|null{

 const raw=process.env.DUBAI_SECURITY_MAIL_SETTINGS;if(!raw)return null;

 try{const c=JSON.parse(raw);if(Object.keys(c).sort().join(',')!=='clientId,clientSecret,from,origin,refreshToken'||c.from!=='owner@example.com'||![c.clientId,c.clientSecret,c.refreshToken].every(v=>typeof v==='string'&&v.length>=10&&v.length<=4096&&!/\s/.test(v)))throw Error();

 const u=new URL(c.origin);if(u.origin!==c.origin||u.username||u.password||u.protocol!=='https:'&&!(u.origin==='http://localhost:3000'||u.origin==='http://127.0.0.1:3000'))throw Error();return c;

 }catch{throw Error('EMAIL_CONFIG');}

}

async function jsonResponse(r:Response){if(!r.ok)throw Error('EMAIL_DELIVERY');const reader=r.body?.getReader();if(!reader)throw Error('EMAIL_DELIVERY');let size=0;const chunks:Uint8Array[]=[];while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>16384){await reader.cancel();throw Error('EMAIL_DELIVERY');}chunks.push(value);}return JSON.parse(Buffer.concat(chunks).toString('utf8'));}

export async function sendSecurityMail(c:SecurityMailSettings,to:string,purpose:'verify'|'reset',secret:string){

 if(!/^[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+$/.test(to)||to.length>254||!/^[A-Za-z0-9_-]{43}$/.test(secret))throw Error('EMAIL_DELIVERY');

 try{const oauth=await jsonResponse(await fetch('https://oauth2.googleapis.com/token',{method:'POST',redirect:'error',cache:'no-store',signal:AbortSignal.timeout(3500),headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:c.clientId,client_secret:c.clientSecret,refresh_token:c.refreshToken,grant_type:'refresh_token'})}));

 if(typeof oauth.access_token!=='string'||oauth.access_token.length<10||oauth.access_token.length>4096||/\s/.test(oauth.access_token))throw Error();

 const link=c.origin+(purpose==='reset'?'/reset-password':'/verify-email')+'#token='+secret;

 const content=(purpose==='reset'?'Reset your member password':'Verify your member email')+'\r\n\r\nOpen this link in your browser, then confirm the action:\r\n'+link+'\r\n\r\n'+(purpose==='reset'?'This link expires in 15 minutes. A successful reset signs out all previous sessions.':'This link expires in 24 hours.')+'\r\nIf you did not request this, ignore this email. Never share this link.\r\nDubai Property Developers';

 const mime=['From: '+c.from,'To: '+to,'Subject: '+(purpose==='reset'?'Reset your Dubai Property Developers password':'Verify your Dubai Property Developers email'),'MIME-Version: 1.0','Content-Type: text/plain; charset=UTF-8','Content-Transfer-Encoding: base64','',''+Buffer.from(content).toString('base64')].join('\r\n');

 const sent=await jsonResponse(await fetch('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',{method:'POST',redirect:'error',cache:'no-store',signal:AbortSignal.timeout(3500),headers:{Authorization:'Bearer '+oauth.access_token,'Content-Type':'application/json'},body:JSON.stringify({raw:Buffer.from(mime).toString('base64url')})}));

 if(typeof sent.id!=='string'||!sent.id||sent.id.length>256)throw Error();return true;

 }catch{throw Error('EMAIL_DELIVERY');}

}

