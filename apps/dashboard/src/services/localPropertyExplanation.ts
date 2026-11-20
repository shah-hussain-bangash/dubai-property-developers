import { getApiBaseUrl, getApiCredentials } from '@/lib/config';
import type { DemoPropertyChoices, DemoPropertyMatch } from './demoProperties';
export interface ExplainedListing { label:string; id:string; name:string; price:string|null; availability:string; date:string }
export type PropertyExplanation={generated:false;reason:string}|{generated:true;text:string;listings:ExplainedListing[];disclaimer:string};
const record=(value:unknown):value is Record<string,unknown>=>typeof value==='object'&&value!==null&&!Array.isArray(value);
export function parsePropertyExplanation(body:unknown,expectedIds:string[]):PropertyExplanation {
  if(!record(body)||body.sent!==false||body.requires_review!==true||!Array.isArray(body.listings))throw new Error('Invalid local property response.');
  if(body.generated===false){if(typeof body.reason!=='string'||!body.reason.trim()||body.listings.length!==0)throw new Error('Invalid no-match response.');return {generated:false,reason:body.reason};}
  if(body.generated!==true||body.provider!=='ollama'||body.model!=='qwen3:8b'||body.is_mock!==false||typeof body.text!=='string'||!body.text.trim()||body.text.length>20000||body.listings.length<1||body.listings.length>3||typeof body.disclaimer!=='string'||!body.disclaimer.includes('must be confirmed')||!body.disclaimer.includes('No investment return'))throw new Error('Invalid local property explanation.');
  const listings=body.listings.map((listing:unknown,index:number):ExplainedListing=>{
    if(!record(listing)||listing.label!==`P${index+1}`||typeof listing.id!=='string'||typeof listing.name!=='string'||!listing.name.includes('(Fictional)')||!['available','unknown'].includes(String(listing.availability))||typeof listing.data_as_of!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(listing.data_as_of)||(listing.price_aed!==null&&(typeof listing.price_aed!=='string'||!/^\d+(\.\d+)?$/.test(listing.price_aed)||!Number.isFinite(Number(listing.price_aed))||Number(listing.price_aed)<=0)))throw new Error('Invalid fictional property reference.');
    return {label:listing.label as string,id:listing.id,name:listing.name,price:listing.price_aed as string|null,availability:listing.availability as string,date:listing.data_as_of};
  });
  if(new Set(listings.map(item=>item.id)).size!==listings.length||listings.length!==expectedIds.length||listings.some((item,index)=>item.id!==expectedIds[index]))throw new Error('Matches changed. Match properties again.');
  const labels=[...body.text.matchAll(/\[P(\d+)\]/g)].map(match=>`P${match[1]}`);
  if(!labels.length||labels.some(label=>!listings.some(item=>item.label===label)))throw new Error('Invalid listing label.');
  return {generated:true,text:body.text,listings,disclaimer:body.disclaimer};
}
export async function explainLocalProperties(choices:DemoPropertyChoices,matches:DemoPropertyMatch[],signal:AbortSignal):Promise<PropertyExplanation>{
  if(!/^\d{1,10}$/.test(choices.budget)||Number(choices.budget)<=0||!['any','Business Bay','Dubai Marina','Jumeirah Village Circle'].includes(choices.location)||!['any','0','1','2','3','4','5'].includes(choices.bedrooms)||typeof choices.paymentPlan!=='boolean'||matches.length<1||matches.length>3)throw new Error('Match valid fictional properties first.');
  const base=new URL(getApiBaseUrl());
  if(base.protocol!=='http:'||!['localhost','127.0.0.1','[::1]'].includes(base.hostname)||base.username||base.password||base.pathname!=='/'||base.search||base.hash)throw new Error('A local API is required.');
  const response=await fetch(base.origin+'/api/v1/local-ai/property-explanation',{method:'POST',credentials:getApiCredentials(),redirect:'error',cache:'no-store',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({budget_max_aed:choices.budget,locations:choices.location==='any'?[]:[choices.location],bedrooms_min:choices.bedrooms==='any'?null:Number(choices.bedrooms),bedrooms_max:choices.bedrooms==='any'?null:Number(choices.bedrooms),require_payment_plan:choices.paymentPlan,include_unavailable:false,limit:3})});
  if(!response.ok)throw new Error('Local property explanation unavailable.');
  return parsePropertyExplanation(await response.json(),matches.map(item=>item.id));
}
