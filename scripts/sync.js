#!/usr/bin/env node
import { syncAll } from '../src/plaid/sync.js';
import { fullSnapshot } from '../src/analytics.js';

const money = (n) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });

const { items } = await syncAll({
  onProgress: (r) => {
    const bits = [
      r.accounts != null && `${r.accounts} accounts`,
      r.holdings != null && r.holdings !== 'n/a' && `${r.holdings} holdings`,
      r.bankTransactions?.added != null && `${r.bankTransactions.added} bank tx`,
      r.investmentTransactions != null && r.investmentTransactions !== 'n/a' &&
        `${r.investmentTransactions} inv tx`,
    ].filter(Boolean);
    console.log(`  ${r.item}: ${bits.join(', ') || 'nothing new'}`);
    if (r.needsReauth) console.log(`    ! login expired — re-link ${r.item} from the Settings tab`);
    for (const e of r.errors) console.log(`    ! ${e}`);
  },
});

if (items.length === 0) {
  console.log('\nNothing linked yet. Run `npm start` and link an account first.\n');
  process.exit(0);
}

const s = fullSnapshot();
console.log(`
  Net worth      ${money(s.netWorth.netWorth)}
  Bank           ${money(s.netWorth.bank)}  (${s.netWorth.bankPct}%)
  Invested       ${money(s.netWorth.invested)}  (${s.netWorth.investedPct}%)
  Cash runway    ${s.runway.runwayMonths ?? '—'} months  (${s.runway.status})
  Positions      ${s.positions.count}, ${s.diversification.hhiVerdict}
  Income 12mo    ${money(s.income.totalIncome)}, ${s.income.reinvestmentRate}% reinvested
`);
