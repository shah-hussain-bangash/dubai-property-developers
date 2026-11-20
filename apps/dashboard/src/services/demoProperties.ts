import { getApiBaseUrl, getApiCredentials } from '@/lib/config';

export interface DemoPropertyChoices {
  budget: string;
  location: string;
  bedrooms: string;
  paymentPlan: boolean;
}
export interface DemoPropertyMatch {
  id: string;
  name: string;
  community: string;
  bedrooms: number;
  price: string | null;
  date: string;
  availability: string;
  score: number;
  reasons: string[];
  caveats: string[];
}
export interface DemoPropertyResult { matches: DemoPropertyMatch[]; disclaimer: string; noMatch: string | null }
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const textList = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string');

export function parsePropertyDemo(body: unknown): DemoPropertyResult {
  if (!record(body) || body.dev_only !== true || body.uses_mock_integrations !== true || body.status !== 'succeeded'
      || !record(body.output) || !Array.isArray(body.output.recommendations) || body.output.recommendations.length > 5
      || typeof body.output.disclaimer !== 'string' || !body.output.disclaimer.includes('must be confirmed')
      || !body.output.disclaimer.includes('No investment return') || typeof body.output.contains_demo_data !== 'boolean') {
    throw new Error('Invalid fictional property result.');
  }
  const matches = body.output.recommendations.map((item: unknown): DemoPropertyMatch => {
    if (!record(item) || !record(item.listing) || item.listing.is_demo !== true || item.listing.source !== 'demo-seed'
        || typeof item.score !== 'number' || !Number.isFinite(item.score) || item.score < 0 || item.score > 1
        || !textList(item.reasons) || !textList(item.caveats)
        || !item.caveats.some(value => value.includes('DEMO DATA')) || !item.caveats.some(value => value.includes('guaranteed'))) {
      throw new Error('Invalid fictional property match.');
    }
    const listing = item.listing;
    if (typeof listing.listing_id !== 'string' || typeof listing.project_name !== 'string'
        || typeof listing.community !== 'string' || typeof listing.bedrooms !== 'number'
        || !Number.isInteger(listing.bedrooms) || listing.bedrooms < 0
        || typeof listing.data_as_of !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(listing.data_as_of)
        || typeof listing.availability !== 'string'
        || (listing.price_aed !== null && (typeof listing.price_aed !== 'string' || !/^\d+(\.\d+)?$/.test(listing.price_aed)
          || !Number.isFinite(Number(listing.price_aed)) || Number(listing.price_aed) <= 0))
        || (listing.price_aed === null && !item.caveats.some(value => value.includes('Price not confirmed')))) {
      throw new Error('Incomplete fictional listing.');
    }
    return { id: listing.listing_id, name: listing.project_name, community: listing.community,
      bedrooms: listing.bedrooms, price: listing.price_aed, date: listing.data_as_of, availability: listing.availability,
      score: item.score, reasons: item.reasons, caveats: item.caveats };
  });
  if (body.output.contains_demo_data !== (matches.length > 0)
      || (matches.length === 0 && (typeof body.output.no_match_reason !== 'string' || !body.output.no_match_reason))) {
    throw new Error('Inconsistent fictional property result.');
  }
  return { matches, disclaimer: body.output.disclaimer, noMatch: matches.length ? null : body.output.no_match_reason as string };
}

export async function matchDemoProperties(choices: DemoPropertyChoices, signal: AbortSignal): Promise<DemoPropertyResult> {
  if (!/^\d{1,10}$/.test(choices.budget) || Number(choices.budget) <= 0
      || !['any', 'Business Bay', 'Dubai Marina', 'Jumeirah Village Circle'].includes(choices.location)
      || !['any', '0', '1', '2', '3', '4', '5'].includes(choices.bedrooms) || typeof choices.paymentPlan !== 'boolean') {
    throw new Error('Choose valid demo property requirements.');
  }
  const base = new URL(getApiBaseUrl());
  if (base.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)
      || base.username || base.password || base.pathname !== '/' || base.search || base.hash) {
    throw new Error('Property matching requires a local demo API.');
  }
  const request = { credentials: getApiCredentials(), redirect: 'error' as const, cache: 'no-store' as const, signal };
  const available = await fetch(base.origin + '/api/v1/leads/demo-capabilities', request);
  if (!available.ok) throw new Error('The local demo API is unavailable.');
  const capability: unknown = await available.json();
  if (!record(capability) || capability.enabled !== true || capability.mock_integrations !== true || capability.memory_storage !== true) {
    throw new Error('The local demo API could not be confirmed.');
  }
  const response = await fetch(base.origin + '/api/v1/properties/demo-recommendations', {
    ...request, method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ budget_max_aed: choices.budget, locations: choices.location === 'any' ? [] : [choices.location],
      bedrooms_min: choices.bedrooms === 'any' ? null : Number(choices.bedrooms),
      bedrooms_max: choices.bedrooms === 'any' ? null : Number(choices.bedrooms),
      require_payment_plan: choices.paymentPlan, include_unavailable: false, limit: 3 }),
  });
  if (!response.ok) throw new Error('The demo property workflow did not complete.');
  return parsePropertyDemo(await response.json());
}
