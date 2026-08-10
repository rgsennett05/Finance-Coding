#!/usr/bin/env node
import { refreshSignals, recentSignals, listFollows } from '../src/signals/index.js';

const follows = listFollows();
if (follows.length === 0) {
  console.log(`
  Not following anyone yet. Add someone first:

    npm run follow -- institution 1067983 "Berkshire Hathaway"
    npm run follow -- insider AAPL
    npm run follow -- congress "Nancy Pelosi"
`);
  process.exit(0);
}

console.log(`Refreshing disclosures for ${follows.length} followed ${follows.length === 1 ? 'entity' : 'entities'}…\n`);

const sources = process.argv[2] ? [process.argv[2]] : undefined;
for (const r of await refreshSignals({ sources })) {
  if (r.error) console.log(`  ! ${r.source}${r.actor ? ` (${r.actor})` : ''}: ${r.error}`);
  else if (r.skipped) console.log(`  - ${r.source}: skipped (${r.skipped})`);
  else
    console.log(
      `  ✓ ${r.source}${r.actor ? ` (${r.actor})` : ''}: ${r.saved ?? 0} rows` +
        (r.daysStale != null ? ` · reported ${r.daysStale} days ago` : '') +
        (r.note ? ` · ${r.note}` : '')
    );
}

const rows = recentSignals({ limit: 20 });
console.log(`\n  Latest ${rows.length} disclosures:\n`);
for (const s of rows) {
  const size = s.amount_low ? `$${Math.round(s.amount_low).toLocaleString()}` : s.quantity ? `${s.quantity} sh` : '';
  console.log(
    `  ${(s.filed_at || '').padEnd(11)} ${String(s.actor_label).slice(0, 34).padEnd(35)} ` +
      `${String(s.action).padEnd(10)} ${String(s.ticker || s.security_name || '').slice(0, 22).padEnd(23)} ${size}`
  );
}
console.log('\n  Reminder: these are filings, not live trades. Check the lag before acting.\n');
