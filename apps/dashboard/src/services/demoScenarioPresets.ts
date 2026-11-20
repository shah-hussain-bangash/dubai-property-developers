import type { ScenarioChoices } from './demoScenario';

export const scenarioExamples = [
  { id: 'matching', label: 'Matching apartment example' },
  { id: 'no-match', label: 'No-match budget example' },
  { id: 'studio', label: 'Studio apartment example' },
] as const;
export type ScenarioExampleId = typeof scenarioExamples[number]['id'];

export function scenarioExampleChoices(id: ScenarioExampleId): ScenarioChoices {
  switch (id) {
    case 'matching': return { budget: '2000000', location: 'Business Bay', bedrooms: 1 };
    case 'no-match': return { budget: '1000', location: 'Business Bay', bedrooms: 1 };
    case 'studio': return { budget: '1000000', location: 'Jumeirah Village Circle', bedrooms: 0 };
    default: throw new Error('Unknown fictional example.');
  }
}
