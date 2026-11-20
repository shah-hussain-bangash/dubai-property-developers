import {emailSecurityApi} from '@/lib/emailSecurityApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(request:Request){return emailSecurityApi(request,'requestVerify');}
