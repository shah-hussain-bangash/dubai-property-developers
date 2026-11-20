import { validateProspect, duplicateProspect, type Prospect, type ProspectInput } from './prospectResearch';
export const PROSPECT_CSV_COLUMNS = ['name','company','role','country','email','phone','source','relevance'] as const;
export const OPTIONAL_CONTACT_CSV_COLUMNS=['whatsapp','whatsapp_source','contact_resources'] as const;
export const MAX_CSV_BYTES = 2_000_000;
export interface CsvReviewRow { row:number; status:'ready'|'duplicate'|'invalid'; input?:ProspectInput; message:string }
export interface CsvReview { rows:CsvReviewRow[]; additions:ProspectInput[]; duplicates:number; invalid:number; overCapacity:boolean }

/** Strict comma-separated CSV, including escaped quotes and quoted newlines. */
export function parseProspectCsv(raw:string):ProspectInput[] {
  if(new TextEncoder().encode(raw).length>MAX_CSV_BYTES)throw new Error('CSV files must be 2 MB or smaller.');
  const text=raw.replace(/^\uFEFF/,'');
  const rows:string[][]=[];let row:string[]=[];let cell='';let quoted=false;let closed=false;
  const endCell=()=>{row.push(cell);cell='';closed=false;if(row.length>11)throw new Error('CSV rows support eight core columns and up to three optional contact columns.');};
  const endRow=()=>{endCell();if(row.some(value=>value.trim()))rows.push(row);row=[];if(rows.length>501)throw new Error('Import up to 500 prospect rows per file.');};
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(quoted){if(c==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}else cell+=c;continue;}
    if(c===','){endCell();continue;}
    if(c==='\n'||c==='\r'){if(c==='\r'&&text[i+1]==='\n')i++;endRow();continue;}
    if(closed)throw new Error('Unexpected text after a quoted field. Check the CSV quoting.');
    if(c==='"'){if(cell)throw new Error('Quotes must begin at the start of a CSV field.');quoted=true;continue;}
    cell+=c;
  }
  if(quoted)throw new Error('A quoted field is unfinished. Check the CSV file.');
  if(cell||row.length||closed)endRow();
  if(!rows.length)throw new Error('The file is empty. Download the CSV template first.');
  const headers=rows.shift()!.map(v=>v.trim().toLowerCase());
  if(headers.length<8||headers.length>11||new Set(headers).size!==headers.length||PROSPECT_CSV_COLUMNS.some(c=>!headers.includes(c))||headers.some(c=>![...PROSPECT_CSV_COLUMNS,...OPTIONAL_CONTACT_CSV_COLUMNS].includes(c as typeof PROSPECT_CSV_COLUMNS[number])))throw new Error('Required headers: '+PROSPECT_CSV_COLUMNS.join(', ')+'.');
  if(!rows.length)throw new Error('The template has no prospect rows yet. Add records before previewing.');
  return rows.map((values,index)=>{
    if(values.length!==headers.length)throw new Error(`CSV record ${index+2} has ${values.length} columns; it must match the header.`);
    const core=Object.fromEntries(PROSPECT_CSV_COLUMNS.map(key=>[key,values[headers.indexOf(key)]])) as unknown as ProspectInput;
    const optional=(key:string)=>headers.includes(key)?values[headers.indexOf(key)]:'';
    return {...core,whatsapp:optional('whatsapp'),whatsappSource:optional('whatsapp_source'),contactResources:optional('contact_resources')?optional('contact_resources').split(/\r?\n/):[]};
  });
}
export function reviewProspectCsv(inputs:ProspectInput[],existing:Prospect[]):CsvReview {
  const rows:CsvReviewRow[]=[];const additions:ProspectInput[]=[];const seen=[...existing];let duplicates=0;let invalid=0;
  inputs.forEach((input,index)=>{
    try{
      const value=validateProspect(input);
      if(duplicateProspect(seen,value)){duplicates++;rows.push({row:index+2,status:'duplicate',input:value,message:'Matches an existing record or an earlier CSV row; will be skipped.'});}
      else{additions.push(value);seen.push({...value,id:`preview-${index}`,status:'pending',collectedAt:'2026-01-01T00:00:00Z'});rows.push({row:index+2,status:'ready',input:value,message:'Ready for human review; contact permissions remain unknown.'});}
    }catch(e){invalid++;rows.push({row:index+2,status:'invalid',message:e instanceof Error?e.message:'Invalid row.'});}
  });
  return {rows,additions,duplicates,invalid,overCapacity:existing.length+additions.length>500};
}
