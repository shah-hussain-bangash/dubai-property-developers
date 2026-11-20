/**
 * Deterministic formatters. They avoid Intl/locale differences between the
 * Node.js server and the browser so server and client renders always match.
 * Times are shown in Dubai time (UTC+4, no daylight saving).
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DUBAI_OFFSET_MS = 4 * 60 * 60 * 1000;

function pad2(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

function toDubai(iso: string): Date | null {
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return null;
  return new Date(time + DUBAI_OFFSET_MS);
}

/** e.g. "08 Oct 2026" */
export function formatDate(iso: string): string {
  const d = toDubai(iso);
  if (!d) return '—';
  return `${pad2(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** e.g. "08 Oct 2026, 14:05" (Dubai time) */
export function formatDateTime(iso: string): string {
  const d = toDubai(iso);
  if (!d) return '—';
  return `${formatDate(iso)}, ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;
}

/** e.g. "14:05" (Dubai time) */
export function formatTime(iso: string): string {
  const d = toDubai(iso);
  if (!d) return '—';
  return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;
}

/** Thousands separators without relying on locale data, e.g. 1250000 → "1,250,000". */
export function formatNumber(value: number, fractionDigits = 0): string {
  const fixed = Math.abs(value).toFixed(fractionDigits);
  const [whole, fraction] = fixed.split('.');
  const grouped = (whole ?? '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const sign = value < 0 ? '-' : '';
  return fraction ? `${sign}${grouped}.${fraction}` : `${sign}${grouped}`;
}

/** e.g. 0.423 → "42.3%" */
export function formatPercent(ratio: number, fractionDigits = 1): string {
  return `${(ratio * 100).toFixed(fractionDigits)}%`;
}

/** Turns snake_case or kebab-case identifiers into "Sentence case". */
export function humanize(identifier: string): string {
  const spaced = identifier.replace(/[_-]+/g, ' ').trim();
  if (spaced.length === 0) return identifier;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

/** Whole days between two ISO timestamps (b - a). */
export function daysBetween(fromIso: string, toIso: string): number {
  const from = Date.parse(fromIso);
  const to = Date.parse(toIso);
  if (Number.isNaN(from) || Number.isNaN(to)) return 0;
  return Math.floor((to - from) / (24 * 60 * 60 * 1000));
}
