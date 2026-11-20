import {publicationApi,publicListingApi,publicListingPhotoApi} from '@/lib/publicationApi';export const runtime='nodejs';export const dynamic='force-dynamic';
export async function GET(){return publicListingApi();}
