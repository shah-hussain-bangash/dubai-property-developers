import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AgentKnowledgePanel } from '@/features/knowledge/AgentKnowledgePanel';
import { knowledgeRequest, parseSourceAnswer, type SourceAnswer } from '@/services/agentKnowledge';

vi.mock('@/services/agentKnowledge', async importOriginal => ({
  ...await importOriginal<typeof import('@/services/agentKnowledge')>(), knowledgeRequest: vi.fn(),
}));
const request = vi.mocked(knowledgeRequest);
const answer: SourceAnswer = {
  agent_id: 'documents', answered: true, supplied_sources_only: true,
  method: 'source-excerpts', sent: false, text: '[1] Fictional gardens allow two visits.',
  sources: [{ source_id: 'fictional-source', label: '1', title: 'Fictional PDF',
    uri: null, page: 1, excerpt: 'Fictional gardens allow two visits.' }],
};
function withReference(fields: Record<string, unknown>): SourceAnswer {
  return { ...answer, sources: [{ ...answer.sources[0], ...fields }] } as SourceAnswer;
}
beforeEach(() => { request.mockReset(); });
afterEach(cleanup);

describe('source citation metadata', () => {
  it.each([0, -1, 1.5, 101, '2', true, undefined])('rejects invalid PDF page %s', page => {
    expect(() => parseSourceAnswer(withReference({ page }), 'documents'))
      .toThrow('A source reference is invalid.');
  });

  it('rejects a null citation with a bounded verification error', () => {
    const malformed = { ...answer, sources: [null] } as unknown as SourceAnswer;
    expect(() => parseSourceAnswer(malformed, 'documents')).toThrow('A source reference is invalid.');
  });

  it.each([{ title: '' }, { title: '   ' }, { source_id: '' }, { source_id: '\t' }])(
    'rejects an empty citation identity or title: %j', fields => {
      expect(() => parseSourceAnswer(withReference(fields), 'documents'))
        .toThrow('A source reference is invalid.');
    },
  );

  it.each([1, 100, null])('accepts supported page metadata %s', page => {
    const valid = withReference({ page });
    expect(parseSourceAnswer(valid, 'documents')).toEqual(valid);
  });

  it('does not display an answer with an invalid page reference', async () => {
    request.mockImplementation(async path => {
      if (path === '') return { configured: true,
        agents: [{ id: 'documents', name: 'Document Agent', status: 'partial' }] };
      if (path.endsWith('/answer')) return withReference({ page: -2 });
      return { agent_id: 'documents', sources: [] };
    });
    render(<AgentKnowledgePanel />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Answer from assigned sources' })).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'fictional gardens' } });
    fireEvent.click(screen.getByRole('button', { name: 'Answer from assigned sources' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('A source reference is invalid.');
    expect(screen.queryByText(answer.text)).toBeNull();
    expect(screen.queryByText('[1] Fictional PDF · Page -2')).toBeNull();
  });
});
