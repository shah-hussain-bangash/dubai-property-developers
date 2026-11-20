import type { DemoPropertyChoices } from './demoProperties';

export const demoPropertyExamples = [
  { id: 'marina', label: 'Marina apartment example' },
  { id: 'studio', label: 'JVC studio example' },
  { id: 'no-match', label: 'No-match search example' },
] as const;
export type DemoPropertyExampleId = typeof demoPropertyExamples[number]['id'];
export function demoPropertyExampleChoices(id: DemoPropertyExampleId): DemoPropertyChoices {
  switch (id) {
    case 'marina': return { budget: '2500000', location: 'Dubai Marina', bedrooms: '2', paymentPlan: false };
    case 'studio': return { budget: '1000000', location: 'Jumeirah Village Circle', bedrooms: '0', paymentPlan: true };
    case 'no-match': return { budget: '1000', location: 'Business Bay', bedrooms: '1', paymentPlan: false };
    default: throw new Error('Unknown fictional property example.');
  }
}
