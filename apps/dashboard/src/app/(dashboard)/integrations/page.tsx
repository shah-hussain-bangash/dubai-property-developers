import type {Metadata} from 'next';
import {IntegrationHub} from '@/features/enquiries/IntegrationHub';
export const metadata:Metadata={title:'Source integrations'};
export default function Page(){return <IntegrationHub/>;}
