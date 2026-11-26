import {getApiBaseUrl,getApiCredentials} from '@/lib/config';

const NO_SOURCE_ANSWER="I could not find an answer in this agent's supplied sources. Add a relevant source or ask a more specific question.";

export type KnowledgeAgent={id:string;name:string;status:string};
export type AssignedSource={id:string;title:string;kind:string;uri:string|null;chars:number;created:string;review_by:string|null;customer_safe:number};
export type SourcePreview={agent_id:string;source:AssignedSource;pages:{page:number|null;text:string}[]};
export function parseReviewedSource(value:{agent_id:string;source:AssignedSource},agent:string,before:AssignedSource,date:string,customerSafe:boolean):AssignedSource{
 if(!value||value.agent_id!==agent||!value.source||(['id','title','kind','uri','chars','created'] as const).some(key=>value.source[key]!==before[key])||value.source.review_by!==date||value.source.customer_safe!==(customerSafe?1:0))throw Error('The saved review could not be verified. Refresh sources before retrying.');
 return value.source;
}
export function parseSourcePreview(value:SourcePreview,agent:string,sourceId:string):SourcePreview{
 const invalid=()=>Error('The saved source text could not be verified.');
 if(!value||value.agent_id!==agent||!value.source||value.source.id!==sourceId||typeof value.source.title!=='string'||!value.source.title.trim()||!['pdf','text','markdown','website'].includes(value.source.kind)||!validSourceUri(value.source.uri)||!Array.isArray(value.pages)||!value.pages.length||value.pages.length>100)throw invalid();
 let chars=0;
 value.pages.forEach((p,i)=>{if(!p||typeof p.text!=='string'||p.page!==(value.source.kind==='pdf'?i+1:null))throw invalid();chars+=p.text.length;});
 // Python stores Unicode code points; JavaScript string length counts UTF-16 units.
 const codePoints=value.pages.reduce((n,p)=>n+[...p.text].length,0);
 if(!chars||codePoints>200000||codePoints!==value.source.chars)throw invalid();
 return value;
}
export type SourceAnswer={agent_id:string;answered:boolean;supplied_sources_only:true;method:'source-excerpts';sent:false;text:string;sources:{source_id:string;label:string;title:string;uri:string|null;page:number|null;excerpt:string}[]};
function validSourceUri(value:unknown):boolean{
 if(value===null)return true;
 if(typeof value!=='string'||!/^https:\/\//i.test(value)||[...value].some(c=>c.charCodeAt(0)<=32||c.charCodeAt(0)===127))return false;
 try{
  const url=new URL(value);
  return url.protocol==='https:'&&!!url.hostname&&!url.username&&!url.password&&!url.port&&!url.hash;
 }catch{return false;}
}
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
  if(s.label!==String(i+1)||typeof s.excerpt!=='string'||!s.excerpt.trim()||typeof s.title!=='string'||!s.title.trim()||typeof s.source_id!=='string'||!s.source_id.trim()||!validPage||!validSourceUri(s.uri))throw Error('A source reference is invalid.');
 }
 if(value.answered&&value.text!==value.sources.map((s,i)=>`[${i+1}] ${s.excerpt}`).join('\n\n'))throw Error('The answer contains text outside the supplied excerpts.');
 return value;
}
