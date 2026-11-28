import type {KnowledgeAgent} from './agentKnowledge';
const fields=['total','staff_eligible','customer_eligible','overdue','due_soon','undated'] as const;
type Counts={total:number;staff_eligible:number;customer_eligible:number;overdue:number;due_soon:number;undated:number};
export type KnowledgeCoverage={as_of:string;window_days:7;agents:({agent_id:string}&Counts)[];summary:Counts};
export function parseKnowledgeCoverage(value:KnowledgeCoverage,agents:KnowledgeAgent[]):KnowledgeCoverage{
 const invalid=()=>Error('The source overview could not be verified. Please check again.');
 if(!value||typeof value.as_of!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value.as_of)||!Number.isFinite(Date.parse(value.as_of))||new Date(value.as_of).toISOString().slice(0,10)!==value.as_of||value.window_days!==7||!Array.isArray(value.agents)||value.agents.length!==agents.length)throw invalid();
 function check(c:Counts,limit:number){if(!c||fields.some(f=>!Number.isSafeInteger(c[f])||c[f]<0||c[f]>limit)||c.staff_eligible+c.overdue!==c.total||c.customer_eligible>c.staff_eligible||c.undated+c.due_soon>c.staff_eligible)throw invalid();}
 value.agents.forEach((row,i)=>{if(!row||row.agent_id!==agents[i].id)throw invalid();check(row,100);});
 check(value.summary,agents.length*100);
 if(fields.some(f=>value.summary[f]!==value.agents.reduce((sum,row)=>sum+row[f],0)))throw invalid();
 return value;
}
