import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { parseProspectCsv, reviewProspectCsv, PROSPECT_CSV_COLUMNS } from '@/services/prospectCsv';
import { ProspectCsvImport } from '@/features/prospects/ProspectCsvImport';
import type { Prospect } from '@/services/prospectResearch';
import { emptyWorkspace } from '@/services/prospectResearch';
import { accessProspectDatabase } from '@/services/prospectDatabase';
import { ProspectResearchWorkspace } from '@/features/prospects/ProspectResearchWorkspace';
vi.mock('@/services/prospectDatabase',()=>({accessProspectDatabase:vi.fn()}));
const header=PROSPECT_CSV_COLUMNS.join(',');
const row='Example Person,Example Company,Director,UAE,person@example.com,+971501234567,https://example.com/team,Public role; buying interest unknown';
const csv=header+'\r\n'+row+'\r\n';
const file=(text:string)=>({name:'prospects.csv',size:new TextEncoder().encode(text).length,arrayBuffer:async()=>new TextEncoder().encode(text).buffer});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it('reads BOM, escaped quotes, embedded commas and newlines',()=>{
  const parsed=parseProspectCsv('\uFEFF'+header+'\n'+row.replace('Example Company','"Example, ""Company"""').replace('Public role; buying interest unknown','"Public role\nBuying interest unknown"'));
  expect(parsed[0].company).toBe('Example, "Company"');expect(parsed[0].relevance).toContain('\n');
});
it('maps reordered headers rather than trusting column positions',()=>{
  const parsed=parseProspectCsv([...PROSPECT_CSV_COLUMNS].reverse().join(',')+'\n'+row.split(',').reverse().join(','));
  expect(parsed[0].name).toBe('Example Person');expect(parsed[0].source).toBe('https://example.com/team');
});
it('rejects malformed quotes, extra columns and permission columns',()=>{
  for(const text of [header+'\n"unfinished',header+'\n'+row+',extra',header.replace('relevance','permission')+'\n'+row,header+'\n"Name"x,Co,Director,UAE,,,https://example.com,Role'])expect(()=>parseProspectCsv(text)).toThrow();
});
it('accepts 500 rows and rejects 501 and oversized input',()=>{
  expect(parseProspectCsv(header+'\n'+Array(500).fill(row).join('\n'))).toHaveLength(500);
  expect(()=>parseProspectCsv(header+'\n'+Array(501).fill(row).join('\n'))).toThrow('500');
  expect(()=>parseProspectCsv('x'.repeat(2_000_001))).toThrow('2 MB');
});
it('skips duplicates within the file and in archived database records',()=>{
  const input=parseProspectCsv(csv)[0];
  const existing:Prospect={...input,id:'existing',status:'archived',collectedAt:'2026-10-26T10:00:00Z'};
  expect(reviewProspectCsv([input,input],[]).duplicates).toBe(1);
  expect(reviewProspectCsv([input],[existing]).additions).toHaveLength(0);
});
it('reports invalid rows without exposing an unsafe source as a link',()=>{
  const input=parseProspectCsv(csv)[0];const review=reviewProspectCsv([{...input,source:'javascript:alert(1)'}],[]);
  expect(review.invalid).toBe(1);expect(review.rows[0].input).toBeUndefined();
});
it('previews locally and sends only after explicit import',async()=>{
  const onImport=vi.fn().mockResolvedValue(true);render(<ProspectCsvImport records={[]} disabled={false} onImport={onImport}/>);
  fireEvent.change(screen.getByLabelText('Choose prospect CSV'),{target:{files:[file(csv)]}});
  const button=await screen.findByRole('button',{name:'Import 1 new prospects to PostgreSQL'});
  expect(onImport).not.toHaveBeenCalled();fireEvent.click(button);
  await vi.waitFor(()=>expect(onImport).toHaveBeenCalledTimes(1));expect(onImport.mock.calls[0][0][0].email).toBe('person@example.com');
  await vi.waitFor(()=>expect(screen.queryByRole('button',{name:'Import 1 new prospects to PostgreSQL'})).toBeNull());
});
it('blocks a batch with invalid rows',async()=>{
  render(<ProspectCsvImport records={[]} disabled={false} onImport={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText('Choose prospect CSV'),{target:{files:[file(csv.replace('+971501234567','invalid'))]}});
  expect(await screen.findByRole('alert')).toHaveTextContent('Fix the invalid records');
  expect(screen.getByRole('button',{name:'Import 0 new prospects to PostgreSQL'})).toBeDisabled();
});
it('does not truncate a batch when database capacity would be exceeded',async()=>{
  const input=parseProspectCsv(csv)[0];const records:Prospect[]=Array.from({length:500},(_,i)=>({...input,name:'Person '+i,email:'',phone:'',id:'id-'+i,collectedAt:'2026-10-26T10:00:00Z',status:'pending'}));
  render(<ProspectCsvImport records={records} disabled={false} onImport={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText('Choose prospect CSV'),{target:{files:[file(csv)]}});
  expect(await screen.findByRole('alert')).toHaveTextContent('No partial batch');
  expect(screen.getByRole('button',{name:'Import 1 new prospects to PostgreSQL'})).toBeDisabled();
});
it('retains preview after an unconfirmed database save and blocks repeated clicks',async()=>{
  let finish!:(value:boolean)=>void;const onImport=vi.fn().mockReturnValue(new Promise<boolean>(resolve=>{finish=resolve;}));
  render(<ProspectCsvImport records={[]} disabled={false} onImport={onImport}/>);
  fireEvent.change(screen.getByLabelText('Choose prospect CSV'),{target:{files:[file(csv)]}});
  fireEvent.click(await screen.findByRole('button',{name:'Import 1 new prospects to PostgreSQL'}));
  fireEvent.click(screen.getByRole('button',{name:'Saving CSV batch…'}));expect(onImport).toHaveBeenCalledTimes(1);
  finish(false);expect(await screen.findByRole('button',{name:'Import 1 new prospects to PostgreSQL'})).toBeVisible();
});
it('rechecks duplicates if the displayed database records change',async()=>{
  const onImport=vi.fn();const {rerender}=render(<ProspectCsvImport records={[]} disabled={false} onImport={onImport}/>);
  fireEvent.change(screen.getByLabelText('Choose prospect CSV'),{target:{files:[file(csv)]}});
  await screen.findByRole('button',{name:'Import 1 new prospects to PostgreSQL'});
  const input=parseProspectCsv(csv)[0];rerender(<ProspectCsvImport records={[{...input,id:'later',status:'pending',collectedAt:'2026-10-26T10:00:00Z'}]} disabled={false} onImport={onImport}/>);
  expect(screen.getByRole('button',{name:'Import 0 new prospects to PostgreSQL'})).toBeDisabled();expect(onImport).not.toHaveBeenCalled();
});
it('saves the merged CSV batch once with the database revision and keeps existing settings',async()=>{
  localStorage.clear();
  const input=parseProspectCsv(csv)[0];const existing:Prospect={...input,name:'Existing Person',email:'existing@example.com',phone:'',id:'existing',status:'reviewed',collectedAt:'2026-10-26T10:00:00Z'};
  const workspace={...emptyWorkspace(),target:{...emptyWorkspace().target,languages:'Arabic'},prospects:[existing]};
  const db=vi.mocked(accessProspectDatabase);db.mockReset();db.mockImplementation(async update=>update?{revision:12,workspace:update.workspace}:{revision:11,workspace});
  render(<ProspectResearchWorkspace/>);await screen.findByRole('heading',{name:'Existing Person'});
  fireEvent.change(screen.getByLabelText('Choose prospect CSV'),{target:{files:[file(csv)]}});
  expect(db).toHaveBeenCalledTimes(1);
  fireEvent.click(await screen.findByRole('button',{name:'Import 1 new prospects to PostgreSQL'}));
  await screen.findByRole('heading',{name:'Example Person'});
  expect(db).toHaveBeenCalledTimes(2);const saved=db.mock.calls[1][0]!;
  expect(saved.revision).toBe(11);expect(saved.workspace.target.languages).toBe('Arabic');expect(saved.workspace.prospects[0]).toEqual(existing);
  expect(saved.workspace.prospects[1].status).toBe('pending');expect(localStorage.length).toBe(0);
});
