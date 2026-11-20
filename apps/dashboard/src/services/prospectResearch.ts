export const PROSPECT_STORAGE_KEY = 'dubai-research-workspace-v1';
export type ReviewStatus = 'pending' | 'reviewed' | 'archived';
export interface ResearchTarget { audiences: string; countries: string; industries: string; languages: string; dailyTarget: number }
export interface ProspectInput { name: string; company: string; role: string; country: string; email: string; phone: string; source: string; relevance: string; whatsapp?: string; whatsappSource?: string; contactResources?: string[] }
export interface Prospect extends ProspectInput { id: string; collectedAt: string; status: ReviewStatus }
export interface ResearchWorkspace { version: 1; target: ResearchTarget; prospects: Prospect[] }
export const emptyWorkspace = (): ResearchWorkspace => ({version:1,target:{audiences:'Investors, property agents, business owners, directors',countries:'United Arab Emirates',industries:'',languages:'English',dailyTarget:500},prospects:[]});
const clean = (value: unknown, max: number): string => {
  if (typeof value !== 'string' || value.length > max) throw new Error('A field is missing or too long.');
  return value.trim();
};
export function validateTarget(input: ResearchTarget): ResearchTarget {
  const target = {audiences:clean(input.audiences,500),countries:clean(input.countries,300),industries:clean(input.industries,300),languages:clean(input.languages,200),dailyTarget:input.dailyTarget};
  if (!target.audiences || !target.countries || !target.languages || !Number.isInteger(target.dailyTarget) || target.dailyTarget < 1 || target.dailyTarget > 500) throw new Error('Enter an audience, countries, languages and a daily target from 1 to 500.');
  return target;
}
export function validateProspect(input: ProspectInput): ProspectInput {
  const record: ProspectInput = {name:clean(input.name,120),company:clean(input.company,160),role:clean(input.role,120),country:clean(input.country,100),email:clean(input.email,254).toLowerCase(),phone:clean(input.phone,40),source:clean(input.source,1500),relevance:clean(input.relevance,1500),whatsapp:clean(input.whatsapp??'',40),whatsappSource:clean(input.whatsappSource??'',1500),contactResources:[]};
  if (!record.name || !record.company || !record.role || !record.country || !record.relevance) throw new Error('Complete the name, company, role, country and evidence of relevance.');
  if (record.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(record.email)) throw new Error('Enter a valid email format or leave it blank.');
  if (record.phone && !/^\+[1-9]\d{6,14}$/.test(record.phone)) throw new Error('Use an international phone number, for example +971 followed by the number, without spaces.');
  if(record.whatsapp&&!/^\+[1-9]\d{6,14}$/.test(record.whatsapp))throw new Error('Use international format for the reported WhatsApp number.');
  const publicUrl=(value:string)=>{let u:URL;try{u=new URL(value);}catch{throw new Error('Contact resources need public HTTPS URLs.');}if(u.protocol!=='https:'||u.username||u.password||!u.hostname.includes('.'))throw new Error('Contact resources need public HTTPS URLs without login details.');return u.href;};
  if(record.whatsapp&&!record.whatsappSource)throw new Error('Add the public source for the reported WhatsApp number.');
  if(record.whatsappSource)record.whatsappSource=publicUrl(record.whatsappSource);
  if(input.contactResources!==undefined&&!Array.isArray(input.contactResources))throw new Error('Add up to five public contact resource URLs.');
  const resources=(input.contactResources??[]).map(value=>clean(value,1500)).filter(Boolean);
  if(resources.length>5)throw new Error('Add up to five public contact resource URLs.');
  record.contactResources=resources.map(publicUrl);
  let url: URL;
  try { url = new URL(record.source); } catch { throw new Error('Enter the public HTTPS source URL.'); }
  if (url.protocol !== 'https:' || url.username || url.password || !url.hostname.includes('.')) throw new Error('Use a public HTTPS source URL without login details.');
  record.source=url.href;
  return record;
}
export function duplicateProspect(records: Prospect[], input: ProspectInput): boolean {
  const key=(v:string)=>v.trim().toLowerCase().replace(/\s+/g,' ');
  return records.some(p => Boolean(input.email && key(p.email)===key(input.email)) || [input.phone,input.whatsapp].some(number=>Boolean(number&&(p.phone===number||p.whatsapp===number))) || (key(p.name)===key(input.name) && key(p.company)===key(input.company)));
}
export function parseWorkspace(raw: string): ResearchWorkspace {
  if (raw.length > 5_000_000) throw new Error('Stored workspace is too large.');
  const data=JSON.parse(raw);
  if (!data || data.version !== 1 || !Array.isArray(data.prospects) || data.prospects.length > 500) throw new Error('Stored workspace format is unsupported.');
  const prospects: Prospect[]=[];
  const ids=new Set<string>();
  for (const item of data.prospects) {
    const input=validateProspect(item);
    if (!['pending','reviewed','archived'].includes(item.status) || typeof item.id!=='string' || !/^[a-zA-Z0-9-]{1,80}$/.test(item.id) || ids.has(item.id) || typeof item.collectedAt!=='string' || !Number.isFinite(Date.parse(item.collectedAt)) || duplicateProspect(prospects,input)) throw new Error('Stored prospect data needs attention.');
    ids.add(item.id);prospects.push({...input,id:item.id,collectedAt:item.collectedAt,status:item.status});
  }
  return {version:1,target:validateTarget(data.target),prospects};
}
