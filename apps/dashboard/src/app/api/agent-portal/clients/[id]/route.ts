import {agentApi} from '@/lib/agentPortalApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function PATCH(r:Request,{params}:{params:{id:string}}){return agentApi(r,'clientUpdate',params.id);}
export async function DELETE(r:Request,{params}:{params:{id:string}}){return agentApi(r,'clientArchive',params.id);}
