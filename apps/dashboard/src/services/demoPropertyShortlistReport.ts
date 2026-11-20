import type { DemoPropertyMatch } from './demoProperties';

export function formatPropertyShortlist(items: DemoPropertyMatch[], createdAt = new Date()): string {
  if (items.length < 1 || items.length > 3 || new Set(items.map(item => item.id)).size !== items.length) throw new Error('Choose one to three distinct fictional properties.');
  const lines = ['FICTIONAL PROPERTY SHORTLIST', 'Local demo snapshots only', `Created (UTC): ${createdAt.toISOString()}`, `Fictional properties: ${items.length}`, 'Match scores reflect the criteria used in each original search.'];
  items.forEach((item, index) => {
    lines.push('', `${index + 1}. ${item.name}`, `Community: ${item.community}`, item.bedrooms === 0 ? 'Bedrooms: Studio' : `Bedrooms: ${item.bedrooms}`,
      item.price === null ? 'Price: Not confirmed\nBudget fit not verified: price is unconfirmed.' : `Illustrative price: AED ${item.price}`,
      `Source: demo-seed | Data as of: ${item.date}`, `Catalog status: ${item.availability}${item.availability === 'unknown' ? '\nAvailability not verified: confirm before offering.' : ''}`,
      `Demo match score: ${Math.round(item.score * 100)}/100`, 'Reasons:', ...item.reasons.map(reason => `- ${reason}`), 'Caveats:', ...item.caveats.map(caveat => `- ${caveat}`));
  });
  lines.push('', 'DEMO NOTICE', 'Fictional demo only. Prices, availability, payment plans and handover dates must be confirmed with the developer. No investment return is implied or guaranteed. Shortlisting does not reserve a property or send an enquiry. This file is a snapshot of earlier searches, not a live record.', '');
  return lines.join('\n');
}

export function downloadPropertyShortlist(items: DemoPropertyMatch[]) {
  const blob = new Blob(['\uFEFF', formatPropertyShortlist(items)], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url; anchor.download = 'fictional-property-shortlist.txt';
    document.body.appendChild(anchor); anchor.click();
  } finally { anchor.remove(); URL.revokeObjectURL(url); }
}
