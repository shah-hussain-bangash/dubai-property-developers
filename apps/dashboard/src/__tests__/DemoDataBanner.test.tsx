import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DEMO_BANNER_TEXT, DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { DEMO_AGENTS, DEMO_LEADS, DEMO_WORKFLOWS } from '@/lib/demo-data';

describe('DemoDataBanner', () => {
  it('renders the default demo notice', () => {
    render(<DemoDataBanner />);
    const banner = screen.getByRole('note', { name: 'Demo data notice' });
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent(DEMO_BANNER_TEXT);
    expect(DEMO_BANNER_TEXT).toBe('Demo data — not live records');
  });

  it('renders optional detail text', () => {
    render(<DemoDataBanner>All leads are fictional.</DemoDataBanner>);
    expect(screen.getByTestId('demo-data-banner')).toHaveTextContent('All leads are fictional.');
  });
});

describe('demo data honesty', () => {
  it('uses obviously fictional contact details', () => {
    for (const lead of DEMO_LEADS) {
      expect(lead.name).toMatch(/^Demo Lead \d{2}$/);
      expect(lead.email).toMatch(/@example\.com$/);
      expect(lead.phone).toMatch(/^\+971 50 000 00\d{2}$/);
    }
  });

  it('lists all 13 agents and 6 workflows from the backend contract', () => {
    expect(DEMO_AGENTS.map((a) => a.agent_id)).toEqual([
      'supervisor',
      'lead_intake',
      'qualification',
      'property_recommendation',
      'sales_conversation',
      'followup',
      'crm',
      'email',
      'whatsapp',
      'voice',
      'marketing',
      'documents',
      'analytics',
    ]);
    expect(DEMO_AGENTS.find((a) => a.agent_id === 'voice')?.implementation_status).toBe('interface_only');
    expect(DEMO_WORKFLOWS).toHaveLength(6);
  });
});
