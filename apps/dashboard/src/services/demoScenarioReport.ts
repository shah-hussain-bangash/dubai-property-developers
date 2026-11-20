import type { ScenarioChoices, ScenarioResult } from './demoScenario';

export function buildScenarioReport(choices: ScenarioChoices, result: ScenarioResult, createdAt = new Date()) {
  return {
    report_version: 2,
    title: 'Fictional guided workflow demo',
    created_at: createdAt.toISOString(),
    fictional_data: true,
    mock_integrations: true,
    outcome: result.status,
    requirements: { budget_max_aed: choices.budget, location: choices.location, bedrooms: choices.bedrooms, property_type: 'apartment', purpose: 'investment' },
    qualification: { duplicate: result.lead.duplicate, score: result.lead.score, category: result.lead.category, queue: result.lead.queue,
      breakdown_status: result.lead.duplicate ? 'duplicate_skipped' : result.lead.factors.length ? 'provided' : 'not_returned',
      factors: result.lead.duplicate ? [] : result.lead.factors.map(factor => ({ name: factor.name, points: factor.points, reason: factor.reason })),
      explanation: 'Qualification score and property availability are separate checks. A high score does not mean a property is available within the chosen budget.',
    },
    property_matching: result.properties === null ? null : {
      no_match_reason: result.properties.noMatch,
      disclaimer: result.properties.disclaimer,
      matches: result.properties.matches.map(match => ({
        project: match.name, community: match.community, bedrooms: match.bedrooms,
        price_aed: match.price, source: 'demo-seed', data_as_of: match.date,
        availability: match.availability, score: match.score,
        reasons: [...match.reasons], caveats: [...match.caveats],
      })),
    },
    viewing_reply: result.reply === null ? null : {
      text: result.reply.text, intent: result.reply.intent, language: result.reply.language,
      requires_human_review: true, sent: false, appointment_booked: false,
      needs_staff_handoff: result.reply.needsHuman, handoff_reason: result.reply.reason,
      citations: result.reply.citations.map(citation => ({ title: citation.title, version: citation.version, excerpt: citation.excerpt })),
    },
    notice: 'Fictional demo only. No message was sent, appointment booked or approval-queue entry created. Prices, availability, payment plans and handover dates require developer confirmation. No investment return is implied or guaranteed. This report is a local snapshot, not a live record.',
  };
}

export function downloadScenarioReport(choices: ScenarioChoices, result: ScenarioResult) {
  const blob = new Blob([JSON.stringify(buildScenarioReport(choices, result), null, 2) + '\n'], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url;
    anchor.download = 'fictional-workflow-demo.json';
    document.body.appendChild(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(url);
  }
}
