/**
 * Example figures used only by `npm run snapshot -- --demo`, so the layout can
 * be reviewed and edited before any real account is linked. Every page built
 * from this carries a visible "Example data" banner.
 */
export function demoSnapshot() {
  const days = 45;
  const history = Array.from({ length: days }, (_, i) => {
    const date = new Date(Date.now() - (days - 1 - i) * 86400000).toISOString().slice(0, 10);
    const drift = i * 62;
    const wobble = Math.sin(i / 3.1) * 380 + Math.sin(i / 7.7) * 240;
    const invested = 24800 + drift + wobble;
    const bank = 11200 - i * 9 + Math.sin(i / 5) * 160;
    return { date, bank: Math.round(bank), invested: Math.round(invested), total: Math.round(bank + invested) };
  });

  const last = history[history.length - 1];
  const assets = last.bank + last.invested;

  const positions = [
    { ticker: 'VTI', name: 'Vanguard Total Stock Market ETF', assetClass: 'etf', value: 9120, costBasis: 7480 },
    { ticker: 'NVDA', name: 'NVIDIA Corp', assetClass: 'equity', value: 6240, costBasis: 3100 },
    { ticker: 'SCHD', name: 'Schwab US Dividend Equity ETF', assetClass: 'etf', value: 4380, costBasis: 4010 },
    { ticker: 'AAPL', name: 'Apple Inc', assetClass: 'equity', value: 3260, costBasis: 2890 },
    { ticker: 'O', name: 'Realty Income Corp', assetClass: 'equity', value: 2140, costBasis: 2260 },
    { ticker: 'BND', name: 'Vanguard Total Bond Market ETF', assetClass: 'fixed income', value: 1490, costBasis: 1560 },
    { ticker: 'CASH', name: 'Brokerage cash', assetClass: 'cash', value: 640, costBasis: 640 },
  ];

  const total = positions.reduce((s, p) => s + p.value, 0);
  const enriched = positions.map((p) => {
    const gain = p.value - p.costBasis;
    return {
      ...p,
      account: 'Robinhood Individual',
      quantity: null,
      price: null,
      gain,
      gainPct: Number(((gain / p.costBasis) * 100).toFixed(2)),
      weight: Number(((p.value / total) * 100).toFixed(2)),
    };
  });

  const groupPct = (rows) =>
    rows.map((r) => ({ ...r, pct: Number(((r.value / total) * 100).toFixed(2)) }));

  const monthlyExpenses = 3180;

  return {
    generatedAt: new Date().toISOString(),
    netWorth: {
      bank: last.bank,
      invested: last.invested,
      liabilities: 1240,
      assets,
      netWorth: assets - 1240,
      bankPct: Number(((last.bank / assets) * 100).toFixed(2)),
      investedPct: Number(((last.invested / assets) * 100).toFixed(2)),
      accounts: [],
      history,
    },
    positions: {
      total,
      count: enriched.length,
      unrealizedGain: enriched.reduce((s, p) => s + p.gain, 0),
      positions: enriched,
    },
    diversification: {
      total,
      byAssetClass: groupPct([
        { label: 'ETF', value: 14990 },
        { label: 'Equity', value: 11640 },
        { label: 'Fixed income', value: 1490 },
        { label: 'Cash', value: 640 },
      ]),
      bySector: groupPct([
        { label: 'Broad market fund', value: 10610 },
        { label: 'Technology', value: 9500 },
        { label: 'Real estate', value: 2140 },
        { label: 'Bonds', value: 1490 },
        { label: 'Unclassified', value: 1530 },
      ]),
      byAccount: groupPct([{ label: 'Robinhood Individual', value: total }]),
      hhi: 1985,
      hhiVerdict: 'moderately concentrated',
      concentrationWarnPct: 20,
      concentrated: [{ ticker: 'VTI', weight: 33.55 }, { ticker: 'NVDA', weight: 22.95 }],
      topFiveWeight: 93.4,
      sectorCoverage: 94.4,
    },
    runway: {
      bankTotal: last.bank,
      monthlyExpenses,
      sampleTransactions: 214,
      targetMonths: 6,
      targetBuffer: monthlyExpenses * 6,
      runwayMonths: Number((last.bank / monthlyExpenses).toFixed(1)),
      surplus: last.bank - monthlyExpenses * 6,
      status: 'below target',
      basis: 'trailing 90 days, 214 transactions, excluding Transfer / Payment',
    },
    income: {
      windowDays: 365,
      totalIncome: 612.44,
      totalReinvested: 471.9,
      heldAsCash: 140.54,
      reinvestmentRate: 77.05,
      trailingYieldPct: 2.25,
      incomeBySubtype: [
        { subtype: 'qualified dividend', amount: 402.18 },
        { subtype: 'non-qualified dividend', amount: 148.9 },
        { subtype: 'interest', amount: 61.36 },
      ],
      bySource: [
        { ticker: 'SCHD', name: 'Schwab US Dividend Equity ETF', amount: 238.6, shares: 0, n: 4 },
        { ticker: 'O', name: 'Realty Income Corp', amount: 164.28, shares: 0, n: 12 },
        { ticker: 'VTI', name: 'Vanguard Total Stock Market ETF', amount: 121.4, shares: 0, n: 4 },
        { ticker: 'BND', name: 'Vanguard Total Bond Market ETF', amount: 61.36, shares: 0, n: 12 },
        { ticker: 'AAPL', name: 'Apple Inc', amount: 26.8, shares: 0, n: 4 },
      ],
      byDestination: [
        { ticker: 'SCHD', name: 'Schwab US Dividend Equity ETF', amount: 238.6, shares: 8.9142, n: 4, currentWeight: 16.12 },
        { ticker: 'O', name: 'Realty Income Corp', amount: 164.28, shares: 2.8901, n: 12, currentWeight: 7.87 },
        { ticker: 'BND', name: 'Vanguard Total Bond Market ETF', amount: 61.36, shares: 0.8404, n: 12, currentWeight: 5.48 },
        { ticker: 'AAPL', name: 'Apple Inc', amount: 7.66, shares: 0.0331, n: 1, currentWeight: 11.99 },
      ],
      hasData: true,
    },
  };
}
