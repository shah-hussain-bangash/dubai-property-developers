import type {Metadata} from 'next';
import {PublicHome} from '@/features/portal/PublicHome';
export const metadata:Metadata={title:{absolute:'Dubai Property Developers | Invest. Build. Grow Together.'},description:'Explore Dubai property communities, development possibilities and professional collaboration with Dubai Property Developers.'};
export default function HomePage(){return <PublicHome/>;}
