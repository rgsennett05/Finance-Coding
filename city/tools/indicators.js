/**
 * indicators — technical statistics computed from a close series.
 * Pure math, no network. A mod can replace this with a library version
 * (see city/mods/technical-indicators).
 */

export const returns = (closes) => closes.slice(1).map((c, i) => c / closes[i] - 1);

export const sma = (closes, n) =>
  closes.length < n ? null : closes.slice(-n).reduce((a, b) => a + b, 0) / n;

export function rsi(closes, n = 14) {
  if (closes.length <= n) return null;
  let gain = 0, loss = 0;
  for (let i = 1; i <= n; i++) {
    const d = closes[i] - closes[i - 1];
    d >= 0 ? (gain += d) : (loss -= d);
  }
  gain /= n; loss /= n;
  for (let i = n + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    gain = (gain * (n - 1) + Math.max(d, 0)) / n;
    loss = (loss * (n - 1) + Math.max(-d, 0)) / n;
  }
  return loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
}

export function annualVol(closes) {
  const r = returns(closes);
  if (r.length < 2) return null;
  const mean = r.reduce((a, b) => a + b, 0) / r.length;
  const variance = r.reduce((a, b) => a + (b - mean) ** 2, 0) / (r.length - 1);
  return Math.sqrt(variance * 252);
}

export function maxDrawdown(closes) {
  let peak = -Infinity, worst = 0;
  for (const c of closes) {
    peak = Math.max(peak, c);
    worst = Math.min(worst, c / peak - 1);
  }
  return worst;
}

const change = (closes, n) => (closes.length > n ? closes.at(-1) / closes.at(-1 - n) - 1 : null);

export function computeAll(closes) {
  return {
    last: closes.at(-1),
    sma50: sma(closes, 50),
    sma200: sma(closes, 200),
    rsi14: rsi(closes, 14),
    ret1m: change(closes, 21),
    ret3m: change(closes, 63),
    ret6m: change(closes, 126),
    // 12-1 momentum: last year's return excluding the most recent month.
    mom12_1: closes.length > 252 ? closes.at(-22) / closes.at(-253) - 1 : change(closes.slice(0, -21), closes.length - 22),
    vol: annualVol(closes),
    maxDrawdown: maxDrawdown(closes),
  };
}

export default {
  name: 'indicators',
  description: 'SMA 50/200, RSI-14, 1/3/6-month and 12-1 momentum, annualized volatility, max drawdown.',
  async run({ closes }) {
    return computeAll(closes);
  },
};
