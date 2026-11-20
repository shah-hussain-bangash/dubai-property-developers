import {agentApi} from '@/lib/agentPortalApi';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function POST(r:Request){return agentApi(r,'create');}
