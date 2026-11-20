import {publicationApi,publicListingApi,publicListingPhotoApi} from '@/lib/publicationApi';export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(r:Request,{params}:{params:Promise<{id:string}>}){return publicationApi(r,'review',(await params).id);}
