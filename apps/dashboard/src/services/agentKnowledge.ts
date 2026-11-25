import {getApiBaseUrl,getApiCredentials} from '@/lib/config';

const NO_SOURCE_ANSWER="I could not find an answer in this agent's supplied sources. Add a relevant source or ask a more specific question.";

export type KnowledgeAgent={id:string;name:string;status:string};
export type AssignedSource={id:string;title:string;kind:string;uri:string|null;chars:number;created:string;review_by:string|null;customer_safe:number};
export type SourceAnswer={agent_id:string;answered:boolean;supplied_sources_only:true;method:'source-excerpts';sent:false;text:string;sources:{source_id:string;label:string;title:string;uri:string|null;page:number|null;excerpt:string}[]};
export async function knowledgeRequest<T>(path:string,init:RequestInit={},signal?:AbortSignal):Promise<T>{
 const response=await fetch(getApiBaseUrl().replace(/\/$/,'')+'/api/v1/knowledge/agents'+path,{...init,signal,credentials:getApiCredentials(),cache:'no-store',redirect:'error'});
 const data=await response.json().catch(()=>{throw Error('The knowledge service returned an unreadable response. Please try again.');});
 if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:data.error?.message||'Knowledge request could not finish. Try again.');
 return data as T;
}
export function parseSourceAnswer(value:SourceAnswer,agent:string):SourceAnswer{
 if(!value||typeof value!=='object')throw Error('The source answer could not be verified.');
 if(value.agent_id!==agent||value.supplied_sources_only!==true||value.method!=='source-excerpts'||value.sent!==false||typeof value.text!=='string'||!Array.isArray(value.sources)||value.sources.length>3||typeof value.answered!=='boolean'||value.answered!==(value.sources.length>0))throw Error('The source answer could not be verified.');
 if(!value.answered&&value.text!==NO_SOURCE_ANSWER)throw Error('The source answer could not be verified.');
 for(const [i,s] of value.sources.entries()){
  if(!s||typeof s!=='object')throw Error('A source reference is invalid.');
  // Match the upload contract: PDFs have 1-100 pages; other sources use null.
  const validPage=s.page===null||(Number.isInteger(s.page)&&s.page>=1&&s.page<=100);
  if(s.label!==String(i+1)||typeof s.excerpt!=='string'||!s.excerpt.trim()||typeof s.title!=='string'||!s.title.trim()||typeof s.source_id!=='string'||!s.source_id.trim()||!validPage)throw Error('A source reference is invalid.');
 }
 if(value.answered&&value.text!==value.sources.map((s,i)=>`[${i+1}] ${s.excerpt}`).join('\n\n'))throw Error('The answer contains text outside the supplied excerpts.');
 return value;
}
