/**
 * dcf — a two-stage discounted cash flow model.
 *
 *   Stage 1: free cash flow grows at a starting rate g0 (historical FCF CAGR,
 *            clamped to [minGrowth, maxGrowth]) that fades linearly to the
 *            terminal rate over `projectionYears`.
 *   Stage 2: Gordon growth terminal value  TV = FCF_N × (1+gT) / (r − gT).
 *
 *   Enterprise value = Σ PV(FCF_t) + PV(TV)
 *   Equity value     = EV + cash − debt
 *   Intrinsic/share  = equity / shares
 *
 * Also returns a sensitivity grid over discount rate (±1%) and terminal
 * growth (±0.5%), because a single DCF number is false precision.
 */

export function cagr(rows) {
  const pos = rows.filter((r) => r.value > 0);
  if (pos.length < 2) return null;
  const years = (new Date(pos.at(-1).end) - new Date(pos[0].end)) / (365.25 * 86400000);
  return years > 0 ? (pos.at(-1).value / pos[0].value) ** (1 / years) - 1 : null;
}

export function valuePerShare({ baseFcf, g0, years, r, gT, cash, debt, shares }) {
  if (!(r > gT)) return null;
  let fcf = baseFcf, pv = 0;
  const path = [];
  for (let t = 1; t <= years; t++) {
    const g = g0 + (gT - g0) * ((t - 1) / Math.max(years - 1, 1));
    fcf *= 1 + g;
    const disc = fcf / (1 + r) ** t;
    pv += disc;
    path.push({ year: t, growth: g, fcf, pv: disc });
  }
  const tv = (fcf * (1 + gT)) / (r - gT);
  const pvTv = tv / (1 + r) ** years;
  const equity = pv + pvTv + (cash || 0) - (debt || 0);
  return { perShare: equity / shares, enterpriseValue: pv + pvTv, pvTerminal: pvTv, terminalShare: pvTv / (pv + pvTv), path };
}

export function runDcf(fund, price, a) {
  const fcf = fund.freeCashFlow ?? [];
  if (fund.hasAnnualReports === false) return { ok: false, reason: 'no annual 10-K cash flows under this SEC filer (new filer ID, or a bank/insurer that doesn\'t report capex)' };
  if (!fcf.length) return { ok: false, reason: 'no year with both operating cash flow and capex reported' };
  if (!fund.sharesOutstanding) return { ok: false, reason: 'no share count in SEC filings' };
  const ageYears = (Date.now() - new Date(fcf.at(-1).end)) / (365.25 * 86400000);
  if (ageYears > 2) return { ok: false, reason: `latest free cash flow is from ${fcf.at(-1).end} — too stale to value` };
  // Normalize: average of the last 3 years smooths one-off swings.
  const recent = fcf.slice(-3).map((r) => r.value);
  const baseFcf = recent.reduce((s, v) => s + v, 0) / recent.length;
  if (baseFcf <= 0) return { ok: false, reason: 'negative normalized free cash flow — DCF not meaningful' };

  const hist = cagr(fcf);
  const g0 = Math.min(a.maxGrowth, Math.max(a.minGrowth, hist ?? a.terminalGrowth));
  const base = { baseFcf, g0, years: a.projectionYears, cash: fund.cash, debt: fund.debt, shares: fund.sharesOutstanding };
  const main = valuePerShare({ ...base, r: a.discountRate, gT: a.terminalGrowth });

  const grid = [];
  for (const dr of [-0.01, 0, 0.01]) {
    for (const dg of [-0.005, 0, 0.005]) {
      const v = valuePerShare({ ...base, r: a.discountRate + dr, gT: a.terminalGrowth + dg });
      grid.push({ r: +(a.discountRate + dr).toFixed(4), gT: +(a.terminalGrowth + dg).toFixed(4), perShare: v?.perShare ?? null });
    }
  }

  return {
    ok: true,
    assumptions: { ...a, normalizedFcf: baseFcf, historicalFcfCagr: hist, startingGrowth: g0 },
    intrinsicPerShare: main.perShare,
    price,
    marginOfSafety: price ? main.perShare / price - 1 : null,
    terminalShareOfValue: main.terminalShare,
    projection: main.path,
    sensitivity: grid,
  };
}

export default {
  name: 'dcf',
  description: 'Two-stage DCF with growth fade, Gordon terminal value and a 3×3 sensitivity grid.',
  async run({ fundamentals, price, assumptions }) {
    return runDcf(fundamentals, price, assumptions);
  },
};
