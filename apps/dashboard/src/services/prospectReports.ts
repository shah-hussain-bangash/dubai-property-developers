import { getApiBaseUrl, getApiCredentials } from '@/lib/config';
export async function downloadProspectReport(revision:number,prospectId?:string,combined=false):Promise<void>{
  if(!Number.isSafeInteger(revision)||revision<0||prospectId!==undefined&&!/^[a-zA-Z0-9-]{1,80}$/.test(prospectId))throw new Error('Reload the saved workspace before exporting.');
  const base=new URL(getApiBaseUrl());
  if(base.protocol!=='http:'||!['localhost','127.0.0.1','[::1]'].includes(base.hostname)||base.username||base.password||base.pathname!=='/'||base.search||base.hash)throw new Error('A local API is required.');
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),180000);
  try{
    const endpoint=combined?'reports.pdf':prospectId?`reports/${prospectId}.pdf`:'reports.zip';
    const response=await fetch(`${base.origin}/api/v1/prospect-research/${endpoint}?revision=${revision}`,{credentials:getApiCredentials(),cache:'no-store',redirect:'error',signal:controller.signal});
    if(response.status===409)throw new Error('Workspace changed or has no records. Reload before downloading reports.');
    if(response.status===422)throw new Error('The PDF font cannot faithfully display text in a record. Use the JSON backup until additional script support is added.');
    if(response.status===429)throw new Error('Another report is being generated. Try again after it finishes.');
    const type=prospectId||combined?'application/pdf':'application/zip';
    if(!response.ok||!response.headers.get('content-type')?.startsWith(type))throw new Error('The report could not be downloaded. Existing records are unchanged.');
    const blob=await response.blob();
    if(blob.size===0||blob.size>50_000_000)throw new Error('The report was empty or too large.');
    const prefix=new Uint8Array(await blob.slice(0,5).arrayBuffer());
    if(prospectId||combined?String.fromCharCode(...prefix)!=='%PDF-':prefix[0]!==80||prefix[1]!==75)throw new Error('The downloaded report format could not be verified.');
    const date=new Date(Date.now()+4*60*60*1000).toISOString().slice(0,10);
    const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=combined?`prospect-batch-${date}.pdf`:prospectId?`prospect-${prospectId}-${date}.pdf`:`prospect-reports-${date}.zip`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }finally{clearTimeout(timeout);}
}
