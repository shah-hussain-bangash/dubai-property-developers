import type { ScenarioSnapshot } from './demoScenarioHistory';

export function formatScenarioComparison(items: ScenarioSnapshot[], createdAt = new Date()): string {
  if (!items.length || items.length > 3 || new Set(items.map(item => item.key)).size !== items.length) throw new Error('Choose one to three distinct demo scenarios.');
  const lines = ['FICTIONAL SCENARIO COMPARISON', 'Mock services only - local snapshot', `Created (UTC): ${createdAt.toISOString()}`, 'Newest scenario first. Match scores reflect each scenario requirements.', ''];
  items.forEach((item, index) => {
    lines.push(`SCENARIO ${index + 1}`, `Maximum budget: AED ${item.choices.budget}`, `Location: ${item.choices.location}`, `Bedrooms: ${item.choices.bedrooms === 0 ? 'Studio' : item.choices.bedrooms}`, 'Property type: Apartment | Purpose: Investment',
      `Score: ${item.score === null ? 'Not returned' : item.score + '/100'}`, `Category: ${item.category ?? 'Not returned'}`, `Routing queue: ${item.queue ?? 'Not returned'}`,
      item.outcome === 'completed' ? 'Reply: Unsent draft; human review required' : 'Reply: Skipped - no matches');
    if (!item.matches.length) lines.push('No fictional property matches.');
    item.matches.forEach(match => lines.push(`Match: ${match.name}`, match.price === null ? 'Price: Not confirmed' : `Illustrative price: AED ${match.price}`, `Source: demo-seed | As of: ${match.date}`));
    lines.push('');
  });
  lines.push('DEMO NOTICE', 'Fictional demo only. Prices, availability, payment plans and handover dates require developer confirmation. No investment return is implied or guaranteed. Nothing was sent or booked. This report does not reserve a property.', 'Summary only. Individual scenario reports contain the detailed score rules, reasons and caveats.', '');
  return lines.join('\n');
}

export function downloadScenarioComparison(items: ScenarioSnapshot[]) {
  const blob = new Blob(['\uFEFF', formatScenarioComparison(items)], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url; anchor.download = 'fictional-scenario-comparison.txt';
    document.body.appendChild(anchor); anchor.click();
  } finally { anchor.remove(); URL.revokeObjectURL(url); }
}
