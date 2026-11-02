/** Risk Office — volatility, drawdown and correlation to the watchlist basket. */
import { percentiles, avg } from './_score.js';
import { returns } from '../tools/indicators.js';

function correlation(a, b) {
  const n = Math.min(a.length, b.length);
  const x = a.slice(-n), y = b.slice(-n);
  const mx = avg(x), my = avg(y);
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) {
    sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2;
  }
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : null;
}

export default {
  id: 'risk',
  name: 'Risk Officer',
  building: 'Risk Office',
  district: 'Civic',
  role: 'Penalizes high volatility and deep drawdowns; reports correlation to the basket.',
  needs: ['scout', 'quant'],
  tools: [],
  async run({ board }) {
    const tickers = Object.keys(board.quant);
    const rets = Object.fromEntries(tickers.map((t) => [t, returns(board.scout[t].series.map((p) => p.close))]));
    const len = Math.min(...tickers.map((t) => rets[t].length));
    const basket = Array.from({ length: len }, (_, i) => avg(tickers.map((t) => rets[t].at(i - len))));

    const pv = percentiles(tickers.map((t) => board.quant[t].vol));
    const pd = percentiles(tickers.map((t) => -board.quant[t].maxDrawdown));
    const data = {};
    tickers.forEach((t, i) => {
      data[t] = {
        vol: board.quant[t].vol,
        maxDrawdown: board.quant[t].maxDrawdown,
        corrToBasket: correlation(rets[t], basket),
        riskScore: avg([1 - pv[i], 1 - pd[i]]), // higher = safer
      };
    });
    const riskiest = tickers.reduce((a, b) => (data[b].riskScore < data[a].riskScore ? b : a));
    return { summary: `Highest risk: ${riskiest}`, data };
  },
};
