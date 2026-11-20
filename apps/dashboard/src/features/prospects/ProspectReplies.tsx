'use client';
import {useRef,useState,type FormEvent} from 'react';
import {prospectReplies,type ReplyKind,type ReplySnapshot,type CallbackTask} from '@/services/prospectReplies';
import type {ResearchWorkspace} from '@/services/prospectResearch';
import styles from './ProspectResearchWorkspace.module.css';

const localNow=()=>{const now=new Date();return new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,16);};
export function ProspectReplies({prospects,disabled}:{prospects:ResearchWorkspace['prospects'];disabled:boolean}){
  const [saved,setSaved]=useState<ReplySnapshot|null>(null);const [busy,setBusy]=useState(false);const active=useRef(false);
  const [stale,setStale]=useState(false);const [error,setError]=useState('');const [message,setMessage]=useState('');
  const [prospect,setProspect]=useState('');const [channel,setChannel]=useState<'email'|'whatsapp'>('email');const [kind,setKind]=useState<ReplyKind>('reply');
  const [text,setText]=useState('');const [received,setReceived]=useState(localNow);const [confirmed,setConfirmed]=useState(false);const [eventId,setEventId]=useState(()=>crypto.randomUUID());
  const [selected,setSelected]=useState<CallbackTask|null>(null);const [outcome,setOutcome]=useState<'completed'|'cancelled'>('completed');const [note,setNote]=useState('');const [limit,setLimit]=useState(20);
  const locked=disabled||busy||stale||!saved;
  const name=(id:string)=>prospects.find(p=>p.id===id)?.name||'Prospect no longer in the current workspace';
  async function act(operation:'read'|'record'|'close',body?:Parameters<typeof prospectReplies>[1]){
    if(active.current||disabled)return false;active.current=true;setBusy(true);setError('');
    try{const value=await prospectReplies(operation,body);setSaved(value);setStale(false);setConfirmed(false);setMessage(operation==='read'?'Replies loaded. No inbox was fetched.':'Saved in PostgreSQL. No notification sent or call placed.');return true;}
    catch(e){setStale(true);setError(e instanceof Error?e.message:'Reply action failed. Reload before another action.');return false;}
    finally{active.current=false;setBusy(false);}
  }
  async function record(event:FormEvent){event.preventDefault();if(locked||!confirmed||!prospect||!text.trim())return;
    const stamp=new Date(received);if(!Number.isFinite(stamp.getTime())){setError('Choose the reply received time.');return;}
    if(await act('record',{revision:saved!.revision,prospect_id:prospect,event_id:eventId,channel,kind,received_at:stamp.toISOString(),text,confirmed})){setText('');setEventId(crypto.randomUUID());setReceived(localNow());}
  }
  async function close(event:FormEvent){event.preventDefault();if(locked||!selected||!note.trim())return;
    if(await act('close',{revision:saved!.revision,task_id:selected.id,status:outcome,note})){setSelected(null);setNote('');}
  }
  const tasks=[...(saved?.tasks??[])].sort((a,b)=>Number(b.status==='needs_review')-Number(a.status==='needs_review')||b.updated_at.localeCompare(a.updated_at));
  return <section className="panel" aria-labelledby="prospect-replies-title"><h2 id="prospect-replies-title" style={{scrollMarginTop:90}}>5. Replies and callback tasks</h2>
    <p>Record a reply you received elsewhere and match it to one saved prospect. Inbox sync, owner email alerts and calling are not connected. A reply creates a human review task; calling permission remains unknown.</p>
    <button className="btn" disabled={disabled||busy} onClick={()=>act('read')}>{saved?'Reload replies and tasks':'Load replies and tasks'}</button>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {saved&&<p>Storage: PostgreSQL · Revision {saved.revision} · {saved.reply_count} recorded replies · {saved.pending_count} callback tasks awaiting review · {saved.notification_count} local notification records, none delivered.</p>}
    <form onSubmit={record}><fieldset disabled={locked} style={{border:0,padding:0}}><div className={styles.grid}>
      <label className={styles.field}>Reply belongs to prospect<select required value={prospect} onChange={e=>{setProspect(e.target.value);setConfirmed(false);}}><option value="">Select a saved prospect</option>{prospects.map(p=><option key={p.id} value={p.id}>{p.name} — {p.company}{p.status==='archived'?' (archived)':''}</option>)}</select></label>
      <label className={styles.field}>Reply channel<select value={channel} onChange={e=>{setChannel(e.target.value as 'email'|'whatsapp');setConfirmed(false);}}><option value="email">Email</option><option value="whatsapp">WhatsApp</option></select></label>
      <label className={styles.field}>Reply classification<select value={kind} onChange={e=>{setKind(e.target.value as ReplyKind);setConfirmed(false);}}><option value="reply">Reply needing human review</option><option value="opt_out">Opt-out — stop contact and cancel pending callbacks</option><option value="auto_reply">Automatic or out-of-office reply</option><option value="bounce">Delivery failure or bounce</option></select></label>
      <label className={styles.field}>Reply received at (your device time)<input required type="datetime-local" value={received} onChange={e=>{setReceived(e.target.value);setConfirmed(false);}}/></label>
      <label className={`${styles.field} ${styles.wide}`}>Copied reply text<textarea required maxLength={10000} value={text} onChange={e=>{setText(e.target.value);setConfirmed(false);}}/></label>
    </div><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> I matched this reply to this prospect and checked its classification, including any opt-out.</label>
    <p><button className="btn btn-primary" disabled={!confirmed||!prospect||!text.trim()} type="submit">Save manually recorded reply</button></p></fieldset></form>
    {saved&&<><h3>Human callback review queue</h3><p>Tasks are assigned to the signed-in user who records the reply. Check contact ownership and permission before any human follow-up. Opt-outs cancel pending callbacks.</p>
      {!tasks.length&&<p>No callback tasks recorded.</p>}
      {tasks.slice(0,limit).map(task=><article key={task.id} className={styles.record}><h4>{name(task.prospect_id)}</h4><p>{task.status==='needs_review'?'Awaiting human callback review':task.status==='completed'?'Completed':'Cancelled'} · Assigned owner: {task.owner_id} · Calling permission: unknown</p>
        {task.completion_note&&<p>{task.completion_note}</p>}{task.status==='needs_review'&&task.owner_id===saved.actor_id&&<button className="btn" disabled={locked} onClick={()=>{setSelected(task);setNote('');}}>Record human outcome for {name(task.prospect_id)}</button>}</article>)}
      {tasks.length>limit&&<button className="btn" onClick={()=>setLimit(limit+20)}>Show more callback tasks</button>}
      {selected&&<form onSubmit={close}><fieldset disabled={locked} style={{border:0,padding:0}}><h4>Human outcome: {name(selected.prospect_id)}</h4><label className={styles.field}>Callback outcome<select value={outcome} onChange={e=>setOutcome(e.target.value as 'completed'|'cancelled')}><option value="completed">Completed human follow-up or review</option><option value="cancelled">Cancel callback task</option></select></label><label className={styles.field}>Human outcome note<textarea required maxLength={1500} value={note} onChange={e=>setNote(e.target.value)}/></label><button className="btn" type="submit" disabled={!note.trim()}>Save human outcome</button><button className="btn" type="button" onClick={()=>setSelected(null)}>Keep task open</button></fieldset></form>}
      <h3>Recent manually recorded replies</h3><p>Showing the latest {saved.recent_replies.length} of {saved.reply_count}; text previews are limited to 500 characters.</p>
      {saved.recent_replies.map(reply=><article key={reply.id} className={styles.record}><strong>{name(reply.prospect_id)}</strong><p>{reply.channel} · {({reply:'Reply',opt_out:'Opt-out',auto_reply:'Automatic reply',bounce:'Delivery failure'})[reply.kind]} · {new Date(reply.received_at).toLocaleString()}</p><p style={{whiteSpace:'pre-wrap'}}>{reply.text}</p></article>)}
    </>}
  </section>;
}
