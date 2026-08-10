import { getSubmissions, listFilingFiles, secFetch, xmlBlocks, xmlText, xmlNumber } from './sec.js';

/**
 * 13F reports a manager's long US equity positions once a quarter, up to 45
 * days after quarter end. It is a conviction signal, never a timing one - by
 * the time you read it the position may be months old or already sold.
 */

// The SEC switched 13F <value> from thousands to whole dollars for filings
// covering periods on or after 2023-01-01.
const WHOLE_DOLLAR_CUTOVER = '2023-01-01';

export function parseInfoTable(xml, reportDate) {
  const inThousands = !reportDate || reportDate < WHOLE_DOLLAR_CUTOVER;
  const rows = [];

  for (const t of xmlBlocks(xml, 'infoTable')) {
    const rawValue = xmlNumber(t, 'value');
    if (rawValue == null) continue;
    rows.push({
      issuer: xmlText(t, 'nameOfIssuer'),
      cusip: xmlText(t, 'cusip'),
      titleOfClass: xmlText(t, 'titleOfClass'),
      value: Math.round(inThousands ? rawValue * 1000 : rawValue),
      shares: xmlNumber(t, 'sshPrnamt'),
      shareType: xmlText(t, 'sshPrnamtType'),
    });
  }

  // Managers often file one row per account; roll them up per security.
  const merged = new Map();
  for (const r of rows) {
    const key = r.cusip || r.issuer;
    const cur = merged.get(key) || { ...r, value: 0, shares: 0 };
    cur.value += r.value;
    cur.shares += r.shares || 0;
    merged.set(key, cur);
  }
  return [...merged.values()].sort((a, b) => b.value - a.value);
}

async function fetchHoldingsForFiling(filing) {
  const files = await listFilingFiles(filing.folder);
  // The information table is the XML that is not the cover page (primary_doc).
  const table =
    files.find((f) => /infotable|information_?table/i.test(f.name) && f.name.endsWith('.xml')) ||
    files.find((f) => f.name.endsWith('.xml') && !/primary_?doc/i.test(f.name));
  if (!table) return null;

  const xml = await secFetch(table.url);
  const holdings = parseInfoTable(xml, filing.reportDate);
  return {
    reportDate: filing.reportDate,
    filingDate: filing.filingDate,
    url: filing.url,
    holdings,
    totalValue: holdings.reduce((s, h) => s + h.value, 0),
  };
}

/** Quarter-over-quarter deltas - what the manager actually did, not just holds. */
export function diffQuarters(current, previous) {
  const prev = new Map((previous?.holdings ?? []).map((h) => [h.cusip || h.issuer, h]));
  const moves = [];

  for (const h of current.holdings) {
    const key = h.cusip || h.issuer;
    const before = prev.get(key);
    const weight = current.totalValue > 0 ? (h.value / current.totalValue) * 100 : 0;

    if (!before) {
      moves.push({ ...h, action: 'new', sharesDelta: h.shares, pctChange: null, weight });
    } else if (h.shares > before.shares) {
      moves.push({
        ...h,
        action: 'increase',
        sharesDelta: h.shares - before.shares,
        pctChange: before.shares ? ((h.shares - before.shares) / before.shares) * 100 : null,
        weight,
      });
    } else if (h.shares < before.shares) {
      moves.push({
        ...h,
        action: 'reduce',
        sharesDelta: h.shares - before.shares,
        pctChange: before.shares ? ((h.shares - before.shares) / before.shares) * 100 : null,
        weight,
      });
    }
    prev.delete(key);
  }

  // Anything left in the previous quarter is a full exit.
  for (const gone of prev.values()) {
    moves.push({ ...gone, action: 'exit', sharesDelta: -(gone.shares || 0), pctChange: -100, weight: 0 });
  }

  const rank = { new: 0, increase: 1, reduce: 2, exit: 3 };
  return moves.sort((a, b) => rank[a.action] - rank[b.action] || b.value - a.value);
}

export async function fetch13F(cik) {
  const { entityName, filings } = await getSubmissions(cik, {
    forms: ['13F-HR', '13F-HR/A'],
    limit: 4,
  });
  if (filings.length === 0) return { entityName, latest: null, moves: [] };

  const latest = await fetchHoldingsForFiling(filings[0]);
  if (!latest) return { entityName, latest: null, moves: [] };

  let previous = null;
  for (const f of filings.slice(1)) {
    if (f.reportDate === filings[0].reportDate) continue; // skip amendments
    previous = await fetchHoldingsForFiling(f);
    break;
  }

  return {
    entityName,
    latest,
    previous: previous ? { reportDate: previous.reportDate, totalValue: previous.totalValue } : null,
    moves: previous ? diffQuarters(latest, previous) : [],
    topHoldings: latest.holdings.slice(0, 15).map((h) => ({
      ...h,
      weight: latest.totalValue > 0 ? Number(((h.value / latest.totalValue) * 100).toFixed(2)) : 0,
    })),
    // How stale this is, stated up front.
    reportedAsOf: latest.reportDate,
    daysStale: latest.reportDate
      ? Math.round((Date.now() - new Date(latest.reportDate).getTime()) / 86400000)
      : null,
  };
}
