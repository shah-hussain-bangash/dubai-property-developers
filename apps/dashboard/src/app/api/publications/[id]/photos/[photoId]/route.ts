import {publicationApi,publicListingApi,publicListingPhotoApi} from '@/lib/publicationApi';export const runtime='nodejs';export const dynamic='force-dynamic';
export async function GET(r:Request,{params}:{params:{id:string;photoId:string}}){return publicListingPhotoApi(r,params.id,params.photoId,true);}
