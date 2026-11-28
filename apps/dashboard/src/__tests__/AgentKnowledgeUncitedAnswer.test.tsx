import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AgentKnowledgePanel } from '@/features/knowledge/AgentKnowledgePanel';
import { knowledgeRequest, parseSourceAnswer, type SourceAnswer } from '@/services/agentKnowledge';

vi.mock('@/services/agentKnowledge', async importOriginal => ({
  ...await importOriginal<typeof import('@/services/agentKnowledge')>(),
  knowledgeRequest: vi.fn(),
}));

const noAnswer: SourceAnswer = {
  agent_id: 'documents', answered: false, supplied_sources_only: true,
  method: 'source-excerpts', sent: false,
  text: "I could not find an answer in this agent's supplied sources. Add a relevant source or ask a more specific question.",
  sources: [],
};
const request = vi.mocked(knowledgeRequest);

beforeEach(() => { request.mockReset(); });
afterEach(cleanup);

describe('uncited knowledge responses', () => {
  it.each([
    'The fictional payment plan requires ninety percent.',
    '',
    '[1] Fictional quoted text without a source.',
    'A different unsupported response.',
  ])('rejects arbitrary text when the service reports no sources: %s', text => {
    expect(() => parseSourceAnswer({ ...noAnswer, text }, 'documents'))
      .toThrow('The source answer could not be verified.');
  });

  it('accepts the documented no-answer message without inventing a citation', () => {
    expect(parseSourceAnswer(noAnswer, 'documents')).toEqual(noAnswer);
  });

  it('does not display an unsupported claim in the Knowledge page', async () => {
    const claim = 'The fictional payment plan requires ninety percent.';
    request.mockImplementation(async path => {
      if (path === '') return {
        configured: true,
        agents: [{ id: 'documents', name: 'Document Agent', status: 'partial' }],
      };
      if (path.endsWith('/answer')) return { ...noAnswer, text: claim };
      return { agent_id: 'documents', sources: [] };
    });
    render(<AgentKnowledgePanel />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Answer from assigned sources' })).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'fictional payment plan' } });
    fireEvent.click(screen.getByRole('button', { name: 'Answer from assigned sources' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The source answer could not be verified.');
    expect(screen.queryByText(claim)).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Not found in this agent’s sources' })).toBeNull();
  });
});
