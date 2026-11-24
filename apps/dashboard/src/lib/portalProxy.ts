import {ownerSession,readSessionCookie,sameLocalOrigin,privateJson} from './portalAuth';
const prefixes=new Set(['prospect-research','leads','conversations','properties','knowledge','local-ai','agents','workflows','integrations','analytics']);
export async function portalProxy(request:Request,segments:string[],health=false):Promise<Response>{
  try{
    if(!await ownerSession(readSessionCookie(request)))return privateJson({error:'Sign in to your workspace.'},401);
    if(!['GET','HEAD'].includes(request.method)&&!sameLocalOrigin(request))return privateJson({error:'Request origin is not allowed.'},403);
    if(!health&&(!segments.length||!prefixes.has(segments[0])||segments.some(s=>!s||s==='.'||s==='..'||!/^[a-zA-Z0-9_.-]{1,100}$/.test(s))))return privateJson({error:'Route is not available.'},404);
    const target=process.env.DUBAI_PORTAL_API_ORIGIN||'http://api:8000';
    const serviceToken=process.env.DUBAI_PORTAL_API_TOKEN;
    if(serviceToken!==undefined){
      if(!/^[a-f0-9]{64}$/.test(serviceToken)||target!=='http://api:8000')return privateJson({error:'Workspace connection is unavailable.'},503);
      const sourcePath=segments[0]==='knowledge'&&segments[1]==='agents'&&/^[a-z][a-z0-9_]{0,63}$/.test(segments[2]||'');
      const sourceWrite=sourcePath&&((request.method==='POST'&&segments.length===4&&['sources','answer'].includes(segments[3]))||(request.method==='DELETE'&&segments.length===5&&segments[3]==='sources'&&/^[a-f0-9]{64}$/.test(segments[4])));
      if(!['GET','HEAD'].includes(request.method)&&!sourceWrite)return privateJson({error:'Only assigned-source knowledge changes are enabled.'},403);
      if(!health&&['prospect-research','local-ai'].includes(segments[0]))return privateJson({error:'Route is not available.'},404);
    }
    if(!['http://api:8000','http://127.0.0.1:8000','http://localhost:8000'].includes(target))return privateJson({error:'Workspace connection is unavailable.'},503);
    const query=new URL(request.url).search;if(query.length>4096)return privateJson({error:'Request is too large.'},413);
    const headers:Record<string,string>={'Accept':request.headers.get('accept')||'application/json','Origin':'http://localhost:3000'};
    if(serviceToken)headers.Authorization='Bearer '+serviceToken;
    if(health&&serviceToken){
      const [ready,authorized]=await Promise.all(['/ready','/api/v1/agents'].map(path=>fetch(target+path,{headers,redirect:'manual',cache:'no-store',signal:AbortSignal.timeout(10000)})));
      if(ready.status!==200||authorized.status!==200)return privateJson({error:'Workspace connection is unavailable.'},503);
      if((await ready.json()).status!=='ready')return privateJson({error:'Workspace connection is unavailable.'},503);
      await authorized.body?.cancel();
    }
    const contentType=request.headers.get('content-type');if(contentType)headers['Content-Type']=contentType;
    let body:Uint8Array|undefined;
    if(!['GET','HEAD'].includes(request.method)){
      const reader=request.body?.getReader();if(reader){const chunks:Uint8Array[]=[];let size=0;while(true){const next=await reader.read();if(next.done)break;size+=next.value.length;if(size>2_100_000){await reader.cancel();return privateJson({error:'Request is too large.'},413);}chunks.push(next.value);}body=Buffer.concat(chunks);}
    }
    const response=await fetch(target+(health?'/health':'/api/v1/'+segments.join('/'))+query,{method:request.method,headers,body,redirect:'manual',cache:'no-store',signal:AbortSignal.timeout(90000)});
    if(response.status>=300&&response.status<400)return privateJson({error:'Workspace connection redirected unexpectedly.'},502);
    const outgoing=new Headers({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'});
    for(const name of ['content-type','content-disposition']){const value=response.headers.get(name);if(value)outgoing.set(name,value);}
    return new Response(response.body,{status:response.status,headers:outgoing});
  }catch{return privateJson({error:'Workspace connection is unavailable. Reload before retrying a save.'},503);}
}
