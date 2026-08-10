import AdmZip from 'adm-zip';

/**
 * STOCK Act disclosures. Members must file a Periodic Transaction Report
 * within 30 days of learning of a trade and no later than 45 days after it -
 * so everything here is weeks old by construction.
 *
 * The House Clerk publishes a machine-readable index of *filings* (who filed,
 * when, and a link). Ticker-level detail lives inside the linked PDF, which
 * this module does not parse - see `parseTransactions` below for how to plug
 * that in. The index alone is still useful: it tells you the moment a member
 * you follow discloses activity.
 */

const HOUSE_INDEX = (year) =>
  `https://disclosures-clerk.house.gov/public_disc/financial-pdfs/${year}FD.ZIP`;

const PTR_PDF = (year, docId) =>
  `https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/${year}/${docId}.pdf`;

const FD_PDF = (year, docId) =>
  `https://disclosures-clerk.house.gov/public_disc/financial-pdfs/${year}/${docId}.pdf`;

const FILING_TYPES = {
  P: 'Periodic Transaction Report',
  O: 'Annual Financial Disclosure',
  A: 'Amendment',
  C: 'Candidate Report',
  T: 'Termination Report',
  W: 'Withdrawal',
  D: 'Due Date Extension',
  X: 'Blind Trust',
};

const normalizeName = (s) =>
  String(s || '')
    .toLowerCase()
    .replace(/[^a-z\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();

function parseIndex(text, year) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length === 0) return [];

  const header = lines[0].split('\t').map((h) => h.trim());
  const col = (row, name) => {
    const i = header.indexOf(name);
    return i === -1 ? null : (row[i] ?? '').trim();
  };

  const out = [];
  for (const line of lines.slice(1)) {
    const row = line.split('\t');
    const docId = col(row, 'DocID');
    if (!docId) continue;

    const type = col(row, 'FilingType');
    const first = col(row, 'First');
    const last = col(row, 'Last');
    const filingYear = col(row, 'Year') || String(year);
    const name = [first, last].filter(Boolean).join(' ');

    out.push({
      source: 'congress',
      chamber: 'House',
      actor: normalizeName(name),
      actorLabel: `${name}${col(row, 'StateDst') ? ` (${col(row, 'StateDst')})` : ''}`,
      filingType: type,
      filingTypeLabel: FILING_TYPES[type] || type,
      isTradeReport: type === 'P',
      filedAt: normalizeDate(col(row, 'FilingDate')),
      docId,
      url: type === 'P' ? PTR_PDF(filingYear, docId) : FD_PDF(filingYear, docId),
      // Paper filings are scanned images; e-filed IDs (8 digits, leading 2)
      // are text PDFs and are the ones worth trying to parse.
      machineReadable: /^2\d{7}$/.test(docId),
    });
  }
  return out;
}

function normalizeDate(d) {
  if (!d) return null;
  const m = d.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!m) return d;
  return `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
}

/** Download and unpack the House Clerk's annual filing index. */
export async function fetchHouseFilings(year = new Date().getFullYear()) {
  const res = await fetch(HOUSE_INDEX(year), {
    headers: { 'User-Agent': 'FinanceCoding personal-tracker' },
  });
  if (!res.ok) {
    throw new Error(`House Clerk index for ${year} unavailable (${res.status}).`);
  }

  const zip = new AdmZip(Buffer.from(await res.arrayBuffer()));
  const entry = zip.getEntries().find((e) => e.entryName.toLowerCase().endsWith('.txt'));
  if (!entry) throw new Error(`No index file inside ${year}FD.ZIP`);

  return parseIndex(zip.readAsText(entry), year);
}

/**
 * Filings by the members you follow, newest first. `names` are matched loosely
 * so "Nancy Pelosi", "pelosi" and "PELOSI, Nancy" all hit.
 */
export async function fetchCongressSignals({ names = [], year, sinceDays = 90 } = {}) {
  const years = year ? [year] : uniqueYearsCovering(sinceDays);
  const cutoff = new Date(Date.now() - sinceDays * 86400000).toISOString().slice(0, 10);

  const all = [];
  for (const y of years) {
    try {
      all.push(...(await fetchHouseFilings(y)));
    } catch {
      // A year with no published index yet is not an error worth failing on.
    }
  }

  const wanted = names.map(normalizeName).filter(Boolean);
  const matches = (f) =>
    wanted.length === 0 || wanted.some((w) => f.actor.includes(w) || w.includes(f.actor));

  return all
    .filter((f) => f.isTradeReport && matches(f) && (!f.filedAt || f.filedAt >= cutoff))
    .sort((a, b) => String(b.filedAt).localeCompare(String(a.filedAt)));
}

function uniqueYearsCovering(days) {
  const now = new Date();
  const then = new Date(Date.now() - days * 86400000);
  return [...new Set([then.getFullYear(), now.getFullYear()])];
}

/**
 * Hook for ticker-level House data.
 *
 * The transactions themselves are only in the PDF, so extracting them needs a
 * PDF text layer (e-filed reports have one; scanned ones need OCR). Point
 * CONGRESS_TX_API at a service that returns normalised rows and this becomes
 * live; otherwise the dashboard shows filing-level events with links.
 */
export async function parseTransactions(filing) {
  const base = process.env.CONGRESS_TX_API;
  if (!base) return null;
  const res = await fetch(`${base.replace(/\/$/, '')}/ptr/${filing.docId}`);
  if (!res.ok) return null;
  return res.json();
}

/**
 * The Senate side (efdsearch.senate.gov) requires accepting terms and holding
 * a session cookie before it will serve results, so it is deliberately left as
 * an explicit unsupported path rather than a silently empty feed.
 */
export function senateSupport() {
  return {
    supported: false,
    reason:
      'efdsearch.senate.gov gates results behind a terms-acceptance session cookie. ' +
      'Use a third-party normalised API via CONGRESS_TX_API, or add Senate scraping deliberately.',
  };
}
