import { getApiBaseUrl, getApiCredentials } from '@/lib/config';
export type DiscoveryScope='web'|'linkedin'|'facebook'|'instagram';
export interface DiscoveryCandidate {id:string;title:string;url:string;snippet:string}
export interface DiscoveryResult {results:DiscoveryCandidate[];query:string;scope:DiscoveryScope;searchedAt:string}
function endpoint(path:string){const u=new URL(getApiBaseUrl());if(u.protocol!=='http:'||!['localhost','127.0.0.1','[::1]'].includes(u.hostname)||u.username||u.password||u.pathname!=='/'||u.search||u.hash)throw new Error('A local API is required.');return u.origin+'/api/v1/prospect-research/'+path;}
export async function discoveryCapabilities(signal:AbortSignal){
  const response=await fetch(endpoint('discovery-capabilities'),{credentials:getApiCredentials(),cache:'no-store',redirect:'error',signal});
  if(!response.ok)throw new Error('Search connection status is unavailable.');
  const value=await response.json();if(typeof value.enabled!=='boolean'||!['disabled','serpapi'].includes(value.provider)||!Number.isInteger(value.daily_limit)||value.daily_limit<1||value.daily_limit>10||value.automatic_collection!==false||value.outreach_enabled!==false)throw new Error('Search status could not be verified.');
  return {enabled:value.enabled,dailyLimit:Number(value.daily_limit)};
}
export function parseDiscovery(value:unknown,query:string,scope:DiscoveryScope):DiscoveryResult{
  const v=value as Record<string,unknown>;
  if(!v||v.provider!=='serpapi'||v.engine!=='google'||v.query!==query||v.scope!==scope||v.contacts_saved!==false||v.outreach_enabled!==false||v.automatic_collection!==false||typeof v.searched_at!=='string'||!Number.isFinite(Date.parse(v.searched_at))||!Array.isArray(v.results)||v.results.length>10)throw new Error('Search response could not be verified.');
  const seen=new Set<string>();const results=v.results.map((row:unknown)=>{
    const r=row as DiscoveryCandidate;if(!r||typeof r.id!=='string'||!/^[a-f0-9]{24}$/.test(r.id)||seen.has(r.id)||typeof r.title!=='string'||!r.title||r.title.length>200||typeof r.snippet!=='string'||r.snippet.length>1000||typeof r.url!=='string'||r.url.length>1500)throw new Error('Invalid discovery result.');
    const u=new URL(r.url);if(u.protocol!=='https:'||u.username||u.password||!u.hostname.includes('.'))throw new Error('Invalid source URL.');
    const hosts={linkedin:'linkedin.com',facebook:'facebook.com',instagram:'instagram.com'};if(scope!=='web'&&u.hostname!==hosts[scope]&&!u.hostname.endsWith('.'+hosts[scope]))throw new Error('Result is outside the selected scope.');
    seen.add(r.id);return {id:r.id,title:r.title,url:r.url,snippet:r.snippet};
  });return {results,query,scope,searchedAt:v.searched_at};
}
export async function discoverProspects(query:string,scope:DiscoveryScope,signal:AbortSignal){
  query=query.trim();if(query.length<3||query.length>300)throw new Error('Enter a search from 3 to 300 characters.');
  const response=await fetch(endpoint('discover'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,scope}),credentials:getApiCredentials(),cache:'no-store',redirect:'error',signal});
  if(response.status===429)throw new Error('Daily search-attempt limit reached. No new provider request was made.');
  if(!response.ok)throw new Error('Search could not finish or the provider is not connected. No contacts were saved. Do not retry automatically; provider credits may be used.');
  return parseDiscovery(await response.json(),query,scope);
}
