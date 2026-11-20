import {agentApi} from '@/lib/agentPortalApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(r:Request,{params}:{params:Promise<{id:string}>}){return agentApi(r,'clientRestore',(await params).id);}
