import {enquiryApi} from '@/lib/enquiryApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function DELETE(r:Request,{params}:{params:{id:string}}){return enquiryApi(r,'disableConnector',params.id);}
