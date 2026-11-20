// Exact browser-origin checks shared by sign-in, portal writes and enquiry tickets.
// Forwarded headers are deliberately not trusted for choosing an allowed origin.
function configuredOrigin(): URL | null {
  const value = process.env.DUBAI_PORTAL_PUBLIC_ORIGIN;
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password ||
        (value !== url.origin && value !== url.origin + '/')) return null;
    return url;
  } catch { return null; }
}

export function allowedPortalHost(request: Request): boolean {
  const host = request.headers.get('host') || new URL(request.url).host;
  return /^(localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?$/.test(host) ||
    configuredOrigin()?.host === host;
}

export function samePortalOrigin(request: Request): boolean {
  const host = request.headers.get('host') || new URL(request.url).host;
  const origin = request.headers.get('origin');
  if (/^(localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?$/.test(host)) {
    return origin === `http://${host}` || origin === `https://${host}`;
  }
  const configured = configuredOrigin();
  return !!configured && host === configured.host && origin === configured.origin;
}

export function enquiryTicketOriginAllowed(request: Request): boolean {
  if (!allowedPortalHost(request) || request.headers.get('sec-fetch-site') === 'cross-site') return false;
  // Same-origin browser GETs normally omit Origin; mutations must still supply it.
  return !request.headers.has('origin') || samePortalOrigin(request);
}
