import {bridgeEnquiryApi} from '@/lib/enquiryApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(r:Request,{params}:{params:{id:string}}){return bridgeEnquiryApi(r,params.id);}
