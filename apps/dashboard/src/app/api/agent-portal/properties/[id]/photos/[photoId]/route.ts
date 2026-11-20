import {propertyPhotoApi} from '@/lib/agentPortalApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function GET(r:Request,{params}:{params:Promise<{id:string;photoId:string}>}){return propertyPhotoApi(r,(await params).id,(await params).photoId);}
export async function DELETE(r:Request,{params}:{params:Promise<{id:string;photoId:string}>}){return propertyPhotoApi(r,(await params).id,(await params).photoId);}
