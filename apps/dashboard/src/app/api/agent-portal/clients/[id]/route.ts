import {agentApi} from '@/lib/agentPortalApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function PATCH(r:Request,{params}:{params:Promise<{id:string}>}){return agentApi(r,'clientUpdate',(await params).id);}
export async function DELETE(r:Request,{params}:{params:Promise<{id:string}>}){return agentApi(r,'clientArchive',(await params).id);}
