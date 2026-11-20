'use client';
import { useMemo, useRef, useState, type ChangeEvent } from 'react';
import { MAX_CSV_BYTES, PROSPECT_CSV_COLUMNS, OPTIONAL_CONTACT_CSV_COLUMNS, parseProspectCsv, reviewProspectCsv } from '@/services/prospectCsv';
import type { Prospect, ProspectInput } from '@/services/prospectResearch';
import styles from './ProspectResearchWorkspace.module.css';
export function ProspectCsvImport({records,disabled,onImport}:{records:Prospect[];disabled:boolean;onImport:(inputs:ProspectInput[])=>Promise<boolean>}) {
  const [inputs,setInputs]=useState<ProspectInput[]|null>(null);const [error,setError]=useState('');const [reading,setReading]=useState(false);const [saving,setSaving]=useState(false);const generation=useRef(0);const fileInput=useRef<HTMLInputElement>(null);const importing=useRef(false);
  const review=useMemo(()=>inputs?reviewProspectCsv(inputs,records):null,[inputs,records]);
  function clear(){generation.current++;setInputs(null);setError('');setReading(false);if(fileInput.current)fileInput.current.value='';}
  async function readFile(event:ChangeEvent<HTMLInputElement>){
    const file=event.target.files?.[0];const current=++generation.current;setInputs(null);setError('');if(!file){setReading(false);return;}setReading(true);
    try{
      if(!file.name.toLowerCase().endsWith('.csv')||file.size>MAX_CSV_BYTES)throw new Error('Choose a UTF-8 .csv file, 2 MB or smaller.');
      const buffer=await file.arrayBuffer();if(buffer.byteLength>MAX_CSV_BYTES)throw new Error('CSV file is too large.');
      const parsed=parseProspectCsv(new TextDecoder('utf-8',{fatal:true}).decode(buffer));
      if(current===generation.current)setInputs(parsed);
    }catch(e){if(current===generation.current)setError(e instanceof TypeError?'The file must use UTF-8 encoding.':e instanceof Error?e.message:'CSV could not be read.');}
    finally{if(current===generation.current)setReading(false);}
  }
  function downloadTemplate(){
    const url=URL.createObjectURL(new Blob(['\uFEFF'+[...PROSPECT_CSV_COLUMNS,...OPTIONAL_CONTACT_CSV_COLUMNS].join(',')+'\r\n'],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download='prospect-import-template.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function confirm(){
    if(importing.current||disabled||!review||review.invalid||review.overCapacity||!review.additions.length)return;
    importing.current=true;setSaving(true);
    try{if(await onImport(review.additions))clear();}catch{setError('Import could not be confirmed. Reload the workspace before retrying.');}finally{importing.current=false;setSaving(false);}
  }
  return <section className="panel" aria-labelledby="csv-title"><h2 id="csv-title">3. Import prospects from CSV</h2>
    <p className="muted">Preview up to 500 rows before saving. Each prospect needs a public source and evidence of relevance. Imports add new records; existing contacts and audience settings are preserved. Email and phone fields can be blank.</p>
    <div className={styles.actions}><button className="btn" onClick={downloadTemplate}>Download blank CSV template</button><label className={styles.field}>Choose prospect CSV<input ref={fileInput} type="file" accept=".csv,text/csv" disabled={disabled||reading||saving} onChange={readFile}/></label><button className="btn" disabled={saving||(!inputs&&!error&&!reading)} onClick={clear}>Clear CSV preview</button></div>
    <p className="muted">Required headers: {PROSPECT_CSV_COLUMNS.join(', ')}. Optional: {OPTIONAL_CONTACT_CSV_COLUMNS.join(', ')}. For multiple contact resources, use one URL per line inside a quoted CSV field. Use UTF-8 CSV with commas. Keep international phone numbers as text, starting with + and the country code. Source URLs must use HTTPS. Files are parsed in this browser; choosing a file does not upload it.</p>
    {reading&&<p role="status">Reading CSV locally…</p>}{error&&<p role="alert">{error}</p>}
    {review&&<><p role="status">{review.additions.length} ready · {review.duplicates} duplicates to skip · {review.invalid} invalid</p>
      {review.invalid>0&&<p role="alert">Fix the invalid records and select the corrected file. Nothing will be imported while invalid records remain.</p>}
      {review.overCapacity&&<p role="alert">This import would exceed the workspace limit of 500 records. Reduce the file before importing. No partial batch will be saved.</p>}
      {!review.additions.length&&!review.invalid&&<p>All rows are duplicates. No records will be saved.</p>}
      <details><summary>Review all {review.rows.length} CSV records</summary><p className="muted">Record numbers include the header; quoted multi-line fields count as one record.</p>{review.rows.map(row=><div className={styles.record} key={row.row}><strong>Record {row.row}: {row.status}</strong>{row.input&&<p>{row.input.name} · {row.input.company} · {row.input.email||'Email unknown'} · {row.input.phone||'Phone unknown'}</p>}<p>{row.message}</p>{row.input&&<><p>{row.input.role} · {row.input.country}</p><p>Reported WhatsApp: {row.input.whatsapp||'Unknown'} (unverified)</p>{row.input.whatsappSource&&<p>WhatsApp source: {row.input.whatsappSource}</p>}{row.input.contactResources?.map((url,index)=><p key={index}>Contact resource: {url}</p>)}<p>Evidence: {row.input.relevance}</p><p>Recorded source: {row.input.source}</p></>}</div>)}</details>
      <p className="muted">Imported records start as awaiting review with unknown contact permissions. No messages, calls or research jobs are triggered.</p>
      <button className="btn btn-primary" disabled={disabled||reading||saving||review.invalid>0||review.overCapacity||!review.additions.length} onClick={confirm}>{saving?'Saving CSV batch…':`Import ${review.additions.length} new prospects to PostgreSQL`}</button>
    </>}
  </section>;
}
