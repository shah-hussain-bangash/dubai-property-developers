import {agentApi} from '@/lib/agentPortalApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function DELETE(r:Request,{params}:{params:{id:string}}){return agentApi(r,'deleteView',params.id);}
