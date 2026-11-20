import {portalProxy} from '@/lib/portalProxy';
export const runtime='nodejs';export const dynamic='force-dynamic';
const handle=(request:Request,{params}:{params:{path:string[]}})=>portalProxy(request,params.path);
export {handle as GET,handle as POST,handle as PUT,handle as PATCH,handle as DELETE,handle as HEAD};
