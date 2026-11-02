/**
 * fundamentals — annual figures from the SEC's XBRL "company facts" API.
 *
 * Free, official, and keyed by ticker → CIK. Needs SEC_USER_AGENT with a
 * contact email (the SEC blocks anonymous requests). Reuses the throttled
 * client from src/signals/sec.js.
 */
import { secFetch, cikForTicker, padCik } from '../../src/signals/sec.js';

// First concept that has data wins — companies tag the same idea differently.
const CONCEPTS = {
  operatingCashFlow: ['NetCashProvidedByUsedInOperatingActivities'],
  capex: ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'],
  revenue: ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet'],
  netIncome: ['NetIncomeLoss'],
  cash: ['CashAndCashEquivalentsAtCarryingValue', 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'],
  debt: ['LongTermDebt', 'LongTermDebtNoncurrent'],
};

const DAY = 86400000;

/**
 * Annual (10-K, ~12-month) values keyed by fiscal-year end date.
 *
 * Companies switch tags over time (NVIDIA and Amazon moved capex from
 * PaymentsToAcquirePropertyPlantAndEquipment to PaymentsToAcquireProductiveAssets),
 * so every listed concept is read and merged per year; for a year reported
 * under several tags, the one listed first wins.
 */
export function annualSeries(facts, concepts, { instant = false } = {}) {
  const byEnd = new Map();
  const used = new Set();
  concepts.forEach((concept, rank) => {
    const units = facts?.facts?.['us-gaap']?.[concept]?.units?.USD;
    if (!units) return;
    for (const u of units) {
      if (u.form !== '10-K') continue;
      if (!instant) {
        const days = (new Date(u.end) - new Date(u.start)) / DAY;
        if (!(days > 350 && days < 380)) continue;
      }
      const prev = byEnd.get(u.end);
      // Prefer the higher-priority concept; within one concept keep the latest restatement.
      if (!prev || rank < prev.rank || (rank === prev.rank && u.filed > prev.filed)) {
        byEnd.set(u.end, { ...u, rank, concept });
      }
    }
  });
  const rows = [...byEnd.values()].sort((a, b) => a.end.localeCompare(b.end));
  rows.forEach((r) => used.add(r.concept));
  return { concepts: [...used], rows: rows.map((u) => ({ end: u.end, value: u.val })) };
}

/** Latest share count: cover-page figure, then balance sheet, then diluted weighted average. */
export function latestShares(facts) {
  const sources = [
    facts?.facts?.dei?.EntityCommonStockSharesOutstanding?.units?.shares,
    facts?.facts?.['us-gaap']?.CommonStockSharesOutstanding?.units?.shares,
    facts?.facts?.['us-gaap']?.WeightedAverageNumberOfDilutedSharesOutstanding?.units?.shares,
  ];
  for (const rows of sources) {
    if (!rows?.length) continue;
    const latest = [...rows].sort((a, b) => a.end.localeCompare(b.end) || a.filed.localeCompare(b.filed)).at(-1);
    if (latest.val > 0) return { value: latest.val, asOf: latest.end };
  }
  return { value: null, asOf: null };
}

export function extractFundamentals(facts) {
  const get = (k, opts) => annualSeries(facts, CONCEPTS[k], opts);
  const ocf = get('operatingCashFlow');
  const capex = get('capex');
  const capexByEnd = new Map(capex.rows.map((r) => [r.end, r.value]));
  const fcf = ocf.rows
    .filter((r) => capexByEnd.has(r.end))
    .map((r) => ({ end: r.end, value: r.value - capexByEnd.get(r.end) }));
  const shares = latestShares(facts);

  return {
    entityName: facts?.entityName ?? null,
    freeCashFlow: fcf.slice(-6),
    revenue: get('revenue').rows.slice(-6),
    netIncome: get('netIncome').rows.slice(-6),
    cash: get('cash', { instant: true }).rows.at(-1)?.value ?? null,
    debt: get('debt', { instant: true }).rows.at(-1)?.value ?? 0,
    sharesOutstanding: shares.value,
    sharesAsOf: shares.asOf,
    hasAnnualReports: ocf.rows.length > 0,
  };
}

export default {
  name: 'fundamentals',
  description: 'Annual free cash flow, revenue, net income, cash, debt and share count from SEC XBRL filings.',
  async run({ ticker }, ctx = {}) {
    if (ctx.offline) return { ticker, available: false, reason: 'offline mode' };
    try {
      const hit = await cikForTicker(ticker);
      if (!hit) return { ticker, available: false, reason: 'ticker not in SEC map (ETF or foreign issuer?)' };
      const facts = await secFetch(`https://data.sec.gov/api/xbrl/companyfacts/CIK${padCik(hit.cik)}.json`, { asJson: true });
      return { ticker, available: true, cik: hit.cik, ...extractFundamentals(facts) };
    } catch (err) {
      return { ticker, available: false, reason: err.message };
    }
  },
};
