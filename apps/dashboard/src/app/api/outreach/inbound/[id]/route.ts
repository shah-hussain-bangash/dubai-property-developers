import {outreachInboundApi} from '@/lib/outreachApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(r:Request,{params}:{params:{id:string}}){return outreachInboundApi(r,params.id);}
