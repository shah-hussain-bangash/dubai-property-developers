import {enquiryApi} from '@/lib/enquiryApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(r:Request,{params}:{params:{id:string}}){return enquiryApi(r,'rotateConnector',params.id);}
