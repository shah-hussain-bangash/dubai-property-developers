'use client';
import { useEffect, useState, useRef, type FormEvent } from 'react';
import { PROSPECT_STORAGE_KEY, emptyWorkspace, validateTarget, validateProspect, duplicateProspect, parseWorkspace, type ResearchWorkspace, type ProspectInput, type ReviewStatus } from '@/services/prospectResearch';
import { accessProspectDatabase } from '@/services/prospectDatabase';
import { ProspectCsvImport } from './ProspectCsvImport';
import { downloadProspectReport } from '@/services/prospectReports';
import { ProspectResearchBatches } from './ProspectResearchBatches';
import { ProspectReplies } from './ProspectReplies';
import { ProspectSourceContacts } from './ProspectSourceContacts';
import type { ContactDraft } from '@/services/prospectSourceContacts';
import { ProspectDiscovery } from './ProspectDiscovery';
import type { DiscoveryCandidate } from '@/services/prospectDiscovery';
import styles from './ProspectResearchWorkspace.module.css';
const blank = (): ProspectInput => ({name:'',company:'',role:'',country:'',email:'',phone:'',source:'',relevance:'',whatsapp:'',whatsappSource:'',contactResources:[]});
export function ProspectResearchWorkspace() {
  const [workspace,setWorkspace]=useState<ResearchWorkspace>(emptyWorkspace);
  const [target,setTarget]=useState(emptyWorkspace().target);
  const [input,setInput]=useState<ProspectInput>(blank);
  const [ready,setReady]=useState(false);
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const [storageError,setStorageError]=useState(false);
  const [revision,setRevision]=useState(0);
  const [busy,setBusy]=useState(false);
  const saving=useRef(false);
  const reportDownload=useRef(false);
  const [reporting,setReporting]=useState(false);
  const [browserBackup,setBrowserBackup]=useState<ResearchWorkspace|null>(null);
  const [filter,setFilter]=useState('all');
  const [search,setSearch]=useState('');
  const [confirmClear,setConfirmClear]=useState(false);
  const [pendingContacts,setPendingContacts]=useState<ContactDraft|null>(null);
  const [pendingSource,setPendingSource]=useState<DiscoveryCandidate|null>(null);
  useEffect(()=>{
    const controller=new AbortController();
    try { const raw=localStorage.getItem(PROSPECT_STORAGE_KEY);if(raw)setBrowserBackup(parseWorkspace(raw)); } catch {setMessage('Browser backup could not be read and has been preserved.');}
    accessProspectDatabase(undefined,controller.signal).then(loaded=>{
      if(!controller.signal.aborted){setWorkspace(loaded.workspace);setTarget(loaded.workspace.target);setRevision(loaded.revision);setReady(true);}
    }).catch(()=>{if(!controller.signal.aborted){setError('PostgreSQL workspace could not be loaded. Existing browser data is preserved. Check that the API and database are running, then reload.');setStorageError(true);}});
    return ()=>controller.abort();
  },[]);
  useEffect(()=>{if(pendingSource)document.getElementById('pending-research-source')?.scrollIntoView?.({behavior:'smooth',block:'center'});},[pendingSource]);
  async function save(next:ResearchWorkspace,notice:string) {
    if(saving.current||!ready||reportDownload.current)return false;
    saving.current=true;setBusy(true);
    try {const saved=await accessProspectDatabase({revision,workspace:next});setWorkspace(saved.workspace);setRevision(saved.revision);setMessage(notice);setError('');return true;}
    catch(e) {setError(e instanceof Error?e.message:'Save could not be confirmed. Reload before retrying.');setReady(false);setStorageError(true);return false;}
    finally {saving.current=false;setBusy(false);}
  }
  async function saveTarget(event:FormEvent) {
    event.preventDefault();try {const value=validateTarget(target);await save({...workspace,target:value},'Audience settings saved in PostgreSQL. No research job has been started.');}catch(e){setError((e as Error).message);}
  }
  async function add(event:FormEvent) {
    event.preventDefault();try {
      const value=validateProspect(input);
      if(workspace.prospects.length>=500) throw new Error('This workspace holds up to 500 records. Export a backup before managing an additional batch.');
      if(duplicateProspect(workspace.prospects,value)) throw new Error('A matching email, phone, or name and company already exists, including archived records.');
      const next={...workspace,prospects:[{...value,id:crypto.randomUUID(),collectedAt:new Date().toISOString(),status:'pending' as ReviewStatus},...workspace.prospects]};
      if(await save(next,'Prospect saved in PostgreSQL for review. Contact details remain unverified; outreach is not enabled.'))setInput(blank());
    }catch(e){setError((e as Error).message || 'Could not save the prospect.');}
  }
  async function importBrowserBackup() {
    if(!browserBackup)return;
    const merged=[...workspace.prospects];let skipped=0;
    for(const p of browserBackup.prospects){if(duplicateProspect(merged,p)||merged.some(r=>r.id===p.id))skipped++;else merged.push(p);}
    if(merged.length>500){setError('Combined records exceed 500. Existing browser and database records are preserved.');return;}
    const target=revision===0?browserBackup.target:workspace.target;
    if(await save({...workspace,target,prospects:merged},`Browser copy saved in PostgreSQL; ${skipped} duplicate records skipped. Original browser backup preserved.`)){setBrowserBackup(null);setTarget(target);}
  }
  async function importCsv(inputs:ProspectInput[]) {
    const merged=[...workspace.prospects];let skipped=0;
    try {
      for(const input of inputs){const value=validateProspect(input);if(duplicateProspect(merged,value)){skipped++;continue;}merged.push({...value,id:crypto.randomUUID(),collectedAt:new Date().toISOString(),status:'pending'});}
      if(merged.length>500)throw new Error('The CSV batch would exceed 500 records. No partial import was saved.');
      if(merged.length===workspace.prospects.length){setMessage('No new prospects to import. Duplicates skipped.');return true;}
      if(new TextEncoder().encode(JSON.stringify({revision,workspace:{...workspace,prospects:merged}})).length>2_000_000)throw new Error('Combined workspace is too large for one database save. Reduce the batch or long notes.');
      return await save({...workspace,prospects:merged},`${merged.length-workspace.prospects.length} CSV prospects saved to PostgreSQL; ${skipped} additional duplicates skipped. Outreach remains disabled.`);
    }catch(e){setError(e instanceof Error?e.message:'CSV import failed.');return false;}
  }
  async function exportReport(id?:string,combined=false) {
    if(reportDownload.current||saving.current||!ready||busy)return;
    reportDownload.current=true;setReporting(true);setError('');
    try {if(combined)await downloadProspectReport(revision,id,true);else await downloadProspectReport(revision,id);setMessage('Private research report downloaded. No records changed and no outreach triggered.');}
    catch(e){setError(e instanceof Error?e.message:'Report could not be downloaded.');}
    finally{reportDownload.current=false;setReporting(false);}
  }
  function exportBackup() {
    const url=URL.createObjectURL(new Blob([JSON.stringify(workspace,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='prospect-research-backup.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    setMessage('Backup downloaded. It contains contact details; keep it private.');
  }
  const records=workspace.prospects.filter(p=>(filter==='all'||p.status===filter)&&`${p.name} ${p.company} ${p.role} ${p.country}`.toLowerCase().includes(search.toLowerCase()));
  return <div className={styles.workspace}>
    <a className="btn" href="/prospect-research/outreach">Open social outreach workspace</a> <a className="btn" href="/integrations#social-connections">Set up social accounts</a>
    <a className="btn" href="#prospect-replies-title">Go to replies and callback tasks</a>
    <div className={styles.notice}><strong>PostgreSQL research workspace — manual entry and CSV import</strong><p>Records are saved in the local PostgreSQL database for your active organization. They survive browser-data clearing and API restarts. This development console is for local use on a trusted computer. Use only public business contact details you are authorised to retain.</p><p>Scheduled 24-hour contact collection, email verification, messaging, AI calls and meeting booking are not connected. Your daily target is a planning setting, not a running 24-hour collection job.</p></div>
    <p className="muted">Private PDFs contain saved contact details and recorded sources. Some writing systems are not yet supported: affected exports are blocked rather than changing names or notes. Use the JSON backup when a PDF cannot be generated.</p>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {storageError&&<p className={styles.notice}>Reload after checking the API and PostgreSQL. Editing is disabled until the last saved database state is loaded. Existing browser backups are preserved.</p>}
    {browserBackup&&<div className={styles.notice}><strong>Browser workspace available: {browserBackup.prospects.length} records</strong><p>Copy these records to PostgreSQL explicitly. Duplicates are skipped; existing database audience settings are kept when a workspace already exists. Your original browser copy remains unchanged.</p><button className="btn" disabled={!ready||busy||reporting} onClick={importBrowserBackup}>Copy browser workspace to PostgreSQL</button></div>}
    <section className="panel" aria-labelledby="audience-title"><h2 id="audience-title">1. Target audience</h2>
      <form onSubmit={saveTarget}><fieldset disabled={!ready||busy||reporting} style={{border:0,padding:0}}><div className={styles.grid}>
        {(['audiences','countries','industries','languages'] as const).map(key=><label className={styles.field} key={key}>{({audiences:'Audience roles',countries:'Target countries',industries:'Industries (optional)',languages:'Languages'})[key]}<input value={target[key]} maxLength={key==='audiences'?500:key==='languages'?200:300} required={key!=='industries'} onChange={e=>setTarget({...target,[key]:e.target.value})}/></label>)}
        <label className={styles.field}>Daily research target (planning only)<input type="number" min="1" max="500" required value={target.dailyTarget} onChange={e=>setTarget({...target,dailyTarget:Number(e.target.value)})}/></label>
      </div><button className="btn btn-primary" type="submit">Save audience settings</button></fieldset></form>
    </section>
    <ProspectResearchBatches disabled={!ready||busy||reporting} onChoose={candidate=>setPendingSource(candidate)}/>
    <ProspectDiscovery disabled={!ready||busy||reporting} onChoose={candidate=>{if(input.source||input.relevance)setPendingSource(candidate);else{setInput(current=>({...current,source:candidate.url,relevance:`Search evidence (unverified): ${candidate.title}. ${candidate.snippet}`.slice(0,1500)}));setMessage('Source copied into the form. Complete and verify the business profile before saving. No contact was saved.');}}}/>
    {pendingSource&&<div id="pending-research-source" className={styles.notice}><p>Replace the source URL and evidence in your unfinished form with this search result? Other entered fields will be kept.</p><p>{pendingSource.title} - {pendingSource.url}</p><button className="btn" disabled={!ready||busy||reporting} onClick={()=>{setInput(current=>({...current,source:pendingSource.url,relevance:`Search evidence (unverified): ${pendingSource.title}. ${pendingSource.snippet}`.slice(0,1500)}));setPendingSource(null);setMessage('Source replaced in the unfinished form. No contact was saved.');}}>Replace form source and evidence</button><button className="btn" onClick={()=>setPendingSource(null)}>Keep existing form source</button></div>}
    <ProspectSourceContacts disabled={!ready||busy||reporting} onChoose={draft=>{setPendingContacts(draft);}}/>
    {pendingContacts&&<div className={styles.notice}><p>Apply these selected contacts and source URL to the unfinished prospect form? Existing name, company, role, country, relevance, WhatsApp and resources will be kept. Email, phone and source will be replaced; blank selections clear those contact fields.</p><p>Email: {pendingContacts.email||'Leave blank'} · Phone: {pendingContacts.phone||'Leave blank'}</p><button className="btn" disabled={!ready||busy||reporting} onClick={()=>{setInput(current=>({...current,...pendingContacts}));setPendingContacts(null);setMessage('Selected contacts copied to the form, unverified. Complete the profile and source evidence before saving.');}}>Apply selected contacts to form</button><button className="btn" onClick={()=>setPendingContacts(null)}>Keep existing prospect form</button></div>}
    <section className="panel" aria-labelledby="add-title"><h2 id="add-title">2. Add a sourced prospect</h2><p className="muted">Source evidence supports your research. A job title or public phone number does not establish buying interest or permission to contact.</p>
      <form onSubmit={add}><fieldset disabled={!ready||busy||reporting} style={{border:0,padding:0}}><div className={styles.grid}>
        {(['name','company','role','country','email','phone','source','relevance'] as const).map(key=><label className={`${styles.field} ${key==='relevance'?styles.wide:''}`} key={key}>{({name:'Full name',company:'Company',role:'Business role',country:'Country',email:'Public business email (optional)',phone:'Public business phone (optional)',source:'Public source URL (HTTPS)',relevance:'Evidence of relevance'})[key]}
          {key==='relevance'?<textarea required maxLength={1500} value={input[key]} onChange={e=>setInput({...input,[key]:e.target.value})}/>:<input required={!['email','phone'].includes(key)} type={key==='email'?'email':key==='source'?'url':'text'} maxLength={key==='source'?1500:key==='email'?254:key==='phone'?40:key==='company'?160:key==='country'?100:120} value={input[key]} onChange={e=>setInput({...input,[key]:e.target.value})}/>}
        </label>)}
        <label className={styles.field}>Reported WhatsApp number (optional, unverified)<input maxLength={40} value={input.whatsapp??''} onChange={e=>setInput({...input,whatsapp:e.target.value})}/></label>
        <label className={styles.field}>Public source for WhatsApp number<input type="url" maxLength={1500} required={Boolean(input.whatsapp)} value={input.whatsappSource??''} onChange={e=>setInput({...input,whatsappSource:e.target.value})}/></label>
        <label className={`${styles.field} ${styles.wide}`}>Other public contact resources (up to five HTTPS URLs, one per line)<textarea maxLength={7504} value={(input.contactResources??[]).join('\n')} onChange={e=>setInput({...input,contactResources:e.target.value?e.target.value.split('\n'):[]})}/></label>
      </div><p className="muted">Record a WhatsApp number only when a source explicitly lists it as WhatsApp. A source is not verification or permission to message. Other resources can be a company contact page or professional profile; no page is fetched automatically.</p><button className="btn btn-primary" type="submit">Save prospect for review</button></fieldset></form>
    </section>
    <ProspectCsvImport records={workspace.prospects} disabled={!ready||busy||reporting} onImport={importCsv}/>
    <section className="panel" aria-labelledby="queue-title"><h2 id="queue-title">4. Prospect review queue</h2>
      <p className="muted">Storage: PostgreSQL · Revision {revision}{busy?' · Saving…':''}</p>
      <div className={styles.stats}><span><strong>{workspace.prospects.length}</strong> collected</span><span><strong>{workspace.prospects.filter(p=>p.status==='pending').length}</strong> awaiting review</span><span><strong>{workspace.prospects.filter(p=>p.status==='reviewed').length}</strong> reviewed</span><span><strong>0</strong> outreach enabled</span></div>
      <div className={styles.actions}><label className={styles.field}>Search prospects<input value={search} onChange={e=>setSearch(e.target.value)}/></label><label className={styles.field}>Review status<select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All statuses</option><option value="pending">Awaiting review</option><option value="reviewed">Reviewed</option><option value="archived">Archived</option></select></label><button className="btn" disabled={!ready||busy||reporting} onClick={exportBackup}>Download private JSON backup</button><button className="btn" disabled={!ready||busy||reporting||!workspace.prospects.length} onClick={()=>exportReport(undefined,true)}>Download all prospects in one PDF</button><button className="btn" disabled={!ready||busy||reporting||!workspace.prospects.length} onClick={()=>exportReport()}>{reporting?'Preparing report download…':'Download all prospect PDFs (ZIP)'}</button></div>
      <p className="muted">Reviewed means a person checked this record. It does not verify email deliverability, WhatsApp availability, buying interest or marketing consent.</p>
      {!records.length&&<p>{workspace.prospects.length?'No prospects match these filters.':'No prospects yet. Add a public business profile above to begin.'}</p>}
      {records.map(p=><article className={styles.record} key={p.id}><h3>{p.name}</h3><p>{p.role} · {p.company} · {p.country}</p><span className={styles.badge}>{p.status==='pending'?'Awaiting review':p.status==='reviewed'?'Reviewed':'Archived'}</span><p>Email: {p.email||'Unknown'} · Phone: {p.phone||'Unknown'}</p><p>Reported WhatsApp: {p.whatsapp||'Unknown'} (unverified)</p>{p.whatsappSource&&<p>WhatsApp source: <a href={p.whatsappSource} target="_blank" rel="noopener noreferrer">{p.whatsappSource}</a></p>}{Boolean(p.contactResources?.length)&&<div><strong>Other recorded contact resources</strong><ul>{p.contactResources!.map((url,index)=><li key={index}><a href={url} target="_blank" rel="noopener noreferrer">{url}</a></li>)}</ul></div>}<p>Contact details: unverified. Email permission: unknown. WhatsApp permission: unknown. Calling permission: unknown.</p><p>{p.relevance}</p><a href={p.source} target="_blank" rel="noopener noreferrer">View recorded public source</a><p className="muted">Recorded {new Date(p.collectedAt).toLocaleString()}. Source contents have not been checked automatically.</p><div className={styles.actions}><button className="btn" disabled={!ready||busy||reporting} onClick={()=>exportReport(p.id)}>Download prospect PDF</button>{(['pending','reviewed','archived'] as const).filter(s=>s!==p.status).map(s=><button className="btn" disabled={!ready||busy||reporting} key={s} onClick={()=>save({...workspace,prospects:workspace.prospects.map(row=>row.id===p.id?{...row,status:s}:row)},'Review status saved. Outreach remains disabled.')}>{s==='reviewed'?'Mark reviewed':s==='archived'?'Archive':'Return to review'}</button>)}</div></article>)}
      <div className={styles.actions}><button className="btn" disabled={!ready||busy||reporting||!workspace.prospects.length} onClick={()=>setConfirmClear(true)}>Clear database prospect records</button>{confirmClear&&<><span>Download a backup first. Delete all database prospect records?</span><button className="btn" disabled={!ready||busy||reporting} onClick={async()=>{if(await save({...workspace,prospects:[]},'Database prospect records cleared.'))setConfirmClear(false);}}>Confirm deletion</button><button className="btn" onClick={()=>setConfirmClear(false)}>Cancel</button></>}</div>
    </section>
    <ProspectReplies prospects={workspace.prospects} disabled={!ready||busy||reporting}/>
  </div>;
}
