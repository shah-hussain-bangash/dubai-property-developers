import {portalProxy} from '@/lib/portalProxy';
export const runtime='nodejs';export const dynamic='force-dynamic';
const handle=async (request:Request,{params}:{params:Promise<{path:string[]}>})=>portalProxy(request,(await params).path);
export {handle as GET,handle as POST,handle as PUT,handle as PATCH,handle as DELETE,handle as HEAD};
