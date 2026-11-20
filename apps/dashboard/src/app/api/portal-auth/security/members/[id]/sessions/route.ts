import {portalSecurityApi} from '@/lib/portalSecurityApi';export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(r:Request,{params}:{params:{id:string}}){return portalSecurityApi(r,'memberRevoke',params.id);}
