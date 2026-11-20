'use client';
import { useState } from 'react';
import { extractSourceContacts,type SourceContacts,type ContactDraft } from '@/services/prospectSourceContacts';
import styles from './ProspectResearchWorkspace.module.css';
export function ProspectSourceContacts({disabled,onChoose}:{disabled:boolean;onChoose:(draft:ContactDraft)=>void}){
  const [source,setSource]=useState(''),[text,setText]=useState(''),[uae,setUae]=useState(false);
  const [preview,setPreview]=useState<SourceContacts|null>(null),[email,setEmail]=useState(''),[phone,setPhone]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
  function clearPreview(){setPreview(null);setEmail('');setPhone('');setError('');setNotice('');}
  return <section className="panel" aria-labelledby="source-contacts-title"><h2 id="source-contacts-title" tabIndex={-1} style={{scrollMarginTop:90}}>Review contacts from public source text</h2>
    <p className="muted">Copy one public business profile and its source URL. Find contact candidates locally, then select the email and phone that belong to that profile. Shared company addresses and support numbers may appear. This does not fetch pages, use search credits or verify contact details.</p>
    <fieldset disabled={disabled} style={{border:0,padding:0}}><div className={styles.grid}>
      <label className={styles.field}>Contact-review source URL<input type="url" maxLength={1500} value={source} onChange={e=>{setSource(e.target.value);clearPreview();}}/></label>
      <label className={`${styles.field} ${styles.wide}`}>Copied public business-profile text<textarea maxLength={30000} value={text} onChange={e=>{setText(e.target.value);clearPreview();}}/></label>
      <label><input type="checkbox" checked={uae} onChange={e=>{setUae(e.target.checked);clearPreview();}}/>This source uses UAE local phone numbers: format recognised local numbers with +971</label>
    </div><div className={styles.actions}><button className="btn" onClick={()=>{clearPreview();try{setPreview(extractSourceContacts(source,text,uae));}catch(e){setError((e as Error).message);}}}>Find contact candidates</button><button className="btn" onClick={()=>{setSource('');setText('');clearPreview();}}>Clear copied source text</button></div>
    {error&&<p role="alert">{error}</p>}{preview&&<div><p>{preview.emails.length} email candidates Â· {preview.phones.length} phone candidates. No contacts saved.</p>
      <fieldset><legend>Select one business email</legend><label><input type="radio" name="source-email" checked={!email} onChange={()=>setEmail('')}/>Leave email blank</label>{preview.emails.map(row=><div key={row.value}><label><input type="radio" name="source-email" checked={email===row.value} onChange={()=>setEmail(row.value)}/>{row.value}</label><p className="muted">Source line: {row.context}</p></div>)}</fieldset>
      <fieldset><legend>Select one business phone</legend><label><input type="radio" name="source-phone" checked={!phone} onChange={()=>setPhone('')}/>Leave phone blank</label>{preview.phones.map(row=><div key={row.value}><label><input type="radio" name="source-phone" checked={phone===row.value} onChange={()=>setPhone(row.value)}/>{row.value}</label><p className="muted">Source line: {row.context}</p></div>)}</fieldset>
      <p className="muted">Selecting a mobile number does not identify it as WhatsApp. Complete the person, company and relevance in the form below; review does not grant marketing permission.</p>
      <button className="btn" disabled={!email&&!phone} onClick={()=>{onChoose({source:preview.source,email,phone});setNotice('Selected details offered to the prospect form. Review that form before saving.');}}>Use selected contacts in prospect form</button>
    </div>}{notice&&<p aria-live="polite">{notice}</p>}</fieldset>
  </section>;
}
