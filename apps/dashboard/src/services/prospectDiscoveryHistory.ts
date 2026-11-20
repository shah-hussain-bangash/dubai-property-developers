import { parseDiscovery,type DiscoveryResult } from './prospectDiscovery';
export const DISCOVERY_HISTORY_KEY='prospect-discovery-last-source-result-v1';
export function readDiscoveryHistory(raw:string|null,now=Date.now()):DiscoveryResult|null {
  if(!raw)return null;
  try{
    if(raw.length>40000)return null;
    const row=JSON.parse(raw);
    if(row.version!==1||typeof row.query!=='string'||row.query.length<3||row.query.length>300||!['web','linkedin','facebook','instagram'].includes(row.scope))return null;
    const result=parseDiscovery(row,row.query,row.scope);
    const age=now-Date.parse(result.searchedAt);if(age< -60000||age>86400000)return null;
    return result;
  }catch{return null;}
}
export function serialiseDiscoveryHistory(result:DiscoveryResult):string {
  return JSON.stringify({version:1,provider:'serpapi',engine:'google',query:result.query,scope:result.scope,searched_at:result.searchedAt,results:result.results,contacts_saved:false,outreach_enabled:false,automatic_collection:false});
}
