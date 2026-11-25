import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AgentKnowledgePanel } from '@/features/knowledge/AgentKnowledgePanel';
import { knowledgeRequest, type AssignedSource, type SourceAnswer } from '@/services/agentKnowledge';

vi.mock('@/services/agentKnowledge', async importOriginal => ({
  ...await importOriginal<typeof import('@/services/agentKnowledge')>(), knowledgeRequest: vi.fn(),
}));
const request = vi.mocked(knowledgeRequest);
const index = { configured: true, agents: [
  { id: 'documents', name: 'Document Agent', status: 'partial' },
  { id: 'marketing', name: 'Marketing Agent', status: 'partial' },
] };
function answer(agent: string): SourceAnswer {
  const excerpt = `Fictional ${agent} policy allows two visits.`;
  return { agent_id: agent, answered: true, supplied_sources_only: true, method: 'source-excerpts',
    sent: false, text: `[1] ${excerpt}`, sources: [{ source_id: agent, label: '1',
      title: `Fictional ${agent} guide`, uri: null, page: null, excerpt }] };
}
function source(agent: string): AssignedSource {
  return { id: agent, title: `Fictional ${agent} source`, kind: 'text', uri: null,
    chars: 40, created: '2026-11-25T00:00:00Z', review_by: null, customer_safe: 0 };
}
beforeEach(() => {
  request.mockReset();
  request.mockImplementation(async path => path === '' ? index
    : path.endsWith('/answer') ? answer(path.split('/')[1])
    : { agent_id: path.split('/')[1], sources: [] });
});
afterEach(cleanup);
async function ready() {
  render(<AgentKnowledgePanel />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Answer from assigned sources' })).toBeEnabled());
}

describe('agent knowledge selection', () => {
  it('clears the old question along with source drafts when selecting another agent', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'fictional document question' } });
    fireEvent.change(screen.getByLabelText('Add from'), { target: { value: 'text' } });
    fireEvent.change(screen.getByLabelText('Source title'), { target: { value: 'Old source title' } });
    fireEvent.change(screen.getByLabelText('Source text'), { target: { value: 'Old source content.' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText('Agent'), { target: { value: 'marketing' } });
    expect(screen.getByLabelText('Question')).toHaveValue('');
    expect(screen.getByLabelText('Source title')).toHaveValue('');
    expect(screen.getByLabelText('Source text')).toHaveValue('');
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(request.mock.calls.filter(([path]) => path.endsWith('/answer'))).toHaveLength(0);
  });

  it('sends a newly entered question only to the newly selected agent', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'old document question' } });
    fireEvent.change(screen.getByLabelText('Agent'), { target: { value: 'marketing' } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Answer from assigned sources' })).toBeEnabled());
    expect(screen.getByLabelText('Question')).toHaveValue('');
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'new marketing question' } });
    fireEvent.click(screen.getByRole('button', { name: 'Answer from assigned sources' }));
    expect(await screen.findByText(answer('marketing').text)).toBeVisible();
    const calls = request.mock.calls.filter(([path]) => path.endsWith('/answer'));
    expect(calls).toHaveLength(1);
    expect(calls[0][0]).toBe('/marketing/answer');
    expect(JSON.parse(calls[0][1]?.body as string)).toEqual({ question: 'new marketing question' });
  });

  it('does not restore old sources when an aborted source request resolves late', async () => {
    let finish!: (value: { agent_id: string; sources: AssignedSource[] }) => void;
    const oldSources = new Promise<{ agent_id: string; sources: AssignedSource[] }>(resolve => { finish = resolve; });
    request.mockImplementation(async path => path === '' ? index
      : path === '/documents/sources' ? oldSources
      : { agent_id: 'marketing', sources: [source('marketing')] });
    render(<AgentKnowledgePanel />);
    await waitFor(() => expect(request).toHaveBeenCalledWith('/documents/sources', {}, expect.any(AbortSignal)));
    fireEvent.change(screen.getByLabelText('Agent'), { target: { value: 'marketing' } });
    expect(await screen.findByText('Fictional marketing source')).toBeVisible();
    await act(async () => { finish({ agent_id: 'documents', sources: [source('documents')] }); });
    expect(screen.queryByText('Fictional documents source')).toBeNull();
    expect(screen.getByText('Fictional marketing source')).toBeVisible();
  });

  it('keeps selection locked during an answer and restores it after completion', async () => {
    let finish!: (value: SourceAnswer) => void;
    const pending = new Promise<SourceAnswer>(resolve => { finish = resolve; });
    request.mockImplementation(async path => path === '' ? index
      : path.endsWith('/answer') ? pending : { agent_id: 'documents', sources: [] });
    await ready();
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'fictional document policy' } });
    fireEvent.click(screen.getByRole('button', { name: 'Answer from assigned sources' }));
    expect(screen.getByLabelText('Agent')).toBeDisabled();
    await act(async () => { finish(answer('documents')); });
    expect(await screen.findByText(answer('documents').text)).toBeVisible();
    expect(screen.getByLabelText('Agent')).toBeEnabled();
    expect(screen.getByLabelText('Question')).toHaveValue('fictional document policy');
  });
});
