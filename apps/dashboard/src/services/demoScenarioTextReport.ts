import type { ScenarioChoices, ScenarioResult } from './demoScenario';
import { buildScenarioReport } from './demoScenarioReport';

export function formatScenarioText(choices: ScenarioChoices, result: ScenarioResult, createdAt = new Date()): string {
  const report = buildScenarioReport(choices, result, createdAt);
  const outcomes = { completed: 'Demo completed; reply awaits human review', duplicate: 'Duplicate stopped before matching', no_matches: 'No fictional properties match' };
  const lines = ['FICTIONAL GUIDED WORKFLOW DEMO', 'Mock services only - local snapshot',
    `Created (UTC): ${report.created_at}`, `Outcome: ${outcomes[report.outcome]}`, '',
    'FICTIONAL REQUIREMENTS', `Maximum budget: AED ${report.requirements.budget_max_aed}`,
    `Location: ${report.requirements.location}`, `Bedrooms: ${report.requirements.bedrooms}`,
    'Property type: Apartment', 'Purpose: Investment', '', '1. QUALIFICATION'];
  if (report.qualification.duplicate) lines.push('Duplicate. No second mock CRM write.');
  else lines.push(`Score: ${report.qualification.score}/100`, `Category: ${report.qualification.category}`, `Routing queue: ${report.qualification.queue}`);
  lines.push('', 'Qualification rule breakdown:');
  if (report.qualification.breakdown_status === 'duplicate_skipped') lines.push('Duplicate detection stopped qualification. No new score was calculated.');
  else if (report.qualification.breakdown_status === 'not_returned') lines.push('No rule breakdown was returned for this run.');
  else for (const factor of report.qualification.factors) lines.push(`${factor.name.replaceAll('_', ' ')}: ${factor.points > 0 ? '+' : ''}${factor.points} points - ${factor.reason}`);
  lines.push(report.qualification.explanation);
  lines.push('', '2. FICTIONAL PROPERTY MATCHING');
  const properties = report.property_matching;
  if (properties === null) lines.push('Skipped.');
  else {
    if (!properties.matches.length) lines.push(properties.no_match_reason || 'No fictional matches.');
    properties.matches.forEach((match, index) => {
      lines.push('', `${index + 1}. ${match.project}`, `${match.community} | ${match.bedrooms} bedroom(s)`,
        match.price_aed === null ? 'Price: Not confirmed' : `Fictional price: AED ${match.price_aed}`,
        `Source: ${match.source} | As of: ${match.data_as_of}`, `Availability: ${match.availability}`,
        'Reasons:', ...match.reasons.map(reason => `- ${reason}`), 'Caveats:', ...match.caveats.map(caveat => `- ${caveat}`));
    });
    lines.push('', properties.disclaimer);
  }
  lines.push('', '3. UNSENT VIEWING REPLY');
  if (report.viewing_reply === null) lines.push('Skipped. No reply prepared.');
  else {
    lines.push('Human review required. Nothing sent. No appointment booked.', report.viewing_reply.text);
    if (report.viewing_reply.needs_staff_handoff) lines.push(`Staff handoff required: ${report.viewing_reply.handoff_reason || 'Review needed.'}`);
    for (const citation of report.viewing_reply.citations) lines.push(`Source: ${citation.title} (version ${citation.version})`, citation.excerpt);
  }
  lines.push('', 'DEMO NOTICE', report.notice, '');
  return lines.join('\n');
}

export function downloadScenarioText(choices: ScenarioChoices, result: ScenarioResult) {
  const blob = new Blob(['\uFEFF', formatScenarioText(choices, result)], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url; anchor.download = 'fictional-workflow-demo.txt';
    document.body.appendChild(anchor); anchor.click();
  } finally { anchor.remove(); URL.revokeObjectURL(url); }
}
