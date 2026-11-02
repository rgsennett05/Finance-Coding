/** City Hall — combines every district's score into ranked picks. */
export default {
  id: 'mayor',
  name: 'Portfolio Mayor',
  building: 'City Hall',
  district: 'Downtown',
  role: 'Weights momentum, value and risk into one score and names the picks.',
  needs: ['quant', 'valuation', 'risk'],
  tools: [],
  async run({ board, config }) {
    const w = config.weights;
    const ranked = Object.keys(board.quant).map((ticker) => {
      const parts = {
        momentum: board.quant[ticker].momentumScore,
        value: board.valuation[ticker]?.valueScore,
        risk: board.risk[ticker].riskScore,
      };
      // Re-normalize weights over the scores that exist, so a ticker without
      // a DCF is judged on what we know rather than silently scored zero.
      let num = 0, den = 0;
      for (const [k, v] of Object.entries(parts)) if (Number.isFinite(v)) { num += w[k] * v; den += w[k]; }
      return { ticker, score: den ? num / den : null, parts, missing: Object.keys(parts).filter((k) => !Number.isFinite(parts[k])) };
    }).sort((a, b) => (b.score ?? -1) - (a.score ?? -1));

    const picks = ranked.slice(0, config.picks);
    return { summary: `Picks: ${picks.map((p) => p.ticker).join(', ')}`, data: { ranked, picks: picks.map((p) => p.ticker) } };
  },
};
