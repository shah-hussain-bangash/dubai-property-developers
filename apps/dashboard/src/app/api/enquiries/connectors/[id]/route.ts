import {enquiryApi} from '@/lib/enquiryApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function DELETE(r:Request,{params}:{params:Promise<{id:string}>}){return enquiryApi(r,'disableConnector',(await params).id);}
