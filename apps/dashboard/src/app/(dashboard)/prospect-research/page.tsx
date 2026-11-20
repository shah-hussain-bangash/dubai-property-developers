import type { Metadata } from 'next';
import { PageHeader } from '@/components/ui/PageHeader';
import { ProspectResearchWorkspace } from '@/features/prospects/ProspectResearchWorkspace';
export const metadata: Metadata = { title: 'Prospect Research' };
export default function ProspectResearchPage() {
  return <><PageHeader eyebrow="Operations" title="Prospect Research" description="Define your audience and review sourced business profiles before outreach."/><ProspectResearchWorkspace/></>;
}
