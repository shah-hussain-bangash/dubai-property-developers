export const DEFAULT_API_BASE_URL = 'http://localhost:8000';

/**
 * Base URL of the backend API. `process.env.NEXT_PUBLIC_API_BASE_URL` must be
 * referenced literally so Next.js can inline it into the client bundle.
 */
export function getApiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_PORTAL_PROXY === '1') return typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000';
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (typeof configured === 'string' && configured.trim().length > 0) {
    return configured.trim();
  }
  return DEFAULT_API_BASE_URL;
}

export const APP_NAME = 'Dubai Real Estate AI';
export const APP_TAGLINE = 'Multi-agent operations console';

export function getApiCredentials(): RequestCredentials { return process.env.NEXT_PUBLIC_PORTAL_PROXY === '1' ? 'same-origin' : 'omit'; }
