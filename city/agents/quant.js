/** Quant Tower — technical indicators and a momentum score per ticker. */
import { percentiles, avg } from './_score.js';

export default {
  id: 'quant',
  name: 'Momentum Quant',
  building: 'Quant Tower',
  district: 'Analytics',
  role: 'Scores trend and momentum (12-1 momentum, 3-month return, 200-day trend).',
  needs: ['scout'],
  tools: ['indicators'],
  async run({ board, use }) {
    const tickers = Object.keys(board.scout);
    const ind = {};
    for (const t of tickers) ind[t] = await use('indicators', { closes: board.scout[t].series.map((p) => p.close) });

    const p12 = percentiles(tickers.map((t) => ind[t].mom12_1));
    const p3 = percentiles(tickers.map((t) => ind[t].ret3m));
    const data = {};
    tickers.forEach((t, i) => {
      const trend = ind[t].sma200 ? (ind[t].last > ind[t].sma200 ? 1 : 0) : null;
      data[t] = { ...ind[t], aboveSma200: trend === 1, momentumScore: avg([p12[i], p3[i], trend]) };
    });
    const leader = tickers.reduce((a, b) => (data[b].momentumScore > data[a].momentumScore ? b : a));
    return { summary: `Momentum leader: ${leader}`, data };
  },
};
