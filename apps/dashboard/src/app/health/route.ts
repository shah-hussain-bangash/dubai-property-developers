import {portalProxy} from '@/lib/portalProxy';
export const runtime='nodejs';export const dynamic='force-dynamic';
export const GET=(request:Request)=>portalProxy(request,[],true);
