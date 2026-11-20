import {portalRecoveryApi} from '@/lib/portalRecoveryApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(request:Request){return portalRecoveryApi(request,'rehearse');}
