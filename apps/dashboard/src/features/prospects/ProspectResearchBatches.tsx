'use client';
import { useRef,useState } from 'react';
import { researchBatches,type SavedBatch,type BatchSummary,type BatchAction } from '@/services/prospectBatches';
import type { DiscoveryCandidate,DiscoveryScope } from '@/services/prospectDiscovery';
import styles from './ProspectResearchWorkspace.module.css';
export function ProspectResearchBatches({disabled,onChoose}:{disabled:boolean;onChoose:(candidate:DiscoveryCandidate)=>void}){
  const [jobs,setJobs]=useState<BatchSummary[]>([]),[selected,setSelected]=useState<SavedBatch|null>(null),[location,setLocation]=useState('Dubai'),[scope,setScope]=useState<DiscoveryScope>('linkedin'),[target,setTarget]=useState(500);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[stale,setStale]=useState(false),[shown,setShown]=useState(20),[confirmCancel,setConfirmCancel]=useState(false),[loaded,setLoaded]=useState(false);
  const lock=useRef(false);
  async function perform(operation:'list'|'read'|'create'|BatchAction,id?:string){
    if(lock.current||disabled)return;lock.current=true;setBusy(true);setError('');
    try{
      const value=await researchBatches(operation,{id,revision:selected?.revision,location,scope,target});
      if(Array.isArray(value)){setJobs(value);setLoaded(true);}
      else{setSelected(value);setStale(false);setConfirmCancel(false);setShown(20);}
    }catch(e){setError(e instanceof Error?e.message:'Reload saved batch state before another action.');if(!['list','read'].includes(operation))setStale(true);}
    finally{lock.current=false;setBusy(false);}
  }
  const state=selected?.state;const waiting=state?.resume_at&&Date.parse(state.resume_at)>Date.now();
  return <section className="panel" aria-labelledby="research-jobs-title"><h2 id="research-jobs-title">Saved research jobs</h2>
    <p className="muted">Create a public-source research plan and retain progress in PostgreSQL. Creating or loading a job makes no search. Run next query makes at most one provider request and uses the shared daily allowance. Unattended scheduling is not enabled.</p>
    <fieldset disabled={disabled||busy} style={{border:0,padding:0}}><div className={styles.grid}>
      <label className={styles.field}>Research location<input value={location} maxLength={100} onChange={e=>setLocation(e.target.value)}/></label>
      <label className={styles.field}>Source candidate target<input type="number" min={1} max={500} value={target} onChange={e=>setTarget(Number(e.target.value))}/></label>
      <label className={styles.field}>Research job public scope<select value={scope} onChange={e=>setScope(e.target.value as DiscoveryScope)}><option value="linkedin">Google-indexed LinkedIn pages</option><option value="web">Google web results</option><option value="facebook">Google-indexed Facebook pages</option><option value="instagram">Google-indexed Instagram pages</option></select></label>
    </div><p className="muted">The plan contains 60 queries across six role groups and ten business sectors. A 500-source target is not a promise of 500 people or contacts. Results can be companies, directories or irrelevant pages and need review. No financial capacity is inferred.</p>
    <div className={styles.actions}><button className="btn" disabled={!location.trim()||!Number.isInteger(target)||target<1||target>500} onClick={()=>perform('create')}>Create research job - no search</button><button className="btn" onClick={()=>perform('list')}>Load research jobs</button></div></fieldset>
    {error&&<p role="alert">{error}</p>}{busy&&<p aria-live="polite">Working on the selected local job. No automatic retries.</p>}
    {loaded&&!jobs.length&&<p>No research jobs saved yet.</p>}
    {jobs.map(job=><p key={job.id}>{job.id} · {job.status} · {job.count}/{job.target} sources <button className="btn" disabled={disabled||busy} onClick={()=>perform('read',job.id)}>Open job {job.id}</button></p>)}
    {state&&<div className={styles.record}><h3>Research job {state.id}</h3><p>{state.status} · {state.candidates.length}/{state.target} source candidates · {state.cursor}/{state.queries.length} queries processed · {state.provider_attempts} intended provider attempts · Revision {selected.revision}</p><p>{state.notice}</p>
      {state.resume_at&&<p>Quota wait until {new Date(state.resume_at).toLocaleString('en-GB',{timeZone:'Asia/Dubai'})} GST. No automatic wake-up is scheduled.</p>}
      <div className={styles.actions}><button className="btn" disabled={disabled||busy} onClick={()=>perform('read',state.id)}>Reload selected job</button>
        <button className="btn btn-primary" disabled={disabled||busy||stale||!!waiting||!['ready','quota_wait'].includes(state.status)} onClick={()=>perform('advance',state.id)}>Run next query - uses search credit</button>
        {['ready','quota_wait'].includes(state.status)&&<button className="btn" disabled={disabled||busy||stale} onClick={()=>perform('pause',state.id)}>Pause research job</button>}
        {state.status==='paused'&&<button className="btn" disabled={disabled||busy||stale} onClick={()=>perform('resume',state.id)}>Resume research job</button>}
        {state.status==='request_uncertain'&&<button className="btn" disabled={disabled||busy||stale} onClick={()=>perform('skip_uncertain',state.id)}>Skip unconfirmed query - no retry</button>}
        {!['completed','queries_exhausted','cancelled'].includes(state.status)&&<button className="btn" disabled={disabled||busy||stale} onClick={()=>setConfirmCancel(true)}>Cancel research job</button>}
      </div>{confirmCancel&&<div><p>Cancel this job and retain its collected source candidates?</p><button className="btn" disabled={disabled||busy||stale} onClick={()=>perform('cancel',state.id)}>Confirm job cancellation</button><button className="btn" onClick={()=>setConfirmCancel(false)}>Keep research job</button></div>}
      {state.queries[state.cursor]&&<p>Next planned query: {state.queries[state.cursor].query} · {state.queries[state.cursor].scope}</p>}
      <p className="muted">These are source candidates, separate from saved prospect records and their PDF exports. Open a source, check relevance and contact attribution, then review it in the prospect form.</p>
      {state.candidates.slice(0,shown).map(row=><article className={styles.record} key={row.id}><h4>{row.title}</h4><p>{row.snippet}</p><p>Search role: {row.query_role} (query label, not a verified personal role)</p><a href={row.url} target="_blank" rel="noopener noreferrer">Open batch public source</a><p>{row.url}</p><button className="btn" disabled={disabled||busy} onClick={()=>onChoose(row)}>Review batch source in prospect form</button></article>)}
      {state.candidates.length>shown&&<button className="btn" onClick={()=>setShown(shown+20)}>Show more saved sources</button>}
    </div>}
  </section>;
}
