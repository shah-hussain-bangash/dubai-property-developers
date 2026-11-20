import {enquiryApi} from '@/lib/enquiryApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function PATCH(r:Request,{params}:{params:{id:string}}){return enquiryApi(r,'update',params.id);}
