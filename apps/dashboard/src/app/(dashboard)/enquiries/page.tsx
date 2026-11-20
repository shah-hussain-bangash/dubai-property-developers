import type {Metadata} from 'next';
import {AdminEnquiryInbox} from '@/features/enquiries/LiveOperations';
export const metadata:Metadata={title:'Enquiry inbox'};
export default function Page(){return <AdminEnquiryInbox/>;}
