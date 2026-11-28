import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AgentKnowledgePanel } from '@/features/knowledge/AgentKnowledgePanel';
import { knowledgeRequest } from '@/services/agentKnowledge';

vi.mock('@/services/agentKnowledge', async importOriginal => ({
  ...await importOriginal<typeof import('@/services/agentKnowledge')>(), knowledgeRequest: vi.fn(),
}));
const request = vi.mocked(knowledgeRequest);
beforeEach(() => {
  request.mockReset();
  request.mockImplementation(async (path, init) => {
    if (path === '') return { configured: true,
      agents: [{ id: 'documents', name: 'Document Agent', status: 'partial' }] };
    if (init?.method === 'POST') {
      const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
      const query = new URLSearchParams(path.split('?')[1] ?? '');
      const mime = (init.headers as Record<string,string>)?.['Content-Type'];
      return { agent_id: path.split('/')[1], source: {
        id: 'fixture', title: body.title ?? query.get('title') ?? 'Fictional source',
        kind: body.kind ?? (mime === 'application/pdf' ? 'pdf' : mime === 'text/markdown' ? 'markdown' : 'text'),
        uri: body.kind === 'website' ? body.url : null, chars: 40,
        created: '2026-11-26T00:00:00Z', review_by: body.review_by ?? query.get('review_by') ?? null,
        customer_safe: (body.customer_safe ?? (query.get('customer_safe') === 'true')) ? 1 : 0,
      } };
    }
    return { agent_id: 'documents', sources: [] };
  });
});
afterEach(cleanup);
async function ready(mode: string) {
  render(<AgentKnowledgePanel />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save source for this agent' })).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Add from'), { target: { value: mode } });
  fireEvent.change(screen.getByLabelText('Source title'), { target: { value: 'Fictional source' } });
  if (mode === 'file') fireEvent.change(screen.getByLabelText('Choose a file'), { target: {
    files: [new File(['Fictional original file.'], 'original.txt', { type: 'text/plain' })],
  } });
  if (mode === 'website') fireEvent.change(screen.getByLabelText('Public website link'), {
    target: { value: 'https://example.test/original' },
  });
  if (mode === 'text') fireEvent.change(screen.getByLabelText('Source text'), {
    target: { value: 'Fictional original policy.' },
  });
}
function submit() {
  fireEvent.submit(screen.getByRole('button', { name: 'Save source for this agent' }).closest('form')!);
}

describe('customer approval belongs to the current source draft', () => {
  it.each(['file', 'website', 'text', 'title'])(
    'clears customer approval after changing the %s and saves the edited source as staff-only', async field => {
      await ready(field === 'title' ? 'text' : field);
      fireEvent.click(screen.getByRole('checkbox'));
      const replacement = new File(['Fictional replacement file.'], 'replacement.txt', { type: 'text/plain' });
      if (field === 'file') fireEvent.change(screen.getByLabelText('Choose a file'), { target: { files: [replacement] } });
      if (field === 'website') fireEvent.change(screen.getByLabelText('Public website link'), { target: { value: 'https://example.test/replacement' } });
      if (field === 'text') fireEvent.change(screen.getByLabelText('Source text'), { target: { value: 'Fictional replacement policy.' } });
      if (field === 'title') fireEvent.change(screen.getByLabelText('Source title'), { target: { value: 'Fictional replacement title' } });
      expect(screen.getByRole('checkbox')).not.toBeChecked();
      submit();
      expect(await screen.findByText(/Source saved for Document Agent/)).toBeVisible();
      const post = request.mock.calls.find(([, init]) => init?.method === 'POST');
      if (field === 'file') {
        expect(post?.[0]).toContain('customer_safe=false');
        expect(post?.[1]?.body).toBe(replacement);
      } else {
        const payload = JSON.parse(post?.[1]?.body as string);
        expect(payload.customer_safe).toBe(false);
        if (field === 'website') expect(payload.url).toBe('https://example.test/replacement');
        if (field === 'text') expect(payload.text).toBe('Fictional replacement policy.');
        if (field === 'title') expect(payload.title).toBe('Fictional replacement title');
      }
    },
  );

  it.each(['file', 'website', 'text'])('allows explicit approval after final %s edits', async mode => {
    await ready(mode);
    fireEvent.click(screen.getByRole('checkbox'));
    submit();
    expect(await screen.findByText(/Source saved for Document Agent/)).toBeVisible();
    const post = request.mock.calls.find(([, init]) => init?.method === 'POST');
    if (mode === 'file') expect(post?.[0]).toContain('customer_safe=true');
    else expect(JSON.parse(post?.[1]?.body as string).customer_safe).toBe(true);
  });

  it('does not revoke source approval when only the test question changes', async () => {
    await ready('text');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'fictional source question' } });
    expect(screen.getByRole('checkbox')).toBeChecked();
    expect(request.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  });
});
