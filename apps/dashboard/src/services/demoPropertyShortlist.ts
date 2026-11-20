import type { DemoPropertyMatch } from './demoProperties';

export function toggleDemoShortlist(previous: DemoPropertyMatch[], match: DemoPropertyMatch): DemoPropertyMatch[] {
  if (previous.some(item => item.id === match.id)) return previous.filter(item => item.id !== match.id);
  if (previous.length >= 3) return previous;
  return [...previous, {
    id: match.id, name: match.name, community: match.community, bedrooms: match.bedrooms,
    price: match.price, date: match.date, availability: match.availability, score: match.score,
    reasons: [...match.reasons], caveats: [...match.caveats],
  }];
}
