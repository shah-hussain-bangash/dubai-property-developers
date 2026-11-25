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
  request.mockImplementation(async path => path === '' ? { configured: true,
    agents: [{ id: 'documents', name: 'Document Agent', status: 'partial' }] }
    : { agent_id: 'documents', sources: [] });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
async function ready() {
  render(<AgentKnowledgePanel />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save source for this agent' })).toBeEnabled());
}
function method(value: string) {
  fireEvent.change(screen.getByLabelText('Add from'), { target: { value } });
}

describe('Knowledge import methods', () => {
  it('switches between upload and URL controls without controlled-input warnings', async () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    await ready();
    for (const mode of ['website', 'text', 'file', 'website', 'file']) method(mode);
    expect(errors.mock.calls.flat().join('\n')).not.toMatch(/uncontrolled input to be controlled|controlled input to be uncontrolled/);
  });

  it.each([
    ['file', 'website'], ['file', 'text'], ['website', 'file'],
    ['website', 'text'], ['text', 'file'], ['text', 'website'],
  ])('requires fresh customer approval when changing from %s to %s', async (from, to) => {
    await ready();
    method(from);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('checkbox')).toBeChecked();
    method(to);
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it('cannot reuse a hidden old file when returning to upload mode', async () => {
    await ready();
    const old = new File(['fictional old PDF'], 'old.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('Choose a file'), { target: { files: [old] } });
    method('website');
    method('file');
    // Exercise handler validation as well as the browser's required-file check.
    fireEvent.submit(screen.getByLabelText('Choose a file').closest('form')!);
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a PDF, text or Markdown file.');
    expect(request.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  });

  it('uploads only a freshly selected file after a method change', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Choose a file'), { target: {
      files: [new File(['old'], 'old.pdf', { type: 'application/pdf' })],
    } });
    fireEvent.click(screen.getByRole('checkbox'));
    method('website');
    method('file');
    const fresh = new File(['Fictional fresh policy.'], 'fresh.md', { type: 'text/markdown' });
    fireEvent.change(screen.getByLabelText('Choose a file'), { target: { files: [fresh] } });
    fireEvent.submit(screen.getByLabelText('Choose a file').closest('form')!);
    expect(await screen.findByText(/Source saved for Document Agent/)).toBeVisible();
    const post = request.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(post?.[0]).toBe('/documents/sources?title=fresh.md&customer_safe=false');
    expect(post?.[1]?.body).toBe(fresh);
  });

  it('preserves visible typing drafts when returning to their input method', async () => {
    await ready();
    method('website');
    fireEvent.change(screen.getByLabelText('Source title'), { target: { value: 'Fictional guide' } });
    fireEvent.change(screen.getByLabelText('Public website link'), { target: { value: 'https://example.test/guide' } });
    method('text');
    fireEvent.change(screen.getByLabelText('Source text'), { target: { value: 'Fictional approved policy.' } });
    method('website');
    expect(screen.getByLabelText('Public website link')).toHaveValue('https://example.test/guide');
    expect(screen.getByLabelText('Source title')).toHaveValue('Fictional guide');
    method('text');
    expect(screen.getByLabelText('Source text')).toHaveValue('Fictional approved policy.');
  });
});
