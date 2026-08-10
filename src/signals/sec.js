import { config } from '../config.js';

const SEC_RATE_LIMIT_MS = 120; // SEC asks for <= 10 req/sec; stay well under.
let lastRequest = 0;

function requireUserAgent() {
  if (!config.sec.userAgent || !config.sec.userAgent.includes('@')) {
    throw new Error(
      'SEC_USER_AGENT must be set to something like "AppName your.email@example.com". ' +
        'The SEC blocks requests without a contact address.'
    );
  }
}

async function throttle() {
  const wait = SEC_RATE_LIMIT_MS - (Date.now() - lastRequest);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  lastRequest = Date.now();
}

export async function secFetch(url, { asJson = false } = {}) {
  requireUserAgent();
  await throttle();

  const res = await fetch(url, {
    headers: {
      'User-Agent': config.sec.userAgent,
      'Accept-Encoding': 'gzip, deflate',
    },
  });

  if (!res.ok) {
    throw new Error(`SEC request failed (${res.status} ${res.statusText}): ${url}`);
  }
  return asJson ? res.json() : res.text();
}

export const padCik = (cik) => String(cik).replace(/\D/g, '').padStart(10, '0');
export const bareCik = (cik) => String(Number(String(cik).replace(/\D/g, '')));

/** Recent filings for an entity, flattened from EDGAR's column-oriented JSON. */
export async function getSubmissions(cik, { forms = null, limit = 40 } = {}) {
  const data = await secFetch(`https://data.sec.gov/submissions/CIK${padCik(cik)}.json`, {
    asJson: true,
  });

  const recent = data.filings?.recent ?? {};
  const n = recent.accessionNumber?.length ?? 0;
  const out = [];

  for (let i = 0; i < n; i++) {
    const form = recent.form[i];
    if (forms && !forms.includes(form)) continue;
    const accession = recent.accessionNumber[i];
    const noDash = accession.replace(/-/g, '');
    out.push({
      cik: bareCik(cik),
      entityName: data.name,
      form,
      accession,
      filingDate: recent.filingDate[i],
      reportDate: recent.reportDate?.[i] || null,
      primaryDocument: recent.primaryDocument?.[i] || null,
      folder: `https://www.sec.gov/Archives/edgar/data/${bareCik(cik)}/${noDash}`,
      url: `https://www.sec.gov/Archives/edgar/data/${bareCik(cik)}/${noDash}/${recent.primaryDocument?.[i] || ''}`,
    });
    if (out.length >= limit) break;
  }

  return { entityName: data.name, tickers: data.tickers || [], filings: out };
}

/** List the files inside a filing folder (used to locate the XML payload). */
export async function listFilingFiles(folder) {
  const idx = await secFetch(`${folder}/index.json`, { asJson: true });
  return (idx.directory?.item ?? []).map((f) => ({
    name: f.name,
    url: `${folder}/${f.name}`,
    size: Number(f.size || 0),
  }));
}

/** Resolve a CIK from a ticker via EDGAR's published mapping file. */
let tickerMap = null;
export async function cikForTicker(ticker) {
  if (!tickerMap) {
    const data = await secFetch('https://www.sec.gov/files/company_tickers.json', { asJson: true });
    tickerMap = new Map(
      Object.values(data).map((r) => [String(r.ticker).toUpperCase(), { cik: r.cik_str, name: r.title }])
    );
  }
  return tickerMap.get(String(ticker).toUpperCase()) || null;
}

// --------------------------------------------------------------------------
// Minimal XML helpers. EDGAR ownership and 13F documents are machine-generated
// with a fixed shape, so a full parser dependency is not warranted.
// --------------------------------------------------------------------------

const stripNs = (tag) => `(?:\\w+:)?${tag}`;

export function xmlBlocks(xml, tag) {
  const re = new RegExp(`<${stripNs(tag)}[^>]*>([\\s\\S]*?)</${stripNs(tag)}>`, 'g');
  return [...xml.matchAll(re)].map((m) => m[1]);
}

export function xmlText(xml, tag) {
  const m = xml.match(new RegExp(`<${stripNs(tag)}[^>]*>([\\s\\S]*?)</${stripNs(tag)}>`));
  if (!m) return null;
  return m[1]
    .replace(/<[^>]+>/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ')
    .trim();
}

export function xmlNumber(xml, tag) {
  const t = xmlText(xml, tag);
  if (t == null) return null;
  const n = Number(t.replace(/[$,\s]/g, ''));
  return Number.isFinite(n) ? n : null;
}
