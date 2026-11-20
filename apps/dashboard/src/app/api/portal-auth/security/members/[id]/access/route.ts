import {portalSecurityApi} from '@/lib/portalSecurityApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(request:Request,{params}:{params:Promise<{id:string}>}){return portalSecurityApi(request,'memberAccess',(await params).id);}
