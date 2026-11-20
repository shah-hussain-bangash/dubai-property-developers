import type { DemoPropertyChoices, DemoPropertyResult } from './demoProperties';

export function formatPropertySearchReport(choices: DemoPropertyChoices, result: DemoPropertyResult, createdAt = new Date()): string {
  const lines = ['FICTIONAL PROPERTY SEARCH REPORT', 'Mock services only - local snapshot', `Created (UTC): ${createdAt.toISOString()}`, '', 'SUBMITTED SEARCH FILTERS', `Maximum budget: AED ${choices.budget}`,
    `Location: ${choices.location === 'any' ? 'Any location' : choices.location}`, `Bedrooms: ${choices.bedrooms === 'any' ? 'Any bedrooms' : choices.bedrooms === '0' ? 'Studio' : choices.bedrooms}`, `Payment plan required: ${choices.paymentPlan ? 'Yes' : 'No'}`, '', `RETURNED FICTIONAL MATCHES: ${result.matches.length}`];
  if (!result.matches.length) lines.push(result.noMatch ?? 'No matching demo properties.');
  result.matches.forEach((item, index) => lines.push('', `${index + 1}. ${item.name}`, `Community: ${item.community}`, `Bedrooms: ${item.bedrooms === 0 ? 'Studio' : item.bedrooms}`, item.price === null ? 'Price: Not confirmed\nBudget fit not verified: price is unconfirmed.' : `Illustrative price: AED ${item.price}`,
    `Source: demo-seed | Data as of: ${item.date}`, `Catalog status: ${item.availability}${item.availability === 'unknown' ? '\nAvailability not verified: confirm before offering.' : ''}`, `Demo match score: ${Math.round(item.score * 100)}/100`, 'Reasons:', ...item.reasons.map(reason => `- ${reason}`), 'Caveats:', ...item.caveats.map(caveat => `- ${caveat}`)));
  lines.push('', result.disclaimer, '', 'DEMO NOTICE', 'Returned results reflect this search and its result limit, not the entire inventory or your saved shortlist. Fictional data only. Confirm prices, availability, payment plans and handover dates with the developer before quoting. No investment return is implied or guaranteed. Nothing was reserved, booked or sent. This report does not restore results into the application.', '');
  return lines.join('\n');
}

export function downloadPropertySearchReport(choices: DemoPropertyChoices, result: DemoPropertyResult) {
  const blob = new Blob(['\uFEFF', formatPropertySearchReport(choices, result)], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url; anchor.download = 'fictional-property-search.txt';
    document.body.appendChild(anchor); anchor.click();
  } finally { anchor.remove(); URL.revokeObjectURL(url); }
}
