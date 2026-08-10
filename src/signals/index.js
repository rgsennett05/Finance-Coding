import crypto from 'node:crypto';
import { db, getPrefNumber } from '../db.js';
import { fetchForm4 } from './form4.js';
import { fetch13F } from './thirteenf.js';
import { fetchCongressSignals } from './congress.js';
import { ratingsForTickers, isConfigured as analystsConfigured } from './analysts.js';
import { secFetch, bareCik } from './sec.js';

/**
 * Starting points for 13F following. CIKs are stable identifiers; names on
 * EDGAR are not, so these are keyed by CIK and verified on first fetch.
 */
export const SUGGESTED_INSTITUTIONS = [
  { cik: '1067983', label: 'Berkshire Hathaway (Warren Buffett)' },
  { cik: '1336528', label: 'Pershing Square (Bill Ackman)' },
  { cik: '1649339', label: 'Scion Asset Management (Michael Burry)' },
  { cik: '1350694', label: 'Bridgewater Associates (Ray Dalio)' },
  { cik: '1037389', label: 'Renaissance Technologies' },
];

const hashId = (...parts) =>
  crypto.createHash('sha1').update(parts.filter(Boolean).join('|')).digest('hex').slice(0, 24);

const insertSignal = db.prepare(
  `INSERT INTO signals (id, source, actor, actor_label, ticker, security_name, action,
                        quantity, amount_low, amount_high, transacted_at, filed_at, url, raw)
   VALUES (@id, @source, @actor, @actor_label, @ticker, @security_name, @action,
           @quantity, @amount_low, @amount_high, @transacted_at, @filed_at, @url, @raw)
   ON CONFLICT(id) DO UPDATE SET
     amount_low = excluded.amount_low, amount_high = excluded.amount_high,
     quantity = excluded.quantity, fetched_at = datetime('now')`
);

const saveMany = db.transaction((rows) => {
  for (const r of rows) insertSignal.run(r);
});

// --------------------------------------------------------------------------
// Follow list
// --------------------------------------------------------------------------

export function listFollows(kind = null) {
  return kind
    ? db.prepare('SELECT * FROM follows WHERE kind = ? AND active = 1 ORDER BY label').all(kind)
    : db.prepare('SELECT * FROM follows WHERE active = 1 ORDER BY kind, label').all();
}

export function addFollow(kind, identifier, label = null) {
  const valid = ['congress', 'institution', 'insider', 'analyst'];
  if (!valid.includes(kind)) throw new Error(`kind must be one of: ${valid.join(', ')}`);
  const id = kind === 'congress' ? identifier.trim() : bareCik(identifier);

  db.prepare(
    `INSERT INTO follows (kind, identifier, label) VALUES (?, ?, ?)
     ON CONFLICT(kind, identifier) DO UPDATE SET active = 1, label = COALESCE(excluded.label, label)`
  ).run(kind, id, label || identifier);

  return { kind, identifier: id, label: label || identifier };
}

export function removeFollow(kind, identifier) {
  const id = kind === 'congress' ? identifier.trim() : bareCik(identifier);
  return db.prepare('UPDATE follows SET active = 0 WHERE kind = ? AND identifier = ?').run(kind, id)
    .changes > 0;
}

/** Look up an entity's CIK on EDGAR by name, so nothing has to be hardcoded. */
export async function findEntity(name, formType = '13F-HR') {
  const url =
    `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${encodeURIComponent(name)}` +
    `&type=${encodeURIComponent(formType)}&dateb=&owner=include&count=25&output=atom`;
  const xml = await secFetch(url);

  const results = [];
  for (const entry of xml.split('<entry>').slice(1)) {
    const cik = entry.match(/CIK=(\d+)/)?.[1];
    const title = entry.match(/<title>([\s\S]*?)<\/title>/)?.[1]?.trim();
    if (cik && !results.some((r) => r.cik === bareCik(cik))) {
      results.push({ cik: bareCik(cik), label: title });
    }
  }
  return results;
}

// --------------------------------------------------------------------------
// Refresh
// --------------------------------------------------------------------------

async function refreshInstitutions(follows, report) {
  for (const f of follows) {
    try {
      const data = await fetch13F(f.identifier);
      if (!data.latest) {
        report.push({ source: '13f', actor: f.label, note: 'no 13F filings found' });
        continue;
      }

      const rows = data.moves.map((m) => ({
        id: hashId('13f', f.identifier, data.latest.reportDate, m.cusip || m.issuer, m.action),
        source: '13f',
        actor: f.identifier,
        actor_label: data.entityName || f.label,
        ticker: null, // 13F reports CUSIPs, not tickers
        security_name: m.issuer,
        action: m.action,
        quantity: m.sharesDelta,
        amount_low: m.value,
        amount_high: m.value,
        transacted_at: data.latest.reportDate,
        filed_at: data.latest.filingDate,
        url: data.latest.url,
        raw: JSON.stringify({ cusip: m.cusip, weight: m.weight, pctChange: m.pctChange }),
      }));

      saveMany(rows);
      report.push({
        source: '13f',
        actor: data.entityName || f.label,
        saved: rows.length,
        asOf: data.reportedAsOf,
        daysStale: data.daysStale,
      });
    } catch (err) {
      report.push({ source: '13f', actor: f.label, error: err.message });
    }
  }
}

async function refreshInsiders(follows, report) {
  for (const f of follows) {
    try {
      const { entityName, trades } = await fetchForm4(f.identifier);
      const rows = trades.map((t) => ({
        id: hashId('form4', t.actor, t.ticker, t.transactedAt, t.action, String(t.quantity)),
        source: 'form4',
        actor: t.actor || f.identifier,
        actor_label: t.actorLabel || entityName || f.label,
        ticker: t.ticker,
        security_name: t.securityName,
        action: t.action,
        quantity: t.quantity,
        amount_low: t.value,
        amount_high: t.value,
        transacted_at: t.transactedAt,
        filed_at: t.filedAt,
        url: t.url,
        raw: JSON.stringify({
          openMarket: t.openMarket,
          price: t.price,
          derivative: t.derivative,
          actionLabel: t.actionLabel,
        }),
      }));

      saveMany(rows);
      report.push({ source: 'form4', actor: entityName || f.label, saved: rows.length });
    } catch (err) {
      report.push({ source: 'form4', actor: f.label, error: err.message });
    }
  }
}

async function refreshCongress(follows, report, sinceDays) {
  try {
    const names = follows.map((f) => f.label || f.identifier);
    const filings = await fetchCongressSignals({ names, sinceDays });

    const rows = filings.map((c) => ({
      id: hashId('congress', c.docId),
      source: 'congress',
      actor: c.actor,
      actor_label: c.actorLabel,
      ticker: null,
      security_name: null,
      action: 'disclosed',
      quantity: null,
      amount_low: null,
      amount_high: null,
      transacted_at: null,
      filed_at: c.filedAt,
      url: c.url,
      raw: JSON.stringify({
        chamber: c.chamber,
        filingType: c.filingTypeLabel,
        machineReadable: c.machineReadable,
      }),
    }));

    saveMany(rows);
    report.push({
      source: 'congress',
      saved: rows.length,
      note: 'filing-level events; ticker detail lives in the linked PDF',
    });
  } catch (err) {
    report.push({ source: 'congress', error: err.message });
  }
}

async function refreshAnalysts(report) {
  if (!analystsConfigured()) {
    report.push({ source: 'analyst', skipped: 'FINNHUB_API_KEY not set' });
    return;
  }
  try {
    const tickers = db
      .prepare(
        `SELECT DISTINCT s.ticker FROM holdings h
           JOIN securities s ON s.security_id = h.security_id
          WHERE s.ticker IS NOT NULL AND s.is_cash_equivalent = 0`
      )
      .all()
      .map((r) => r.ticker);

    if (tickers.length === 0) {
      report.push({ source: 'analyst', skipped: 'no holdings to rate yet' });
      return;
    }

    const { ratings } = await ratingsForTickers(tickers);
    const rows = ratings.map((r) => ({
      id: hashId('analyst', r.ticker, r.trend?.period || new Date().toISOString().slice(0, 7)),
      source: 'analyst',
      actor: 'street-consensus',
      actor_label: `Analyst consensus (${r.trend?.analystCount ?? 0} analysts)`,
      ticker: r.ticker,
      security_name: null,
      action: r.trend?.consensus || 'unknown',
      quantity: r.trend?.analystCount ?? null,
      amount_low: r.target?.low ?? null,
      amount_high: r.target?.high ?? null,
      transacted_at: null,
      filed_at: r.trend?.period || new Date().toISOString().slice(0, 10),
      url: `https://finnhub.io/`,
      raw: JSON.stringify(r),
    }));

    saveMany(rows);
    report.push({ source: 'analyst', saved: rows.length });
  } catch (err) {
    report.push({ source: 'analyst', error: err.message });
  }
}

export async function refreshSignals({ sources = ['13f', 'form4', 'congress', 'analyst'] } = {}) {
  const sinceDays = getPrefNumber('signal_lookback_days', 90);
  const report = [];

  if (sources.includes('13f')) await refreshInstitutions(listFollows('institution'), report);
  if (sources.includes('form4')) await refreshInsiders(listFollows('insider'), report);
  if (sources.includes('congress')) await refreshCongress(listFollows('congress'), report, sinceDays);
  if (sources.includes('analyst')) await refreshAnalysts(report);

  return report;
}

// --------------------------------------------------------------------------
// Reading signals back out
// --------------------------------------------------------------------------

/**
 * Every signal here is a disclosure with a built-in delay, so each row carries
 * how stale it is. Nothing in this feed is real time.
 */
export function recentSignals({ source = null, limit = 100, ticker = null } = {}) {
  const where = [];
  const params = [];
  if (source) {
    where.push('source = ?');
    params.push(source);
  }
  if (ticker) {
    where.push('ticker = ?');
    params.push(ticker);
  }
  const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';

  return db
    .prepare(`SELECT * FROM signals ${clause} ORDER BY filed_at DESC, fetched_at DESC LIMIT ?`)
    .all(...params, limit)
    .map((r) => ({
      ...r,
      raw: safeParse(r.raw),
      daysSinceFiled: r.filed_at
        ? Math.round((Date.now() - new Date(r.filed_at).getTime()) / 86400000)
        : null,
    }));
}

/** Signals that touch something you already own - the ones that matter most. */
export function signalsOnMyHoldings({ limit = 50 } = {}) {
  return db
    .prepare(
      `SELECT s.*, sec.ticker AS my_ticker
         FROM signals s
         JOIN securities sec ON UPPER(sec.ticker) = UPPER(s.ticker)
         JOIN holdings h ON h.security_id = sec.security_id
        WHERE s.ticker IS NOT NULL
        GROUP BY s.id
        ORDER BY s.filed_at DESC
        LIMIT ?`
    )
    .all(limit)
    .map((r) => ({ ...r, raw: safeParse(r.raw) }));
}

function safeParse(s) {
  try {
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
