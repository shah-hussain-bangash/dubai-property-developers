import type { DemoLeadChoices, DemoLeadResult } from './demoLeads';

export function formatDemoLeadReport(choices: DemoLeadChoices, result: DemoLeadResult, createdAt = new Date()): string {
  const lines = ['FICTIONAL LEAD QUALIFICATION REPORT', 'Mock services only - local snapshot', `Created (UTC): ${createdAt.toISOString()}`, '', 'SUBMITTED REQUIREMENTS',
    `Maximum budget: AED ${choices.budget}`, `Location: ${choices.location}`, `Bedrooms: ${choices.bedrooms === 0 ? 'Studio' : choices.bedrooms}`, `Buying timeline: ${choices.timeline} month(s)`, `Purpose: ${choices.purpose === 'investment' ? 'Investment' : 'Own home'}`, '', 'QUALIFICATION'];
  if (result.duplicate) lines.push('Duplicate detected. Qualification was skipped. No new score or second mock CRM write.');
  else {
    lines.push(`Score: ${result.score === null ? 'Not returned' : result.score + '/100'}`, `Category: ${result.category ?? 'Not returned'}`, `Routing queue: ${result.queue ?? 'Not returned'}`, '', 'RETURNED SCORE REASONS');
    if (!result.factors.length) lines.push('No score rule breakdown was returned.');
    result.factors.forEach(factor => lines.push(`${factor.name.replaceAll('_', ' ')}: ${factor.points > 0 ? '+' : ''}${factor.points} points - ${factor.reason}`));
  }
  lines.push('', 'WORKFLOW STEPS');
  if (!result.steps.length) lines.push('No workflow steps were returned.');
  result.steps.forEach(step => lines.push(`${step.name.replaceAll('_', ' ')}: ${step.status}`));
  lines.push('', 'DEMO NOTICE', 'Fictional data and demo scoring rules only. This score is not a credit assessment or a decision about eligibility to buy or rent a property. No messages were sent, no appointment was booked and no property was reserved. The sample leads table remains separate. In-memory demo records clear when the API restarts.', '');
  return lines.join('\n');
}

export function downloadDemoLeadReport(choices: DemoLeadChoices, result: DemoLeadResult) {
  const blob = new Blob(['\uFEFF', formatDemoLeadReport(choices, result)], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url; anchor.download = 'fictional-lead-qualification.txt';
    document.body.appendChild(anchor); anchor.click();
  } finally { anchor.remove(); URL.revokeObjectURL(url); }
}
