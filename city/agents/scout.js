/** Market Exchange — gathers price history for every ticker on the watchlist. */
export default {
  id: 'scout',
  name: 'Market Scout',
  building: 'Market Exchange',
  district: 'Harbor',
  role: 'Collects daily prices for the watchlist.',
  needs: [],
  tools: ['prices'],
  async run({ config, use }) {
    const prices = {};
    for (const ticker of config.watchlist) {
      prices[ticker] = await use('prices', { ticker, days: config.lookbackDays });
    }
    const synthetic = Object.values(prices).filter((p) => p.synthetic).length;
    return {
      summary: `Priced ${config.watchlist.length} tickers` + (synthetic ? ` (${synthetic} synthetic — data source unreachable)` : ''),
      warnings: synthetic ? [`${synthetic} series are synthetic, not market data`] : [],
      data: prices,
    };
  },
};
