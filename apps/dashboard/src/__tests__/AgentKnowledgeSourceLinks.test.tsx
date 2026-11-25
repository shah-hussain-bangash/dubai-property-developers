import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AgentKnowledgePanel } from '@/features/knowledge/AgentKnowledgePanel';
import { knowledgeRequest, parseSourceAnswer, type SourceAnswer } from '@/services/agentKnowledge';

vi.mock('@/services/agentKnowledge', async importOriginal => ({
  ...await importOriginal<typeof import('@/services/agentKnowledge')>(), knowledgeRequest: vi.fn(),
}));
const request = vi.mocked(knowledgeRequest);
const answer: SourceAnswer = {
  agent_id: 'documents', answered: true, supplied_sources_only: true, method: 'source-excerpts',
  sent: false, text: '[1] Fictional gardens allow two visits.',
  sources: [{ source_id: 'fictional-website', label: '1', title: 'Fictional website',
    uri: null, page: null, excerpt: 'Fictional gardens allow two visits.' }],
};
function withUri(uri: unknown): SourceAnswer {
  return { ...answer, sources: [{ ...answer.sources[0], uri }] } as SourceAnswer;
}
beforeEach(() => { request.mockReset(); });
afterEach(cleanup);
async function ask(uri: string) {
  request.mockImplementation(async path => path === '' ? { configured: true,
    agents: [{ id: 'documents', name: 'Document Agent', status: 'partial' }] }
    : path.endsWith('/answer') ? withUri(uri) : { agent_id: 'documents', sources: [] });
  render(<AgentKnowledgePanel />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Answer from assigned sources' })).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'fictional gardens' } });
  fireEvent.click(screen.getByRole('button', { name: 'Answer from assigned sources' }));
}

describe('Knowledge source links', () => {
  it.each([
    undefined, 0, true, {}, [], '', 'http://example.test/guide', 'javascript:alert(1)',
    'https://reader@example.test/guide', 'https://example.test:444/guide',
    'https://example.test/guide#part', 'https://example.test/a\npath', 'not a url',
  ].map(uri => [uri]))('rejects malformed or unsupported source URI %j', uri => {
    expect(() => parseSourceAnswer(withUri(uri), 'documents')).toThrow('A source reference is invalid.');
  });

  it.each([
    null, 'https://example.test/guide', 'HTTPS://EXAMPLE.TEST/guide',
    'https://example.test/%D8%AF%D8%A8%D9%8A', 'https://موقع.example/دبي',
  ])('preserves valid source URI %s', uri => {
    const valid = withUri(uri);
    expect(parseSourceAnswer(valid, 'documents')).toEqual(valid);
  });

  it('renders uppercase HTTPS source links without rewriting the saved URI', async () => {
    const uri = 'HTTPS://EXAMPLE.TEST/guide';
    await ask(uri);
    const link = await screen.findByRole('link', { name: 'Open source page ↗' });
    expect(link).toHaveAttribute('href', uri);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('does not render an answer or link with credential-bearing URI metadata', async () => {
    await ask('https://reader@example.test/guide');
    expect(await screen.findByRole('alert')).toHaveTextContent('A source reference is invalid.');
    expect(screen.queryByRole('link', { name: 'Open source page ↗' })).toBeNull();
    expect(screen.queryByText(answer.text)).toBeNull();
  });
});
