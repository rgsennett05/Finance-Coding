/**
 * Minimal, throttled SEC EDGAR client.
 *
 * The SEC requires a User-Agent with a contact email on every request and asks
 * for no more than 10 requests per second.
 */
const SEC_RATE_LIMIT_MS = 120;
let lastRequest = 0;

function userAgent() {
  const ua = process.env.SEC_USER_AGENT || '';
  if (!ua.includes('@')) {
    throw new Error('SEC_USER_AGENT must be set to something like "TickerCity you@example.com" — the SEC blocks requests without a contact address.');
  }
  return ua;
}

async function throttle() {
  const wait = SEC_RATE_LIMIT_MS - (Date.now() - lastRequest);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  lastRequest = Date.now();
}

export async function secFetch(url, { asJson = false } = {}) {
  const ua = userAgent();
  await throttle();
  const res = await fetch(url, { headers: { 'User-Agent': ua, 'Accept-Encoding': 'gzip, deflate' } });
  if (!res.ok) throw new Error(`SEC request failed (${res.status} ${res.statusText}): ${url}`);
  return asJson ? res.json() : res.text();
}

export const padCik = (cik) => String(cik).replace(/\D/g, '').padStart(10, '0');

/** Resolve a CIK from a ticker via EDGAR's published mapping file. */
let tickerMap = null;
export async function cikForTicker(ticker) {
  if (!tickerMap) {
    const data = await secFetch('https://www.sec.gov/files/company_tickers.json', { asJson: true });
    tickerMap = new Map(Object.values(data).map((r) => [String(r.ticker).toUpperCase(), { cik: r.cik_str, name: r.title }]));
  }
  return tickerMap.get(String(ticker).toUpperCase()) || null;
}
