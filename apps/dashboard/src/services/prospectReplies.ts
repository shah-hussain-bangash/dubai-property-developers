import { getApiBaseUrl, getApiCredentials } from '@/lib/config';

export interface CallbackTask {id:string;prospect_id:string;owner_id:string;status:'needs_review'|'completed'|'cancelled';calling_permission:'unknown';created_at:string;updated_at:string;completion_note:string}
export interface ReplyPreview {id:string;prospect_id:string;channel:'email'|'whatsapp';kind:ReplyKind;received_at:string;text:string}
export type ReplyKind='reply'|'opt_out'|'auto_reply'|'bounce';
export interface ReplySnapshot {revision:number;actor_id:string;reply_count:number;notification_count:number;pending_count:number;suppressed_prospect_ids:string[];tasks:CallbackTask[];recent_replies:ReplyPreview[]}
export interface ManualReplyDraft {prospect_id:string;event_id:string;channel:'email'|'whatsapp';kind:ReplyKind;received_at:string;text:string;confirmed:boolean}
const id=(value:unknown):value is string=>typeof value==='string'&&/^[a-zA-Z0-9-]{1,100}$/.test(value);
const key=(value:unknown):value is string=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
const integer=(value:unknown,maximum:number)=>Number.isInteger(value)&&Number(value)>=0&&Number(value)<=maximum;
const date=(value:unknown)=>typeof value==='string'&&Number.isFinite(Date.parse(value))&&/(Z|[+-]\d\d:\d\d)$/.test(value);

function parse(value:Record<string,unknown>):ReplySnapshot {
  if(value.storage!=='postgresql'||value.outreach_enabled!==false||value.inbox_connected!==false||value.notifications_delivered!==false)throw new Error('Reply storage provenance could not be verified.');
  if(!integer(value.revision,2_000_000_000)||!id(value.actor_id)||!integer(value.reply_count,2000)||!integer(value.notification_count,2000)||!integer(value.pending_count,2000))throw new Error('Invalid reply counts.');
  const tasks=value.tasks as CallbackTask[];const replies=value.recent_replies as ReplyPreview[];const suppressed=value.suppressed_prospect_ids;
  if(!Array.isArray(tasks)||tasks.length>2000||!Array.isArray(replies)||replies.length!==Math.min(Number(value.reply_count),50)||!Array.isArray(suppressed)||suppressed.length>500||!suppressed.every(id)||new Set(suppressed).size!==suppressed.length)throw new Error('Invalid reply workspace.');
  for(const row of tasks){if(!row||!key(row.id)||!id(row.prospect_id)||!id(row.owner_id)||!['needs_review','completed','cancelled'].includes(row.status)||row.calling_permission!=='unknown'||!date(row.created_at)||!date(row.updated_at)||typeof row.completion_note!=='string'||row.completion_note.length>500)throw new Error('Invalid callback task.');}
  for(const row of replies){if(!row||!key(row.id)||!id(row.prospect_id)||!['email','whatsapp'].includes(row.channel)||!['reply','opt_out','auto_reply','bounce'].includes(row.kind)||!date(row.received_at)||typeof row.text!=='string'||row.text.length>500)throw new Error('Invalid reply preview.');}
  if(new Set(tasks.map(t=>t.id)).size!==tasks.length||new Set(replies.map(r=>r.id)).size!==replies.length||tasks.filter(t=>t.status==='needs_review').length!==value.pending_count)throw new Error('Inconsistent callback tasks.');
  return value as unknown as ReplySnapshot;
}

export async function prospectReplies(operation:'read'|'record'|'close'='read',body?:({revision:number}&ManualReplyDraft)|{revision:number;task_id:string;status:'completed'|'cancelled';note:string}):Promise<ReplySnapshot>{
  const base=new URL(getApiBaseUrl());
  if(base.protocol!=='http:'||!['localhost','127.0.0.1','[::1]'].includes(base.hostname)||base.username||base.password||base.pathname!=='/'||base.search||base.hash)throw new Error('A local API is required.');
  if(operation!=='read'&&(!body||!integer(body.revision,2_000_000_000)))throw new Error('Load replies before saving.');
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),20000);
  try{
    const response=await fetch(base.origin+'/api/v1/prospect-research/replies'+(operation==='close'?'/close-task':''),{method:operation==='read'?'GET':'POST',headers:operation==='read'?undefined:{'Content-Type':'application/json'},body:operation==='read'?undefined:JSON.stringify(body),credentials:getApiCredentials(),cache:'no-store',redirect:'error',signal:controller.signal});
    if(!response.ok)throw new Error(response.status===409?'Replies changed. Keep your draft and reload replies before another action.':'Reply action could not be confirmed. Keep your draft and reload replies before another action.');
    const raw=await response.text();if(raw.length>4_000_000)throw new Error('Reply response is too large.');
    return parse(JSON.parse(raw));
  }finally{clearTimeout(timeout);}
}
