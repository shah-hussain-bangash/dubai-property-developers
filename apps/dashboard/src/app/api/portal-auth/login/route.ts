import {agentAccess} from '@/lib/agentPropertyStore';
import {memberSignIn,MEMBER_COOKIE} from '@/lib/portalMembers';
import {NextResponse} from 'next/server';
import {ownerSignIn,sameLocalOrigin,privateJson,SESSION_COOKIE,SESSION_SECONDS} from '@/lib/portalAuth';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(request:Request){
  if(!sameLocalOrigin(request))return privateJson({error:'Request origin is not allowed.'},403);
  if(!request.headers.get('content-type')?.startsWith('application/json'))return privateJson({error:'Invalid sign-in request.'},415);
  try{
    const reader=request.body?.getReader();if(!reader)return privateJson({error:'Invalid sign-in request.'},400);
    const chunks:Uint8Array[]=[];let size=0;
    while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>4096){await reader.cancel();return privateJson({error:'Sign-in request is too large.'},413);}chunks.push(value);}
    let body;try{body=JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{return privateJson({error:'Invalid sign-in request.'},400);}
    if(!body||Object.keys(body).some(key=>!['email','password','portal'].includes(key)))return privateJson({error:'Invalid sign-in request.'},400);
    const isOwner=typeof body.email==='string'&&body.email.trim().toLowerCase()===(process.env.DUBAI_PORTAL_ADMIN_EMAIL||'').trim().toLowerCase();
    if(body.portal!==undefined&&!['auto','admin','agent'].includes(body.portal))return privateJson({error:'Invalid sign-in request.'},400);
    if(body.portal==='admin'&&!isOwner||body.portal==='agent'&&isOwner)return privateJson({error:body.portal==='agent'?'Use Admin sign-in for the operations console.':'Use Agent sign-in for member and agent accounts.'},401);
    const session=isOwner?await ownerSignIn(body.email,body.password):await memberSignIn(body.email,body.password);
    if(!session)return privateJson({error:'Email or password is incorrect.'},401);
    const access=!isOwner&&'member' in session?await agentAccess(session.member.id):null;
    const destination=isOwner?'/overview':body.portal==='agent'||access==='approved'?'/agent-portal':'/account';
    const response=NextResponse.json({signed_in:true,destination},{headers:{'Cache-Control':'no-store, private'}});
    response.cookies.set(isOwner?SESSION_COOKIE:MEMBER_COOKIE,session.token,{httpOnly:true,sameSite:'strict',secure:new URL(request.url).protocol==='https:',path:'/',maxAge:SESSION_SECONDS});
    response.cookies.set(isOwner?MEMBER_COOKIE:SESSION_COOKIE,'',{httpOnly:true,sameSite:'strict',secure:new URL(request.url).protocol==='https:',path:'/',maxAge:0});
    return response;
  }catch(error){const code=(error as Error).message;return privateJson({error:(code==='SIGN_IN_LIMIT'||code==='MEMBER_LIMIT')?'Too many attempts. Try again in 15 minutes.':code==='PORTAL_NOT_CONFIGURED'?'The workspace owner needs to finish sign-in setup.':'Sign-in is temporarily unavailable. Please try again.'},(code==='SIGN_IN_LIMIT'||code==='MEMBER_LIMIT')?429:503);}
}
