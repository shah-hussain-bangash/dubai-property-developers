'use client';
import {useEffect,useState,type FormEvent} from 'react';
import {knowledgeRequest} from '@/services/agentKnowledge';
import {parseEvaluationSet,parseEvaluationReport,serializeEvaluationSet,MAX_QUESTION_SET_BYTES,QUESTION_SET_SIZE_MESSAGE,type EvaluationCase,type EvaluationReport} from '@/services/knowledgeEvaluation';
import s from './AgentKnowledgePanel.module.css';

function download(name:string,text:string){
 const url=URL.createObjectURL(new Blob([text],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download=name;link.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
const empty=(id:string):EvaluationCase=>({id,question:'',expectation:'answer',expected_excerpt:''});
export function AgentKnowledgeEvaluation({agent,name,sourceVersion,disabled,perform}:{agent:string;name:string;sourceVersion:string;disabled:boolean;perform:(action:(signal:AbortSignal)=>Promise<void>)=>Promise<void>}){
 const [audience,setAudience]=useState<'staff'|'customer'>('staff');
 const [cases,setCases]=useState<EvaluationCase[]>([empty('case-1')]);
 const [report,setReport]=useState<EvaluationReport|null>(null),[error,setError]=useState('');
 useEffect(()=>setReport(null),[sourceVersion]);
 function change(i:number,patch:Partial<EvaluationCase>){setCases(current=>current.map((c,j)=>i===j?{...c,...patch}:c));setReport(null);setError('');}
 function addQuestion(){setCases(current=>{if(current.length>=20)return current;const ids=new Set(current.map(c=>c.id));let next=1;while(ids.has('case-'+next))next++;return [...current,empty('case-'+next)];});setReport(null);}
 function checked(){return parseEvaluationSet({agent_id:agent,...(audience==='customer'?{audience}:{}),cases},agent);}
 async function run(event:FormEvent){event.preventDefault();setReport(null);setError('');await perform(async signal=>{const checks=checked();const result=await knowledgeRequest<EvaluationReport>('/'+agent+'/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(checks)},signal);if(signal.aborted)return;setReport(parseEvaluationReport(result,checks));});}
 return <section className={s.box} aria-labelledby="evaluation-title"><h3 id="evaluation-title">Saved checks for {name}</h3><p>Keep a separate question set for this agent. These checks never become knowledge sources. An answer check passes when a returned passage contains your expected text, with matching capital letters. A “not found” check passes when no passage is returned.</p><p>Save question sets on your device and load them here later. Up to 20 questions per set; question files can be up to 256 KB. Choose staff or customer checks. Customer checks use only current, approved sources for this agent. No customer reply is sent. Older question files use staff mode. Loading and editing a set preserves its check references; added questions receive a new reference.</p>
 <form onSubmit={run}><fieldset disabled={disabled}>
 <label htmlFor="evaluation-audience">Saved checks audience</label><select id="evaluation-audience" value={audience} onChange={e=>{setAudience(e.target.value as typeof audience);setReport(null);setError('');}}><option value="staff">Staff · all eligible assigned sources</option><option value="customer">Customer · approved sources only</option></select>
 {cases.map((c,i)=><div className={s.box} key={c.id}><label htmlFor={'check-question-'+i}>Question {i+1}</label><textarea id={'check-question-'+i} required minLength={3} maxLength={1000} rows={2} value={c.question} onChange={e=>change(i,{question:e.target.value})}/><label htmlFor={'check-outcome-'+i}>Expected outcome {i+1}</label><select id={'check-outcome-'+i} value={c.expectation} onChange={e=>change(i,{expectation:e.target.value as EvaluationCase['expectation'],expected_excerpt:e.target.value==='answer'?'':null})}><option value="answer">Should find a passage</option><option value="no_answer">Should say not found</option></select>{c.expectation==='answer'&&<><label htmlFor={'check-passage-'+i}>Expected passage {i+1}</label><textarea id={'check-passage-'+i} required maxLength={1000} rows={2} value={c.expected_excerpt??''} onChange={e=>change(i,{expected_excerpt:e.target.value})}/></>}<button type="button" className="btn" disabled={cases.length===1} onClick={()=>{setCases(cases.filter((_,j)=>i!==j));setReport(null);}}>Remove question {i+1}</button></div>)}
 <button type="button" className="btn" disabled={cases.length>=20} onClick={addQuestion}>Add question</button>
 <button type="submit" className="btn btn-primary">Run saved checks</button>
 <button type="button" className="btn" onClick={()=>{try{download(agent+(audience==='customer'?'-customer':'')+'-questions.json',serializeEvaluationSet(checked()));setError('');}catch(e){setError((e as Error).message);}}}>Save question set</button>
 <label htmlFor="evaluation-file">Load question set for this agent</label><input id="evaluation-file" type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;void perform(async signal=>{if(file.size>MAX_QUESTION_SET_BYTES)throw Error(QUESTION_SET_SIZE_MESSAGE);const loaded=parseEvaluationSet(JSON.parse(await file.text()),agent);if(signal.aborted)return;setAudience(loaded.audience??'staff');setCases(loaded.cases);setReport(null);setError('');});}}/>
 </fieldset></form>{error&&<p role="alert" className={s.error}>{error}</p>}
 {report&&<section aria-live="polite"><p><strong>{audience==='customer'?'Customer checks · Approved sources only':'Staff checks · All eligible assigned sources'}</strong></p><h4>{report.passed} of {report.evaluated} checks passed</h4><p>Results reflect this agent’s sources at the time of this run. Run again after changing sources.</p><ol>{report.cases.map((result,i)=><li key={result.id}><strong>{result.passed?'Passed':'Failed'}: {cases[i].question}</strong><p className={s.text}>{result.answer.text}</p>{result.answer.sources.map(source=><p key={source.label}>[{source.label}] {source.title}{source.page?' · Page '+source.page:''}</p>)}</li>)}</ol><button type="button" className="btn" disabled={disabled} onClick={()=>download(agent+(audience==='customer'?'-customer':'')+'-check-results.json',JSON.stringify({questions:checked(),results:report},null,2))}>Download results</button></section>}
 </section>;
}
