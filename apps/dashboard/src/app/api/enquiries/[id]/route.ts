import {enquiryApi} from '@/lib/enquiryApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function PATCH(r:Request,{params}:{params:Promise<{id:string}>}){return enquiryApi(r,'update',(await params).id);}
