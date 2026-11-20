import {bridgeEnquiryApi} from '@/lib/enquiryApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(r:Request,{params}:{params:Promise<{id:string}>}){return bridgeEnquiryApi(r,(await params).id);}
