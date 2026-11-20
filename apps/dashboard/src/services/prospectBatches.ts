import { getApiBaseUrl, getApiCredentials } from '@/lib/config';
import type { DiscoveryCandidate,DiscoveryScope } from './prospectDiscovery';
export type BatchStatus='ready'|'paused'|'quota_wait'|'request_uncertain'|'completed'|'queries_exhausted'|'cancelled'|'error';
export interface BatchSummary {id:string;target:number;status:BatchStatus;cursor:number;provider_attempts:number;resume_at:string|null;notice:string;revision:number;count:number;query_count:number}
export interface SavedBatch {revision:number;state:{id:string;target:number;status:BatchStatus;cursor:number;provider_attempts:number;resume_at:string|null;notice:string;queries:{query:string;role:string;scope:DiscoveryScope}[];candidates:(DiscoveryCandidate&{search_query:string;query_role:string;discovered_at:string})[]}}
export type BatchAction='advance'|'pause'|'resume'|'cancel'|'skip_uncertain';
const statuses=['ready','paused','quota_wait','request_uncertain','completed','queries_exhausted','cancelled','error'];
const integer=(n:unknown,min:number,max:number)=>Number.isSafeInteger(n)&&Number(n)>=min&&Number(n)<=max;
function validSummary(row:BatchSummary){return row&&typeof row.id==='string'&&/^[a-zA-Z0-9-]{1,80}$/.test(row.id)&&statuses.includes(row.status)&&integer(row.target,1,500)&&integer(row.count,0,row.target)&&integer(row.cursor,0,100)&&integer(row.query_count,1,100)&&row.cursor<=row.query_count&&integer(row.provider_attempts,0,row.cursor)&&integer(row.revision,1,1000000)&&typeof row.notice==='string'&&row.notice.length<=250&&(row.resume_at===null||typeof row.resume_at==='string'&&Number.isFinite(Date.parse(row.resume_at)));}
function parseBatch(value:unknown):SavedBatch{
  const saved=value as SavedBatch;const state=saved?.state;
  if(!state||!Array.isArray(state.candidates)||!Array.isArray(state.queries)||!validSummary({...state,revision:saved.revision,count:state.candidates.length,query_count:state.queries.length}))throw new Error('Invalid saved batch response.');
  if(!state.queries.every(q=>q&&typeof q.query==='string'&&q.query.length>=3&&q.query.length<=300&&['ceo','director','entrepreneur','investor','agent','business_owner'].includes(q.role)&&['web','linkedin','facebook','instagram'].includes(q.scope)))throw new Error('Invalid saved query plan.');
  const ids=new Set<string>();
  for(const row of state.candidates){
    if(!row||typeof row.id!=='string'||!/^[a-f0-9]{24}$/.test(row.id)||ids.has(row.id)||typeof row.title!=='string'||!row.title||row.title.length>200||typeof row.snippet!=='string'||row.snippet.length>1000||typeof row.url!=='string'||row.url.length>1500||!Number.isFinite(Date.parse(row.discovered_at)))throw new Error('Invalid saved source candidate.');
    const url=new URL(row.url);if(url.protocol!=='https:'||url.username||url.password||!url.hostname.includes('.'))throw new Error('Invalid saved public source.');ids.add(row.id);
  }
  return saved;
}
export async function researchBatches(operation:'list'|'read'|'create'|BatchAction='list',options:{id?:string;revision?:number;location?:string;scope?:DiscoveryScope;target?:number}={}):Promise<BatchSummary[]|SavedBatch>{
  const base=new URL(getApiBaseUrl());if(base.protocol!=='http:'||!['localhost','127.0.0.1','[::1]'].includes(base.hostname)||base.username||base.password||base.pathname!=='/'||base.search||base.hash)throw new Error('A local API is required.');
  if(!['list','create'].includes(operation)&&(!options.id||!/^[a-zA-Z0-9-]{1,80}$/.test(options.id)))throw new Error('Load a saved batch first.');
  const mutating=!['list','read'].includes(operation);
  const action=mutating&&operation!=='create';
  if(action&&!integer(options.revision,1,1000000))throw new Error('Reload the saved batch before acting.');
  const path=operation==='list'||operation==='create'?'':`/${options.id}${action?'/actions':''}`;
  const body=operation==='create'?{location:options.location,scope:options.scope,target:options.target}:action?{action:operation,revision:options.revision}:undefined;
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),90000);
  try{
    const response=await fetch(base.origin+'/api/v1/prospect-research/batches'+path,{method:mutating?'POST':'GET',body:body?JSON.stringify(body):undefined,headers:body?{'Content-Type':'application/json'}:undefined,credentials:getApiCredentials(),cache:'no-store',redirect:'error',signal:controller.signal});
    if(response.status===409)throw new Error('Batch busy, changed or capacity reached. Reload saved state; do not retry automatically.');
    if(!response.ok)throw new Error('Batch operation could not be confirmed. Reload saved state before another action.');
    const raw=await response.text();if(raw.length>5000000)throw new Error('Batch response too large.');
    const value=JSON.parse(raw);if(value.storage!=='postgresql'||value.outreach_enabled!==false||value.scheduled!==false)throw new Error('Batch provenance could not be verified.');
    if(operation==='list'){if(!Array.isArray(value.batches)||value.batches.length>20||!value.batches.every(validSummary))throw new Error('Invalid batch list.');return value.batches;}
    const saved=parseBatch(value.batch);if(options.id&&saved.state.id!==options.id)throw new Error('Saved batch identity changed.');return saved;
  }finally{clearTimeout(timeout);}
}
