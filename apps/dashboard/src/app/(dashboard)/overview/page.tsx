import type {Metadata} from 'next';
import {LiveOperationsOverview} from '@/features/enquiries/LiveOperations';
export const metadata:Metadata={title:'Operations overview'};
export default function Page(){return <LiveOperationsOverview/>;}
