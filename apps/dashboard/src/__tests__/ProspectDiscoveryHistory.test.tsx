import { cleanup,fireEvent,render,screen } from '@testing-library/react';
import { afterEach,expect,it,vi } from 'vitest';
import { DISCOVERY_HISTORY_KEY,readDiscoveryHistory,serialiseDiscoveryHistory } from '@/services/prospectDiscoveryHistory';
import { ProspectDiscovery } from '@/features/prospects/ProspectDiscovery';
const result={query:'Dubai brokerage companies',scope:'web' as const,searchedAt:new Date().toISOString(),results:[{id:'1234567890abcdef12345678',title:'Earlier company source',url:'https://company.example/contact',snippet:'Public business profile'}]};
const cap={enabled:true,provider:'serpapi',daily_limit:1,automatic_collection:false,outreach_enabled:false};
afterEach(()=>{cleanup();sessionStorage.clear();vi.unstubAllGlobals();});
it('round trips bounded public results',()=>{expect(readDiscoveryHistory(serialiseDiscoveryHistory(result))).toEqual(result);});
it('rejects expired future malformed and unsafe results',()=>{
  expect(readDiscoveryHistory(serialiseDiscoveryHistory({...result,searchedAt:new Date(Date.now()-86400001).toISOString()}))).toBeNull();
  expect(readDiscoveryHistory(serialiseDiscoveryHistory({...result,searchedAt:new Date(Date.now()+120000).toISOString()}))).toBeNull();
  expect(readDiscoveryHistory('x'.repeat(40001))).toBeNull();expect(readDiscoveryHistory('{')).toBeNull();
  expect(readDiscoveryHistory(serialiseDiscoveryHistory({...result,results:[{...result.results[0],url:'javascript:alert(1)'}]}))).toBeNull();
});
it('restores cached query and scope without making any network call',()=>{
  sessionStorage.setItem(DISCOVERY_HISTORY_KEY,serialiseDiscoveryHistory(result));const fetch=vi.fn();vi.stubGlobal('fetch',fetch);render(<ProspectDiscovery disabled={false} onChoose={vi.fn()}/>);
  expect(screen.queryByRole('heading',{name:'Earlier company source'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Restore last search results - no credit'}));
  expect(screen.getByRole('heading',{name:'Earlier company source'})).toBeVisible();expect(screen.getByLabelText('Business-profile search')).toHaveValue(result.query);expect(fetch).not.toHaveBeenCalled();
});
it('keeps old success after a daily-limit failure and can restore it',async()=>{
  sessionStorage.setItem(DISCOVERY_HISTORY_KEY,serialiseDiscoveryHistory(result));const fetch=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>cap}).mockResolvedValueOnce({ok:false,status:429});vi.stubGlobal('fetch',fetch);render(<ProspectDiscovery disabled={false} onChoose={vi.fn()}/>);
  fireEvent.click(screen.getByRole('button',{name:'Check search connection'}));await screen.findByText(/SerpApi connection configured/);
  fireEvent.click(screen.getByRole('button',{name:'Search public profiles once'}));await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'Restore last search results - no credit'}));expect(fetch).toHaveBeenCalledTimes(2);expect(screen.getByRole('heading',{name:'Earlier company source'})).toBeVisible();
});
it('clears cached results without touching prospect storage',()=>{
  localStorage.setItem('prospect-test-backup','preserved');sessionStorage.setItem(DISCOVERY_HISTORY_KEY,serialiseDiscoveryHistory(result));render(<ProspectDiscovery disabled={false} onChoose={vi.fn()}/>);fireEvent.click(screen.getByRole('button',{name:'Clear cached search results'}));expect(sessionStorage.getItem(DISCOVERY_HISTORY_KEY)).toBeNull();expect(localStorage.getItem('prospect-test-backup')).toBe('preserved');localStorage.removeItem('prospect-test-backup');
});
it('offers the contact review shortcut regardless of connection or quota',()=>{
  render(<ProspectDiscovery disabled={false} onChoose={vi.fn()}/>);expect(screen.getByRole('link',{name:'Go to contact review - no search needed'})).toHaveAttribute('href','#source-contacts-title');
});
