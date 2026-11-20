import type { DemoLeadChoices } from './demoLeads';

export const demoLeadExamples = [
  { id: 'near-term', label: 'Near-term apartment example' },
  { id: 'later', label: 'Later enquiry example' },
  { id: 'own-home', label: 'Own-home studio example' },
] as const;
export type DemoLeadExampleId = typeof demoLeadExamples[number]['id'];
export function demoLeadExampleChoices(id: DemoLeadExampleId): DemoLeadChoices {
  switch (id) {
    case 'near-term': return { budget: '1500000', location: 'Business Bay', bedrooms: 1, timeline: 1, purpose: 'investment' };
    case 'later': return { budget: '750000', location: 'Jumeirah Village Circle', bedrooms: 0, timeline: 12, purpose: 'investment' };
    case 'own-home': return { budget: '1000000', location: 'Jumeirah Village Circle', bedrooms: 0, timeline: 6, purpose: 'end_use' };
    default: throw new Error('Unknown fictional lead example.');
  }
}
