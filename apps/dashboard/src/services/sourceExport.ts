import {parseSourcePreview,type SourcePreview} from './agentKnowledge';
export type SourceExport={format:'agent-source-text-v1';agent_id:string;exported_at:string;sources:Omit<SourcePreview,'agent_id'>[]};
function calendar(value:unknown):boolean{return typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number(value.slice(0,4))>=1&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;}
export function parseSourceExport(value:SourceExport,agent:string):SourceExport{
 const invalid=()=>Error('The saved knowledge download could not be verified. Please try again.');
 if(!value||value.format!=='agent-source-text-v1'||value.agent_id!==agent||typeof value.exported_at!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|\+00:00)$/.test(value.exported_at)||!calendar(value.exported_at.slice(0,10))||!Number.isFinite(Date.parse(value.exported_at))||!Array.isArray(value.sources)||value.sources.length>100)throw invalid();
 const seen=new Set<string>();let chars=0;
 for(const item of value.sources){
  const source=item?.source;
  if(!source||typeof source.id!=='string'||!/^[a-f0-9]{64}$/.test(source.id)||seen.has(source.id)||![0,1].includes(source.customer_safe)||!(source.review_by===null||calendar(source.review_by))||typeof source.created!=='string'||!Number.isFinite(Date.parse(source.created)))throw invalid();
  parseSourcePreview({...item,agent_id:agent},agent,source.id);seen.add(source.id);chars+=source.chars;
 }
 if(chars>2000000)throw invalid();
 return value;
}
export function downloadSourceExport(value:SourceExport){
 const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
 try{const link=document.createElement('a');link.href=url;link.download=value.agent_id+'-saved-knowledge.json';link.click();}finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
}
