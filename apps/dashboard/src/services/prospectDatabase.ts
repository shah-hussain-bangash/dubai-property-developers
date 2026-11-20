import { getApiBaseUrl, getApiCredentials } from '@/lib/config';
import { parseWorkspace, type ResearchWorkspace } from './prospectResearch';
export interface DatabaseWorkspace { revision:number; workspace:ResearchWorkspace }
export function parseDatabaseWorkspace(body:unknown):DatabaseWorkspace {
  const value=body as Record<string,unknown>;
  if(!value||value.storage!=='postgresql'||value.outreach_enabled!==false||!Number.isSafeInteger(value.revision)||Number(value.revision)<0) throw new Error('The PostgreSQL workspace response could not be verified.');
  return {revision:Number(value.revision),workspace:parseWorkspace(JSON.stringify(value.workspace))};
}
export async function accessProspectDatabase(update?:DatabaseWorkspace,signal?:AbortSignal):Promise<DatabaseWorkspace> {
  const base=new URL(getApiBaseUrl());
  if(base.protocol!=='http:'||!['localhost','127.0.0.1','[::1]'].includes(base.hostname)||base.username||base.password||base.pathname!=='/'||base.search||base.hash) throw new Error('A local API is required for this development workspace.');
  const controller=new AbortController();const onAbort=()=>controller.abort();signal?.addEventListener('abort',onAbort,{once:true});if(signal?.aborted)controller.abort();
  const timeout=setTimeout(()=>controller.abort(),20000);
  try {
    const response=await fetch(base.origin+'/api/v1/prospect-research/workspace',{method:update?'PUT':'GET',body:update?JSON.stringify(update):undefined,headers:update?{'Content-Type':'application/json'}:undefined,credentials:getApiCredentials(),redirect:'error',cache:'no-store',signal:controller.signal});
    if(response.status===409)throw new Error('Another session changed this workspace. Reload before editing. Your browser backup remains available.');
    if(!response.ok)throw new Error('PostgreSQL storage is unavailable or the workspace could not be saved. Reload to check the saved state before retrying.');
    return parseDatabaseWorkspace(await response.json());
  }finally {clearTimeout(timeout);signal?.removeEventListener('abort',onAbort);}
}
