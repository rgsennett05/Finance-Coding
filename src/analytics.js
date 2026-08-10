import { db, getPrefNumber, getPref } from './db.js';

const round = (n, p = 2) => (Number.isFinite(n) ? Number(n.toFixed(p)) : 0);
const pct = (part, whole) => (whole > 0 ? round((part / whole) * 100) : 0);
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);

/**
 * Plaid's sign convention on investment transactions: positive = cash debited
 * (a buy), negative = cash credited (a dividend, a sale). Income arrives
 * negative, so it is flipped for display.
 */
const REINVEST_SUBTYPES = [
  'dividend reinvestment',
  'interest reinvestment',
  'long-term capital gain reinvestment',
  'short-term capital gain reinvestment',
];

const INCOME_SUBTYPES = [
  'dividend',
  'qualified dividend',
  'non-qualified dividend',
  'interest',
  'interest receivable',
  'long-term capital gain',
  'short-term capital gain',
  'return of capital',
];

const placeholders = (arr) => arr.map(() => '?').join(',');

// --------------------------------------------------------------------------
// Net worth, and the bank-vs-invested split
// --------------------------------------------------------------------------

export function netWorth() {
  const accounts = db
    .prepare(
      `SELECT a.*, i.institution_name
         FROM accounts a JOIN items i ON i.item_id = a.item_id
        ORDER BY a.type, a.name`
    )
    .all();

  const sum = (t) =>
    accounts.filter((a) => a.type === t).reduce((s, a) => s + (a.current_balance || 0), 0);

  const bank = sum('depository');
  const invested = sum('investment');
  const credit = sum('credit');
  const loan = sum('loan');

  const assets = bank + invested;
  const liabilities = credit + loan;

  const history = db
    .prepare('SELECT as_of, bank_total, invested_total FROM balance_history ORDER BY as_of')
    .all()
    .map((r) => ({
      date: r.as_of,
      bank: round(r.bank_total),
      invested: round(r.invested_total),
      total: round(r.bank_total + r.invested_total),
    }));

  return {
    bank: round(bank),
    invested: round(invested),
    liabilities: round(liabilities),
    assets: round(assets),
    netWorth: round(assets - liabilities),
    bankPct: pct(bank, assets),
    investedPct: pct(invested, assets),
    accounts: accounts.map((a) => ({
      id: a.account_id,
      institution: a.institution_name,
      name: a.name,
      mask: a.mask,
      type: a.type,
      subtype: a.subtype,
      balance: round(a.current_balance || 0),
    })),
    history,
  };
}

// --------------------------------------------------------------------------
// Position-level P&L
// --------------------------------------------------------------------------

export function positions() {
  const rows = db
    .prepare(
      `SELECT h.*, s.ticker, s.name AS security_name, s.type AS security_type,
              s.is_cash_equivalent, a.name AS account_name, i.institution_name
         FROM holdings h
         JOIN securities s ON s.security_id = h.security_id
         JOIN accounts   a ON a.account_id  = h.account_id
         JOIN items      i ON i.item_id     = a.item_id`
    )
    .all();

  const total = rows.reduce((s, r) => s + (r.institution_value || 0), 0);

  const list = rows
    .map((r) => {
      const value = r.institution_value || 0;
      // Plaid's cost_basis is per-share for most institutions but total for
      // some; treat it as per-share only when that yields a sane basis.
      const basis = r.cost_basis == null ? null : r.cost_basis * (r.quantity || 0);
      const gain = basis == null ? null : value - basis;
      return {
        ticker: r.ticker || r.security_name || 'Unknown',
        name: r.security_name,
        account: `${r.institution_name} ${r.account_name}`,
        assetClass: r.security_type,
        quantity: round(r.quantity || 0, 6),
        price: round(r.institution_price || 0),
        value: round(value),
        costBasis: basis == null ? null : round(basis),
        gain: gain == null ? null : round(gain),
        gainPct: gain == null || !basis ? null : round((gain / basis) * 100),
        weight: pct(value, total),
      };
    })
    .sort((a, b) => b.value - a.value);

  const withBasis = list.filter((p) => p.gain != null);
  return {
    total: round(total),
    count: list.length,
    unrealizedGain: round(withBasis.reduce((s, p) => s + p.gain, 0)),
    positions: list,
  };
}

// --------------------------------------------------------------------------
// Diversification
// --------------------------------------------------------------------------

export function diversification() {
  const { positions: list, total } = positions();
  const warnAt = getPrefNumber('concentration_warn_pct', 20);

  const group = (keyFn) => {
    const map = new Map();
    for (const p of list) {
      const key = keyFn(p) || 'Unclassified';
      map.set(key, (map.get(key) || 0) + p.value);
    }
    return [...map.entries()]
      .map(([label, value]) => ({ label, value: round(value), pct: pct(value, total) }))
      .sort((a, b) => b.value - a.value);
  };

  const sectorOf = new Map(
    db.prepare('SELECT ticker, sector FROM sector_map').all().map((r) => [r.ticker, r.sector])
  );

  const byAssetClass = group((p) => p.assetClass);
  const bySector = group((p) => sectorOf.get(p.ticker));
  const byAccount = group((p) => p.account);

  // Herfindahl index on position weights: 0 = perfectly spread, 10000 = one holding.
  const hhi = round(list.reduce((s, p) => s + p.weight ** 2, 0), 0);
  const concentrated = list.filter((p) => p.weight >= warnAt);
  const unclassifiedSectorPct = bySector.find((s) => s.label === 'Unclassified')?.pct ?? 0;

  return {
    total,
    byAssetClass,
    bySector,
    byAccount,
    hhi,
    hhiVerdict:
      hhi >= 2500 ? 'highly concentrated' : hhi >= 1500 ? 'moderately concentrated' : 'diversified',
    concentrationWarnPct: warnAt,
    concentrated,
    topFiveWeight: round(list.slice(0, 5).reduce((s, p) => s + p.weight, 0)),
    // Sector data is only as good as the ticker map; say so rather than imply
    // the breakdown is complete.
    sectorCoverage: round(100 - unclassifiedSectorPct),
  };
}

// --------------------------------------------------------------------------
// Cash runway and safety buffer
// --------------------------------------------------------------------------

export function cashRunway() {
  const excluded = JSON.parse(getPref('exclude_transfer_categories', '[]'));
  const targetMonths = getPrefNumber('target_buffer_months', 6);
  const since = daysAgo(90);

  const filter = excluded.length
    ? `AND COALESCE(category, '') NOT IN (${placeholders(excluded)})`
    : '';

  // Plaid: positive amount = money leaving the account.
  const spend = db
    .prepare(
      `SELECT COALESCE(SUM(amount), 0) AS outflow, COUNT(*) AS n
         FROM bank_transactions
        WHERE amount > 0 AND pending = 0 AND date >= ? ${filter}`
    )
    .get(since, ...excluded);

  const monthsObserved = 3;
  const monthlyExpenses = spend.outflow > 0 ? spend.outflow / monthsObserved : 0;

  const bank = db
    .prepare(
      `SELECT COALESCE(SUM(current_balance), 0) AS total
         FROM accounts WHERE type = 'depository'`
    )
    .get().total;

  const targetBuffer = monthlyExpenses * targetMonths;
  const runwayMonths = monthlyExpenses > 0 ? bank / monthlyExpenses : null;

  return {
    bankTotal: round(bank),
    monthlyExpenses: round(monthlyExpenses),
    sampleTransactions: spend.n,
    targetMonths,
    targetBuffer: round(targetBuffer),
    runwayMonths: runwayMonths == null ? null : round(runwayMonths, 1),
    surplus: round(bank - targetBuffer),
    status:
      spend.n === 0
        ? 'no spending data yet'
        : bank >= targetBuffer
          ? 'buffer met'
          : bank >= targetBuffer / 2
            ? 'below target'
            : 'thin',
    // Surfacing this keeps the number honest when a bank has only just linked.
    basis: `trailing 90 days, ${spend.n} transactions${excluded.length ? `, excluding ${excluded.join(' / ')}` : ''}`,
  };
}

// --------------------------------------------------------------------------
// Dividend + interest income, and where it gets reinvested
// --------------------------------------------------------------------------

export function incomeAndReinvestment({ days = 365 } = {}) {
  const since = daysAgo(days);

  const income = db
    .prepare(
      `SELECT t.subtype, s.ticker, s.name AS security_name,
              SUM(ABS(t.amount)) AS amount, COUNT(*) AS n
         FROM investment_transactions t
         LEFT JOIN securities s ON s.security_id = t.security_id
        WHERE t.date >= ? AND t.subtype IN (${placeholders(INCOME_SUBTYPES)})
        GROUP BY t.subtype, s.ticker, s.name`
    )
    .all(since, ...INCOME_SUBTYPES);

  const reinvested = db
    .prepare(
      `SELECT t.subtype, s.ticker, s.name AS security_name,
              SUM(ABS(t.amount)) AS amount, SUM(t.quantity) AS shares, COUNT(*) AS n
         FROM investment_transactions t
         LEFT JOIN securities s ON s.security_id = t.security_id
        WHERE t.date >= ? AND t.subtype IN (${placeholders(REINVEST_SUBTYPES)})
        GROUP BY t.subtype, s.ticker, s.name`
    )
    .all(since, ...REINVEST_SUBTYPES);

  const totalIncome = income.reduce((s, r) => s + r.amount, 0);
  const totalReinvested = reinvested.reduce((s, r) => s + r.amount, 0);

  const rollUp = (rows) => {
    const map = new Map();
    for (const r of rows) {
      const key = r.ticker || r.security_name || 'Cash / unspecified';
      const cur = map.get(key) || { ticker: key, name: r.security_name, amount: 0, shares: 0, n: 0 };
      cur.amount += r.amount;
      cur.shares += r.shares || 0;
      cur.n += r.n;
      map.set(key, cur);
    }
    return [...map.values()]
      .map((r) => ({ ...r, amount: round(r.amount), shares: round(r.shares, 6) }))
      .sort((a, b) => b.amount - a.amount);
  };

  const bySource = rollUp(income);
  const byDestination = rollUp(reinvested);

  // What the destinations are worth today, so "where is it going" connects to
  // the current portfolio rather than floating free.
  const valueByTicker = new Map(positions().positions.map((p) => [p.ticker, p]));
  for (const d of byDestination) {
    const pos = valueByTicker.get(d.ticker);
    d.currentWeight = pos ? pos.weight : null;
  }

  const breakdownBySubtype = (rows) => {
    const map = new Map();
    for (const r of rows) map.set(r.subtype, round((map.get(r.subtype) || 0) + r.amount));
    return [...map.entries()].map(([subtype, amount]) => ({ subtype, amount }));
  };

  const portfolioValue = positions().total;

  return {
    windowDays: days,
    totalIncome: round(totalIncome),
    totalReinvested: round(totalReinvested),
    // Income that landed as cash and stayed there.
    heldAsCash: round(Math.max(0, totalIncome - totalReinvested)),
    reinvestmentRate: pct(totalReinvested, totalIncome),
    trailingYieldPct: pct(totalIncome, portfolioValue),
    incomeBySubtype: breakdownBySubtype(income),
    bySource,
    byDestination,
    hasData: income.length > 0 || reinvested.length > 0,
  };
}

// --------------------------------------------------------------------------

export function fullSnapshot() {
  return {
    generatedAt: new Date().toISOString(),
    netWorth: netWorth(),
    positions: positions(),
    diversification: diversification(),
    runway: cashRunway(),
    income: incomeAndReinvestment(),
  };
}
