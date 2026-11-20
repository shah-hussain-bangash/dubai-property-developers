import type {Metadata} from 'next';
import {AdminPropertyPortfolio} from '@/features/agent-portal/AdminPropertyPortfolio';
export const metadata:Metadata={title:'Admin · Properties'};
export default function Page(){return <AdminPropertyPortfolio preview={process.env.DUBAI_PORTAL_DESIGN_PREVIEW==='1'}/>;}
