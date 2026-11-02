/**
 * Mod: live prices from Finnhub (https://finnhub.io).
 *
 * The free tier gives real-time US quotes but not price history, so this mod
 * WRAPS the built-in `prices` tool instead of replacing it: history still comes
 * from Yahoo/Stooq, and the latest point is overwritten with Finnhub's live
 * quote. Every agent downstream sees live prices without changing.
 *
 * Needs FINNHUB_API_KEY (in .env locally, or as a GitHub Actions secret).
 */
const API = 'https://finnhub.io/api/v1';

export async function liveQuote(ticker, key) {
  const res = await fetch(`${API}/quote?symbol=${encodeURIComponent(ticker)}&token=${key}`);
  if (res.status === 429) throw new Error('Finnhub rate limit (60/min on the free tier)');
  if (!res.ok) throw new Error(`Finnhub ${res.status}`);
  const q = await res.json();
  if (!q.t || !Number.isFinite(q.c) || q.c === 0) throw new Error('no quote (unknown symbol?)');
  return {
    price: q.c,
    change: q.d,
    changePct: q.dp / 100,
    high: q.h,
    low: q.l,
    open: q.o,
    prevClose: q.pc,
    at: new Date(q.t * 1000).toISOString(),
  };
}

/** Put the live price on the series: replace today's bar, or append one. */
export function applyQuote(series, quote) {
  const day = quote.at.slice(0, 10);
  const rest = series.at(-1)?.date === day ? series.slice(0, -1) : series;
  return [...rest, { date: day, close: quote.price, live: true }];
}

export default {
  name: 'finnhub-live',
  description: 'Overlays real-time Finnhub quotes on the daily price history.',
  async register(registry) {
    const key = process.env.FINNHUB_API_KEY;
    if (!key) throw new Error('FINNHUB_API_KEY not set');
    const history = registry.get('prices');

    registry.add(
      {
        name: 'prices',
        description: 'Daily price history (Yahoo/Stooq) with the latest point replaced by a live Finnhub quote.',
        async run(input, ctx = {}) {
          const base = await history.run(input, ctx);
          if (ctx.offline || base.synthetic) return base; // never mix a real quote into fake history
          try {
            const quote = await liveQuote(input.ticker, key);
            return { ...base, source: `${base.source}+finnhub`, live: quote, series: applyQuote(base.series, quote) };
          } catch (err) {
            ctx.log?.(`finnhub: ${input.ticker} — ${err.message}; using ${base.source} close`);
            return base;
          }
        },
      },
      { source: 'mod:finnhub-live' }
    );
    return 'live quotes layered on top of daily history';
  },
};
