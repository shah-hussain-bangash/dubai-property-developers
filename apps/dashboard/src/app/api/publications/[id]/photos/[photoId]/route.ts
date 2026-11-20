import {publicationApi,publicListingApi,publicListingPhotoApi} from '@/lib/publicationApi';export const runtime='nodejs';export const dynamic='force-dynamic';
export async function GET(r:Request,{params}:{params:Promise<{id:string;photoId:string}>}){return publicListingPhotoApi(r,(await params).id,(await params).photoId,true);}
