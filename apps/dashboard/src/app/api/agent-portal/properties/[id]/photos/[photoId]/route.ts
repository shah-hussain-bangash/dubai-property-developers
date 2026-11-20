import {propertyPhotoApi} from '@/lib/agentPortalApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function GET(r:Request,{params}:{params:{id:string;photoId:string}}){return propertyPhotoApi(r,params.id,params.photoId);}
export async function DELETE(r:Request,{params}:{params:{id:string;photoId:string}}){return propertyPhotoApi(r,params.id,params.photoId);}
