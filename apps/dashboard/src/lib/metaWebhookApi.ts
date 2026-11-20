import {metaSettings,metaStatus,metaChallenge,verifyMetaSignature,parseMetaMessages} from './metaMessaging';
import {receiveMetaBatch,AgentError} from './agentPropertyStore';
import {OutreachError} from './outreachWorkflow';import {portalActor} from './agentPortalApi';import {privateJson} from './portalAuth';
export async function metaStatusApi(r:Request){try{const actor=await portalActor(r);if(actor.kind!=='admin')return privateJson({error:'Admin access is required.'},403);return privateJson(metaStatus());}catch{return privateJson({error:'Sign in as Admin.'},401);}}
export async function metaWebhookApi(r:Request){try{
 if(r.method==='GET')return new Response(metaChallenge(r),{status:200,headers:{'Content-Type':'text/plain','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
 const settings=metaSettings();if(!r.headers.get('content-type')?.startsWith('application/json'))throw new OutreachError('Use JSON.',415);const reader=r.body?.getReader();if(!reader)throw new OutreachError('Missing event body.');let size=0;const chunks:Uint8Array[]=[];
 while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>131072){await reader.cancel();throw new OutreachError('Meta event is too large.',413);}chunks.push(value);}const raw=Buffer.concat(chunks);verifyMetaSignature(raw,r.headers.get('x-hub-signature-256'),settings.appSecret);
 let payload:unknown;try{payload=JSON.parse(raw.toString('utf8'));}catch{throw new OutreachError('Invalid JSON.');}const result=await receiveMetaBatch(parseMetaMessages(payload));return privateJson({accepted:true,...result});
 }catch(e){return privateJson({error:e instanceof AgentError||e instanceof OutreachError?e.message:'Meta event processing is unavailable. Retry using the same provider message IDs.'},e instanceof AgentError||e instanceof OutreachError?e.status:503);}}
