import type {AssignedSource} from './agentKnowledge';
export type ReviewQueue={agent_id:string;as_of:string;window_days:7;summary:{overdue:number;due_soon:number;current:number;undated:number};items:(AssignedSource&{review_status:'overdue'|'due_soon'})[]};
function day(value:unknown):number{
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return NaN;
 const stamp=Date.parse(value+'T00:00:00Z');return Number.isFinite(stamp)&&new Date(stamp).toISOString().slice(0,10)===value?stamp:NaN;
}
export function parseReviewQueue(value:ReviewQueue,agent:string):ReviewQueue{
 const invalid=()=>Error('The source review dates could not be verified.');
 if(!value||value.agent_id!==agent||!Number.isFinite(day(value.as_of))||value.window_days!==7||!value.summary||!Array.isArray(value.items)||value.items.length>100)throw invalid();
 const counts=['overdue','due_soon','current','undated'] as const;
 if(counts.some(k=>!Number.isInteger(value.summary[k])||value.summary[k]<0)||counts.reduce((n,k)=>n+value.summary[k],0)>100||value.items.length!==value.summary.overdue+value.summary.due_soon)throw invalid();
 const ids=new Set<string>();let overdue=0;
 for(const item of value.items){
  if(!item||typeof item.id!=='string'||!item.id.trim()||ids.has(item.id)||typeof item.title!=='string'||!item.title.trim()||!Number.isFinite(day(item.review_by)))throw invalid();
  const days=(day(item.review_by)-day(value.as_of))/86400000;
  const expected=days<0?'overdue':days<=7?'due_soon':'current';
  if(expected==='current'||item.review_status!==expected)throw invalid();
  if(expected==='overdue')overdue++;
  ids.add(item.id);
 }
 if(overdue!==value.summary.overdue)throw invalid();
 return value;
}
