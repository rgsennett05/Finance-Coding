#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { config, ensureDirs } from '../src/config.js';
import { renderSnapshot } from '../src/render.js';

const args = process.argv.slice(2);
const has = (flag) => args.includes(flag);
const valueOf = (flag, fallback) => {
  const i = args.indexOf(flag);
  return i !== -1 && args[i + 1] ? args[i + 1] : fallback;
};

if (has('--help')) {
  console.log(`
  npm run snapshot                 build a page from your synced data
  npm run snapshot -- --redact     mask every dollar figure, keep the percentages
  npm run snapshot -- --demo       example figures, for reviewing the layout
  npm run snapshot -- --json       also write the raw snapshot data
  npm run snapshot -- --out FILE   write somewhere specific
`);
  process.exit(0);
}

ensureDirs();

const demo = has('--demo');
const redact = has('--redact');

// The demo path must not touch the database, so it can run before any linking.
const snapshot = demo
  ? (await import('../src/demo-data.js')).demoSnapshot()
  : (await import('../src/analytics.js')).fullSnapshot();

const html = renderSnapshot(snapshot, {
  demo,
  redact,
  title: valueOf('--title', 'Money'),
});

const outPath = path.resolve(
  valueOf('--out', path.join(config.snapshotDir, `${demo ? 'demo' : 'snapshot'}.html`))
);
fs.writeFileSync(outPath, html);
console.log(`  Wrote ${outPath}`);

if (has('--json')) {
  const jsonPath = outPath.replace(/\.html$/, '.json');
  fs.writeFileSync(jsonPath, JSON.stringify(snapshot, null, 2));
  console.log(`  Wrote ${jsonPath}`);
}

if (!demo && snapshot.positions.count === 0 && snapshot.netWorth.accounts.length === 0) {
  console.log('\n  Nothing linked yet — this page will be empty. Run `npm start` and link an account,');
  console.log('  or preview the layout with: npm run snapshot -- --demo\n');
}
