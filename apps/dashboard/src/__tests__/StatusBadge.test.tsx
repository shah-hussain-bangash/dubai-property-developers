import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusBadge, labelForStatus, toneForStatus } from '@/components/ui/StatusBadge';

describe('StatusBadge', () => {
  it('renders a humanised status label', () => {
    render(<StatusBadge status="functional" />);
    expect(screen.getByText('Functional')).toBeInTheDocument();
  });

  it('uses friendly labels for known multi-word statuses', () => {
    render(<StatusBadge status="interface_only" />);
    expect(screen.getByText('Interface only')).toBeInTheDocument();
  });

  it('prefers an explicit label and tone', () => {
    render(<StatusBadge status="anything" label="Custom label" tone="gold" />);
    const badge = screen.getByText('Custom label');
    expect(badge).toHaveAttribute('data-tone', 'gold');
    expect(badge).toHaveAttribute('data-status', 'anything');
  });

  it('maps statuses to tones with a neutral default', () => {
    expect(toneForStatus('functional')).toBe('success');
    expect(toneForStatus('partial')).toBe('warning');
    expect(toneForStatus('unknown_status')).toBe('neutral');
    expect(labelForStatus('pending_approval')).toBe('Pending approval');
  });
});
