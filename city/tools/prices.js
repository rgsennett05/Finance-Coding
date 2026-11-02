/**
 * prices — daily closes for one ticker.
 *
 * Tries Yahoo's public chart endpoint, then Stooq's CSV export. Neither needs
 * a key. If both fail (offline laptop, blocked network) it returns a seeded
 * synthetic series flagged `synthetic: true`, so every downstream agent still
 * runs and the city map makes it obvious the numbers are not real.
 */

const UA = 'Mozilla/5.0 (TickerCity research bot)';

async function fromYahoo(ticker, days) {
  const range = days > 365 ? '2y' : '1y';
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=${range}&interval=1d`;
  const res = await fetch(url, { headers: { 'User-Agent': UA } });
  if (!res.ok) throw new Error(`Yahoo ${res.status}`);
  const json = await res.json();
  const r = json.chart?.result?.[0];
  const closes = r?.indicators?.adjclose?.[0]?.adjclose ?? r?.indicators?.quote?.[0]?.close;
  if (!r?.timestamp || !closes) throw new Error('Yahoo: empty series');
  return r.timestamp
    .map((t, i) => ({ date: new Date(t * 1000).toISOString().slice(0, 10), close: closes[i] }))
    .filter((p) => Number.isFinite(p.close));
}

async function fromStooq(ticker) {
  const url = `https://stooq.com/q/d/l/?s=${ticker.toLowerCase()}.us&i=d`;
  const res = await fetch(url, { headers: { 'User-Agent': UA } });
  if (!res.ok) throw new Error(`Stooq ${res.status}`);
  const rows = (await res.text()).trim().split('\n').slice(1);
  const out = rows
    .map((line) => line.split(','))
    .map(([date, , , , close]) => ({ date, close: Number(close) }))
    .filter((p) => Number.isFinite(p.close));
  if (!out.length) throw new Error('Stooq: empty series');
  return out;
}

/** Deterministic random walk so offline runs are repeatable. */
export function syntheticSeries(ticker, days = 260) {
  let seed = [...ticker].reduce((a, c) => a * 31 + c.charCodeAt(0), 7) >>> 0;
  const rand = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32);
  const drift = (rand() - 0.45) * 0.002;
  const vol = 0.01 + rand() * 0.02;
  let price = 50 + rand() * 250;
  const start = Date.now() - days * 86400000;
  const out = [];
  for (let i = 0; i < days; i++) {
    const z = Math.sqrt(-2 * Math.log(rand() || 1e-9)) * Math.cos(2 * Math.PI * rand());
    price *= Math.exp(drift + vol * z);
    out.push({ date: new Date(start + i * 86400000).toISOString().slice(0, 10), close: +price.toFixed(2) });
  }
  return out;
}

export default {
  name: 'prices',
  description: 'Daily closing prices for a ticker (Yahoo → Stooq → synthetic fallback).',
  async run({ ticker, days = 365 }, ctx = {}) {
    if (!ctx.offline) {
      for (const [source, fn] of [['yahoo', fromYahoo], ['stooq', fromStooq]]) {
        try {
          const series = (await fn(ticker, days)).slice(-days);
          return { ticker, source, synthetic: false, series };
        } catch (err) {
          ctx.log?.(`prices: ${source} failed for ${ticker} (${err.message})`);
        }
      }
    }
    return { ticker, source: 'synthetic', synthetic: true, series: syntheticSeries(ticker) };
  },
};
