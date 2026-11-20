import type { DemoKnowledgeResult } from './demoKnowledge';

export function formatDemoKnowledgeReport(question: string, result: DemoKnowledgeResult, createdAt = new Date()): string {
  const lines = ['FICTIONAL KNOWLEDGE ANSWER REPORT', 'Public fictional documents only - local snapshot', `Created (UTC): ${createdAt.toISOString()}`, '', 'SUBMITTED QUESTION', question, '',
    result.needsHuman ? 'HUMAN HANDOFF NEEDED' : 'DRAFT ANSWER - REVIEW BEFORE SHARING', result.answer ?? 'No sufficiently relevant public demo passage was found. Ask a staff member to review this question.', '', 'RETURNED REVIEW NOTES'];
  if (!result.notes.length) lines.push('No additional review notes were returned.');
  result.notes.forEach(note => lines.push(`- ${note}`));
  lines.push('', 'CITED FICTIONAL SOURCES');
  if (!result.citations.length) lines.push('No source citations were returned. No answer or source has been invented.');
  result.citations.forEach((citation, index) => lines.push(`${index + 1}. ${citation.title}`, `Document version: ${citation.version}`, citation.excerpt, ''));
  lines.push('DEMO NOTICE', 'Fictional documents and demo drafts only. This is not an approved customer reply. Human review is required before sharing. No message was sent. Confirm current prices, availability and payment terms with the developer before quoting. No investment return is implied or guaranteed. The sample document table remains separate.', '');
  return lines.join('\n');
}

export function downloadDemoKnowledgeReport(question: string, result: DemoKnowledgeResult) {
  const blob = new Blob(['\uFEFF', formatDemoKnowledgeReport(question, result)], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url; anchor.download = 'fictional-knowledge-answer.txt';
    document.body.appendChild(anchor); anchor.click();
  } finally { anchor.remove(); URL.revokeObjectURL(url); }
}
