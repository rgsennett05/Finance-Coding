/** Valuation Bank — SEC fundamentals into a two-stage DCF per ticker. */
import { percentiles } from './_score.js';

export default {
  id: 'valuation',
  name: 'DCF Analyst',
  building: 'Valuation Bank',
  district: 'Financial',
  role: 'Pulls 10-K cash flows from SEC XBRL and runs a DCF with sensitivity grid.',
  needs: ['scout'],
  tools: ['fundamentals', 'dcf'],
  async run({ board, config, use }) {
    const data = {};
    const warnings = [];
    for (const [ticker, px] of Object.entries(board.scout)) {
      const fundamentals = await use('fundamentals', { ticker });
      if (!fundamentals.available) {
        data[ticker] = { ok: false, reason: fundamentals.reason };
        continue;
      }
      // A DCF against a synthetic price would be meaningless, so say so.
      const price = px.synthetic ? null : px.series.at(-1)?.close;
      data[ticker] = { entityName: fundamentals.entityName, ...(await use('dcf', { fundamentals, price, assumptions: config.dcf })) };
    }
    const tickers = Object.keys(data);
    const pct = percentiles(tickers.map((t) => data[t].marginOfSafety));
    tickers.forEach((t, i) => (data[t].valueScore = pct[i]));

    const valued = tickers.filter((t) => data[t].ok);
    if (valued.length < tickers.length) warnings.push(`${tickers.length - valued.length} tickers could not be valued`);
    return { summary: `Valued ${valued.length}/${tickers.length} with a DCF`, warnings, data };
  },
};
