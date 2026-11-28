import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AgentKnowledgePanel } from '@/features/knowledge/AgentKnowledgePanel';
import { knowledgeRequest } from '@/services/agentKnowledge';

vi.mock('@/services/agentKnowledge', async importOriginal => ({
  ...await importOriginal<typeof import('@/services/agentKnowledge')>(), knowledgeRequest: vi.fn(),
}));
const request = vi.mocked(knowledgeRequest);
const index = { configured: true, agents: [{ id: 'documents', name: 'Document Agent', status: 'partial' }] };
const source = { id: 'fixture', title: 'Fictional saved source', kind: 'text', uri: null,
  chars: 40, created: '2026-11-26T00:00:00Z', review_by: null, customer_safe: 0 };
beforeEach(() => { request.mockReset(); });
afterEach(cleanup);
async function ready() {
  render(<AgentKnowledgePanel />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save source for this agent' })).toBeEnabled());
}

it.each(['file', 'website', 'text'])('reports a saved %s source when only its list refresh fails', async kind => {
  let reads = 0;
  request.mockImplementation(async (path, init) => {
    if (path === '') return index;
    if (init?.method === 'POST') return { agent_id: 'documents', source };
    if (++reads === 1) return { agent_id: 'documents', sources: [] };
    if (reads === 2) throw Error('Fictional list failure');
    return { agent_id: 'documents', sources: [source] };
  });
  await ready();
  fireEvent.change(screen.getByLabelText('Add from'), { target: { value: kind } });
  fireEvent.change(screen.getByLabelText('Source title'), { target: { value: 'Fictional draft' } });
  if (kind === 'file') fireEvent.change(screen.getByLabelText('Choose a file'), { target: {
    files: [new File(['Fictional policy.'], 'fixture.txt', { type: 'text/plain' })],
  } });
  else fireEvent.change(screen.getByLabelText(kind === 'text' ? 'Source text' : 'Public website link'), {
    target: { value: kind === 'text' ? 'Fictional policy.' : 'https://example.test/policy' },
  });
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.submit(screen.getByRole('button', { name: 'Save source for this agent' }).closest('form')!);
  expect(await screen.findByRole('alert')).toHaveTextContent('Source was saved, but the list could not be refreshed.');
  expect(screen.getByText(/Source saved for Document Agent/)).toBeVisible();
  expect(screen.getByLabelText('Source title')).toHaveValue('');
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.queryByText(/No sources for this agent yet/)).toBeNull();
  expect(screen.getByRole('button', { name: 'Refresh sources' })).toBeEnabled();
  if (kind !== 'file') expect(screen.getByLabelText(kind === 'text' ? 'Source text' : 'Public website link')).toHaveValue('');
  expect(request.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh sources' }));
  expect(await screen.findByText(source.title)).toBeVisible();
  expect(screen.queryByRole('alert')).toBeNull();
  expect(request.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
});

it('does not offer to remove an already removed source when its list refresh fails', async () => {
  let reads = 0;
  request.mockImplementation(async (path, init) => {
    if (path === '') return index;
    if (init?.method === 'DELETE') return { removed: true };
    if (++reads === 1) return { agent_id: 'documents', sources: [source] };
    throw Error('Fictional list failure');
  });
  await ready();
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm removal' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Source was removed, but the list could not be refreshed.');
  expect(screen.queryByText(source.title)).toBeNull();
  expect(screen.queryByRole('button', { name: 'Confirm removal' })).toBeNull();
  expect(screen.getByText('Source removed from future answers.')).toBeVisible();
  expect(request.mock.calls.filter(([, init]) => init?.method === 'DELETE')).toHaveLength(1);
});

it('does not claim the source list is empty when loading failed', async () => {
  request.mockImplementation(async path => {
    if (path === '') return index;
    throw Error('Fictional list failure');
  });
  render(<AgentKnowledgePanel />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Sources could not be loaded.');
  expect(screen.queryByText(/No sources for this agent yet/)).toBeNull();
  expect(screen.getByRole('button', { name: 'Refresh sources' })).toBeEnabled();
});

it('retains a draft and does not claim a save when the import request fails', async () => {
  request.mockImplementation(async (path, init) => {
    if (path === '') return index;
    if (init?.method === 'POST') throw Error('Fictional import rejected');
    return { agent_id: 'documents', sources: [] };
  });
  await ready();
  fireEvent.change(screen.getByLabelText('Add from'), { target: { value: 'text' } });
  fireEvent.change(screen.getByLabelText('Source title'), { target: { value: 'Keep this draft' } });
  fireEvent.change(screen.getByLabelText('Source text'), { target: { value: 'Fictional draft policy.' } });
  fireEvent.submit(screen.getByRole('button', { name: 'Save source for this agent' }).closest('form')!);
  expect(await screen.findByRole('alert')).toHaveTextContent('Fictional import rejected');
  expect(screen.getByLabelText('Source title')).toHaveValue('Keep this draft');
  expect(screen.getByLabelText('Source text')).toHaveValue('Fictional draft policy.');
  expect(screen.queryByText(/Source saved for/)).toBeNull();
});

it('retains the source when the removal request fails', async () => {
  request.mockImplementation(async (path, init) => {
    if (path === '') return index;
    if (init?.method === 'DELETE') throw Error('Fictional removal rejected');
    return { agent_id: 'documents', sources: [source] };
  });
  await ready();
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm removal' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Fictional removal rejected');
  expect(screen.getByText(source.title)).toBeVisible();
  expect(screen.queryByText('Source removed from future answers.')).toBeNull();
});
