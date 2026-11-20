import { cleanup,fireEvent,render,screen } from '@testing-library/react';
import { afterEach,expect,it,vi } from 'vitest';
import { extractSourceContacts } from '@/services/prospectSourceContacts';
import { ProspectSourceContacts } from '@/features/prospects/ProspectSourceContacts';
import { ProspectResearchWorkspace } from '@/features/prospects/ProspectResearchWorkspace';
import { accessProspectDatabase } from '@/services/prospectDatabase';
import { emptyWorkspace } from '@/services/prospectResearch';
vi.mock('@/services/prospectDatabase',()=>({accessProspectDatabase:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const source='https://company.example/brokers';
it('deduplicates shared email addresses and retains source context',()=>{
  const result=extractSourceContacts(source,'Agent A: SALES@company.example\nAgent B: sales@company.example',false);
  expect(result.emails).toEqual([{value:'sales@company.example',context:'Agent A: SALES@company.example'}]);
});
it('does not turn office identifiers, dates or zero into phone contacts',()=>{
  const result=extractSourceContacts(source,'Office Number: 28641\nLicense: 17-12-2026\nPhone: 0',true);expect(result.phones).toEqual([]);
});
it('normalises international formatting without inferring WhatsApp',()=>{
  const result=extractSourceContacts(source,'Phone +971 (50) 123-4567',false);expect(result.phones[0].value).toBe('+971501234567');expect(result).not.toHaveProperty('whatsapp');
});
it('requires an explicit UAE choice before formatting local phones',()=>{
  const text='Mobile 0557695995\nOffice 042954422';expect(extractSourceContacts(source,text,false).phones).toEqual([]);expect(extractSourceContacts(source,text,true).phones.map(row=>row.value)).toEqual(['+971557695995','+97142954422']);
});
it('rejects unsafe sources and oversized text',()=>{
  for(const url of ['http://company.example','javascript:alert(1)','https://user:pass@company.example'])expect(()=>extractSourceContacts(url,'Contact',false)).toThrow();
  expect(()=>extractSourceContacts(source,'x'.repeat(30001),false)).toThrow();
});
it('bounds the candidate count and ignores phone-like URL values',()=>{
  expect(extractSourceContacts(source,'https://company.example/+971501234567',false).phones).toEqual([]);
  expect(()=>extractSourceContacts(source,Array.from({length:51},(_,i)=>`agent${i}@company.example`).join('\n'),false)).toThrow('Too many');
});
function preview(){
  fireEvent.change(screen.getByLabelText('Contact-review source URL'),{target:{value:source}});
  fireEvent.change(screen.getByLabelText('Copied public business-profile text'),{target:{value:'Business: sales@company.example\nPhone +971501234567'}});
  fireEvent.click(screen.getByRole('button',{name:'Find contact candidates'}));
}
it('requires selection and does not use network or save on preview',()=>{
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch);const choose=vi.fn();render(<ProspectSourceContacts disabled={false} onChoose={choose}/>);preview();
  expect(screen.getByRole('button',{name:'Use selected contacts in prospect form'})).toBeDisabled();expect(choose).not.toHaveBeenCalled();expect(fetch).not.toHaveBeenCalled();vi.unstubAllGlobals();
});
it('only offers the selected contact and clears preview on source edits',()=>{
  const choose=vi.fn();render(<ProspectSourceContacts disabled={false} onChoose={choose}/>);preview();fireEvent.click(screen.getByRole('radio',{name:'sales@company.example'}));fireEvent.click(screen.getByRole('button',{name:'Use selected contacts in prospect form'}));
  expect(choose).toHaveBeenCalledWith({source,email:'sales@company.example',phone:''});fireEvent.change(screen.getByLabelText('Contact-review source URL'),{target:{value:'https://another.example/'}});expect(screen.queryByRole('radio',{name:'sales@company.example'})).toBeNull();
});
it('requires confirmation before changing the parent form and preserves identity',async()=>{
  vi.mocked(accessProspectDatabase).mockResolvedValue({revision:2,workspace:emptyWorkspace()});render(<ProspectResearchWorkspace/>);
  await screen.findByText(/Storage: PostgreSQL/);await vi.waitFor(()=>expect(screen.getByRole('button',{name:'Find contact candidates'})).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Full name'),{target:{value:'Reviewed agent'}});fireEvent.change(screen.getByLabelText('Public business email (optional)'),{target:{value:'old@company.example'}});
  preview();fireEvent.click(screen.getByRole('radio',{name:'sales@company.example'}));fireEvent.click(screen.getByRole('button',{name:'Use selected contacts in prospect form'}));
  expect(screen.getByLabelText('Public business email (optional)')).toHaveValue('old@company.example');fireEvent.click(screen.getByRole('button',{name:'Apply selected contacts to form'}));
  expect(screen.getByLabelText('Full name')).toHaveValue('Reviewed agent');expect(screen.getByLabelText('Public business email (optional)')).toHaveValue('sales@company.example');expect(screen.getByLabelText('Reported WhatsApp number (optional, unverified)')).toHaveValue('');expect(accessProspectDatabase).toHaveBeenCalledTimes(1);
});
