import type { DemoReply } from './demoConversations';

export function formatDemoReplyReport(message: string, result: DemoReply, createdAt = new Date()): string {
  const lines = ['FICTIONAL UNSENT SALES REPLY REPORT', 'Mock services only - local snapshot', `Created (UTC): ${createdAt.toISOString()}`, '', 'SUBMITTED FICTIONAL MESSAGE', message, '',
    result.needsHuman ? 'STAFF HANDOFF REQUIRED' : 'DRAFT READY FOR HUMAN REVIEW', `Intent: ${result.intent.replaceAll('_', ' ')}`, `Language: ${result.language === 'ar' ? 'Arabic' : 'English'}`];
  if (result.reason) lines.push(`Handoff reason: ${result.reason}`);
  lines.push('', result.needsHuman ? 'UNSENT ACKNOWLEDGEMENT DRAFT' : 'UNSENT REPLY DRAFT', result.text, '', 'CITED FICTIONAL SOURCES');
  if (!result.citations.length) lines.push('No source citations were returned. No sources have been invented.');
  result.citations.forEach((citation, index) => lines.push(`${index + 1}. ${citation.title}`, `Document version: ${citation.version}`, citation.excerpt, ''));
  lines.push('DEMO NOTICE', 'Fictional messages and demo drafts only. Human review is required before sharing. Nothing was sent, no appointment was booked, no consent was changed and no approval-queue entry was created. Downloading does not approve or send this reply. Confirm prices, availability and payment terms with the developer before quoting. No investment return is implied or guaranteed. The sample conversation list remains separate.', '');
  return lines.join('\n');
}

export function downloadDemoReplyReport(message: string, result: DemoReply) {
  const blob = new Blob(['\uFEFF', formatDemoReplyReport(message, result)], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url; anchor.download = 'fictional-unsent-sales-reply.txt';
    document.body.appendChild(anchor); anchor.click();
  } finally { anchor.remove(); URL.revokeObjectURL(url); }
}
