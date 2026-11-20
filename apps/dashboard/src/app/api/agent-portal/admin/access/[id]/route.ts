import {agentApi} from '@/lib/agentPortalApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function PATCH(r:Request,{params}:{params:Promise<{id:string}>}){return agentApi(r,'access',(await params).id);}
