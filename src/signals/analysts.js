import { config } from '../config.js';

/**
 * Analyst ratings are the one feed here with no free public source - the SEC
 * publishes filings, not Wall Street opinions. Finnhub's free tier covers
 * recommendation trends; price targets and analyst-level track records sit
 * behind their paid plans. With no key set, every call degrades to an empty
 * result rather than throwing, so the rest of the dashboard still renders.
 */

const BASE = 'https://finnhub.io/api/v1';

export const isConfigured = () => Boolean(config.finnhubKey);

async function finnhub(path, params = {}) {
  if (!isConfigured()) return null;
  const url = new URL(`${BASE}${path}`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  url.searchParams.set('token', config.finnhubKey);

  const res = await fetch(url);
  if (res.status === 429) throw new Error('Finnhub rate limit hit - slow down or upgrade the plan.');
  if (!res.ok) throw new Error(`Finnhub ${path} failed (${res.status}).`);
  return res.json();
}

/** Aggregate buy/hold/sell counts for a ticker, most recent month first. */
export async function recommendationTrend(ticker) {
  const data = await finnhub('/stock/recommendation', { symbol: ticker });
  if (!Array.isArray(data) || data.length === 0) return null;

  const latest = data[0];
  const bullish = (latest.strongBuy || 0) + (latest.buy || 0);
  const bearish = (latest.strongSell || 0) + (latest.sell || 0);
  const total = bullish + bearish + (latest.hold || 0);

  return {
    ticker,
    period: latest.period,
    strongBuy: latest.strongBuy || 0,
    buy: latest.buy || 0,
    hold: latest.hold || 0,
    sell: latest.sell || 0,
    strongSell: latest.strongSell || 0,
    analystCount: total,
    consensus: total === 0 ? 'no coverage' : bullish / total >= 0.6 ? 'bullish' : bearish / total >= 0.4 ? 'bearish' : 'mixed',
    bullishPct: total ? Number(((bullish / total) * 100).toFixed(1)) : 0,
    history: data.slice(0, 6),
  };
}

/** Consensus price target vs. where the stock trades now. */
export async function priceTarget(ticker) {
  try {
    const [target, quote] = await Promise.all([
      finnhub('/stock/price-target', { symbol: ticker }),
      finnhub('/quote', { symbol: ticker }),
    ]);
    if (!target?.targetMean) return null;

    const current = quote?.c ?? null;
    return {
      ticker,
      current,
      mean: target.targetMean,
      high: target.targetHigh,
      low: target.targetLow,
      upsidePct:
        current > 0 ? Number((((target.targetMean - current) / current) * 100).toFixed(1)) : null,
      updated: target.lastUpdated,
    };
  } catch (err) {
    // Price targets are a paid endpoint; a 403 here is expected on free tier.
    if (String(err.message).includes('403')) return null;
    throw err;
  }
}

/** Ratings for the tickers you actually hold. */
export async function ratingsForTickers(tickers) {
  if (!isConfigured()) {
    return { configured: false, ratings: [], note: 'Set FINNHUB_API_KEY in .env to enable analyst ratings.' };
  }

  const ratings = [];
  for (const ticker of tickers) {
    try {
      const [trend, target] = await Promise.all([recommendationTrend(ticker), priceTarget(ticker)]);
      if (trend || target) ratings.push({ ticker, trend, target });
    } catch {
      // Skip the ticker rather than abandoning the batch.
    }
    await new Promise((r) => setTimeout(r, 1100)); // free tier: 60 calls/min
  }

  return { configured: true, ratings };
}
