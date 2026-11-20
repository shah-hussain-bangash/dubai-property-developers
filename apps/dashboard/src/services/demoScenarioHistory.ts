import type { ScenarioChoices, ScenarioResult } from './demoScenario';

export interface ScenarioSnapshot {
  key: string;
  choices: ScenarioChoices;
  outcome: 'completed' | 'no_matches';
  score: number | null;
  category: string | null;
  queue: string | null;
  matches: { name: string; price: string | null; date: string }[];
}

export function rememberScenario(previous: ScenarioSnapshot[], choices: ScenarioChoices, result: ScenarioResult, key: string): ScenarioSnapshot[] {
  if (result.status === 'duplicate' || previous.some(item => item.key === key)) return previous;
  const snapshot: ScenarioSnapshot = {
    key, choices: { budget: choices.budget, location: choices.location, bedrooms: choices.bedrooms },
    outcome: result.status, score: result.lead.score, category: result.lead.category, queue: result.lead.queue,
    matches: (result.properties?.matches ?? []).map(match => ({ name: match.name, price: match.price, date: match.date })),
  };
  return [snapshot, ...previous].slice(0, 3);
}
