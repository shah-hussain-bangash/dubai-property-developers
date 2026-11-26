import {parseSourceAnswer,type SourceAnswer} from './agentKnowledge';

export type EvaluationCase={id:string;question:string;expectation:'answer'|'no_answer';expected_excerpt:string|null};
export type EvaluationSet={agent_id:string;audience?:'staff'|'customer';cases:EvaluationCase[]};
export type EvaluationReport={agent_id:string;audience?:'staff'|'customer';supplied_sources_only:true;sent:false;evaluated:number;passed:number;failed:number;cases:{id:string;passed:boolean;answer:SourceAnswer}[]};
const invalid=()=>Error('This question set or result could not be verified for the selected agent.');
export function parseEvaluationSet(value:unknown,agent:string):EvaluationSet{
 if(!value||typeof value!=='object')throw invalid();
 const set=value as EvaluationSet;
 if(!['agent_id,cases','agent_id,audience,cases'].includes(Object.keys(set).sort().join(','))||(Object.hasOwn(set,'audience')&&set.audience!=='staff'&&set.audience!=='customer')||set.agent_id!==agent||!Array.isArray(set.cases)||!set.cases.length||set.cases.length>20)throw invalid();
 const ids=new Set<string>();
 for(const c of set.cases){
  if(!c||typeof c!=='object'||Object.keys(c).sort().join(',')!=='expectation,expected_excerpt,id,question'||typeof c.id!=='string'||!/^[a-zA-Z0-9_-]{1,64}$/.test(c.id)||ids.has(c.id)||typeof c.question!=='string'||c.question.trim().length<3||c.question.length>1000)throw invalid();
  if(c.expectation==='answer'?(typeof c.expected_excerpt!=='string'||!c.expected_excerpt.trim()||c.expected_excerpt.length>1000):c.expectation!=='no_answer'||c.expected_excerpt!==null)throw invalid();
  ids.add(c.id);
 }
 return {agent_id:agent,...(set.audience==='customer'?{audience:'customer' as const}:{}),cases:set.cases.map(c=>({...c,question:c.question.trim(),expected_excerpt:c.expected_excerpt?.trim()??null}))};
}
export function parseEvaluationReport(value:EvaluationReport,set:EvaluationSet):EvaluationReport{
 if(!value||(value.audience===undefined?'staff':value.audience)!==(set.audience??'staff')||value.agent_id!==set.agent_id||value.supplied_sources_only!==true||value.sent!==false||!Array.isArray(value.cases)||value.cases.length!==set.cases.length||value.evaluated!==set.cases.length)throw invalid();
 let passed=0;
 value.cases.forEach((result,i)=>{
  if(!result||result.id!==set.cases[i].id||typeof result.passed!=='boolean')throw invalid();
  const answer=parseSourceAnswer(result.answer,set.agent_id,set.audience??'staff'),expected=set.cases[i];
  const correct=expected.expectation==='no_answer'?!answer.answered:answer.sources.some(s=>s.excerpt.includes(expected.expected_excerpt!));
  if(result.passed!==correct)throw invalid();
  if(correct)passed++;
 });
 if(value.passed!==passed||value.failed!==value.evaluated-passed)throw invalid();
 return value;
}
