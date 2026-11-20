import type { Metadata } from 'next';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { DemoPropertyForm } from '@/features/properties/DemoPropertyForm';
import { PropertiesView } from '@/features/properties/PropertiesView';
import { DEMO_PROPERTIES } from '@/lib/demo-data';

export const metadata: Metadata = {
  title: 'Properties',
};

export default function PropertiesPage() {
  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Properties"
        description="Project and unit inventory used by the Property Recommendation Agent."
      />
      <DemoDataBanner>
        Projects, developers and units are fictional. Prices are illustrative placeholders, not market data.
      </DemoDataBanner>
      <DemoPropertyForm />
      <PropertiesView units={DEMO_PROPERTIES} />
    </>
  );
}
