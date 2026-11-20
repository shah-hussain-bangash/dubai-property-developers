export interface ContactCandidate { value:string; context:string }
export interface SourceContacts { source:string; emails:ContactCandidate[]; phones:ContactCandidate[] }
export interface ContactDraft { source:string; email:string; phone:string }
export function extractSourceContacts(source:string,text:string,uae:boolean):SourceContacts {
  if(text.length>30000)throw new Error('Use up to 30,000 characters of public business-profile text.');
  if(!text.trim())throw new Error('Paste text from the public business source first.');
  let url:URL;try{url=new URL(source.trim());}catch{throw new Error('Enter the public HTTPS source URL.');}
  if(source.length>1500||url.protocol!=='https:'||url.username||url.password||!url.hostname.includes('.'))throw new Error('Enter a public HTTPS source URL without login details.');
  const emails:ContactCandidate[]=[],phones:ContactCandidate[]=[];
  const add=(rows:ContactCandidate[],value:string,line:string)=>{if(!rows.some(row=>row.value===value)){if(rows.length>=50)throw new Error('Too many contact candidates. Copy one business profile at a time.');rows.push({value,context:line.trim().slice(0,240)});}};
  for(const line of text.split(/\r?\n/)){
    for(const match of line.matchAll(/[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?)+/gi)){
      if(match[0].length<=254)add(emails,match[0].toLowerCase(),line);
    }
    const phoneText=line.replace(/https?:\/\/\S+|\S+@\S+/g,'');
    for(const match of phoneText.matchAll(/(?<![\w+])\+[1-9](?:[ ()-]*\d){6,14}(?![\d ()-]*\d)/g)){
      const value=match[0].replace(/[^+\d]/g,'');if(/^\+[1-9]\d{6,14}$/.test(value))add(phones,value,line);
    }
    if(uae)for(const match of phoneText.matchAll(/(?<![\w+\d])0(?:5\d(?:[ -]*\d){7}|[234679](?:[ -]*\d){7})(?![\w\d])/g)){
      add(phones,'+971'+match[0].replace(/\D/g,'').slice(1),line);
    }
  }
  return {source:url.href,emails,phones};
}
