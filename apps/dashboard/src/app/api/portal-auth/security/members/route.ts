import {portalSecurityApi} from '@/lib/portalSecurityApi';export const runtime='nodejs';export const dynamic='force-dynamic';
export async function GET(r:Request){return portalSecurityApi(r,'members');}
