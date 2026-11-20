import type { LeadSource } from '@/types/domain';

export const LEAD_SOURCE_LABELS: Record<LeadSource, string> = {
  website: 'Website',
  whatsapp: 'WhatsApp',
  portal_listing: 'Listing portal',
  referral: 'Referral',
  social_ads: 'Social ads',
  walk_in: 'Walk-in',
};
