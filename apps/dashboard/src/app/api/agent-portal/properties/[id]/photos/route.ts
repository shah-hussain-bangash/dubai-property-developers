import {propertyPhotoApi} from '@/lib/agentPortalApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(r:Request,{params}:{params:Promise<{id:string}>}){return propertyPhotoApi(r,(await params).id);}
