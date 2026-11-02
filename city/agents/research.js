/** Research Library — Claude writes a short memo on each pick. */
const SYSTEM = `You are a buy-side equity analyst writing for a single individual investor who is learning.
You receive numbers computed by other models. Explain what they imply, what would make the thesis wrong,
and which number you trust least. Be specific and brief (under 150 words per ticker). This is research,
not a recommendation to trade.`;

export default {
  id: 'research',
  name: 'Research Librarian',
  building: 'Research Library',
  district: 'Downtown',
  role: 'Asks Claude to write a plain-English memo on the Mayor\'s picks.',
  needs: ['mayor', 'quant', 'valuation', 'risk'],
  tools: ['claude'],
  async run({ board, use }) {
    const picks = board.mayor.picks;
    const facts = picks.map((t) => ({
      ticker: t,
      momentum: board.quant[t],
      valuation: { ...board.valuation[t], projection: undefined, sensitivity: board.valuation[t]?.sensitivity },
      risk: board.risk[t],
      composite: board.mayor.ranked.find((r) => r.ticker === t),
    }));
    const res = await use('claude', {
      system: SYSTEM,
      prompt: `Here are tonight's picks with every number the city computed:\n\n${JSON.stringify(facts, null, 1)}`,
    });
    if (!res.available || !res.text) return { status: 'closed', summary: `Library closed: ${res.reason}`, data: null };
    return { summary: `Memo written on ${picks.join(', ')}`, data: { model: res.model, memo: res.text } };
  },
};
