#!/usr/bin/env node
/**
 * First-run setup. Writes .env, seeds a starting follow list, and explains what
 * each answer is for. Every question can be skipped - the app runs with
 * whatever is filled in and tells you what is still missing.
 */
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline/promises';
import { execSync } from 'node:child_process';

const root = path.resolve(import.meta.dirname, '..');
const envPath = path.join(root, '.env');

const bold = (s) => `\x1b[1m${s}\x1b[0m`;
const dim = (s) => `\x1b[2m${s}\x1b[0m`;
const green = (s) => `\x1b[32m${s}\x1b[0m`;

/** A plausible default, but never a shared CI or placeholder address. */
function guessEmail() {
  try {
    const email = execSync('git config user.email', { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    return /noreply|example\.com|localhost/i.test(email) ? '' : email;
  } catch {
    return '';
  }
}

function writeEnv({ email = '', clientId = '', secret = '', finnhub = '' }) {
  fs.writeFileSync(
    envPath,
    `# Written by \`npm run setup\`. Safe to edit by hand.
PLAID_CLIENT_ID=${clientId}
PLAID_SECRET=${secret}
PLAID_ENV=sandbox
PLAID_PRODUCTS=transactions,investments
PLAID_COUNTRY_CODES=US

# The SEC serves filings free but requires a contact address on every request.
SEC_USER_AGENT=FinanceCoding personal-tracker ${email}

FINNHUB_API_KEY=${finnhub}

PORT=4000
DB_PATH=./data/finance.db
`
  );
}

/** Give the investor feeds something to show without anyone learning the CLI. */
async function seedFollows() {
  try {
    const { listFollows, addFollow, SUGGESTED_INSTITUTIONS } = await import('../src/signals/index.js');
    if (listFollows().length > 0) return 0;
    for (const s of SUGGESTED_INSTITUTIONS) addFollow('institution', s.cik, s.label);
    return SUGGESTED_INSTITUTIONS.length;
  } catch {
    return 0; // Seeding is a convenience; never let it block setup.
  }
}

export async function runSetup({ force = false } = {}) {
  if (fs.existsSync(envPath) && !force) return false;

  // Piped or non-interactive shells cannot answer questions - asking would hang
  // forever waiting on a stdin that is already closed.
  if (!process.stdin.isTTY) {
    writeEnv({ email: guessEmail() });
    await seedFollows();
    console.log(
      `\n${green('✓')} Wrote a starter .env.\n` +
        `  This shell is not interactive, so nothing was asked. Open .env and fill in\n` +
        `  your email and Plaid keys, or run ${bold('npm run setup')} in a normal terminal.\n`
    );
    return true;
  }

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  // Ctrl-D / Ctrl-C mid-question should exit cleanly, not leave a dangling await.
  let aborted = false;
  rl.on('close', () => {
    aborted = true;
  });

  const ask = async (question, fallback = '') => {
    if (aborted) return fallback;
    try {
      const answer = (await rl.question(question)).trim();
      return answer || fallback;
    } catch {
      aborted = true;
      return fallback;
    }
  };

  console.log(`
${bold('Setting up Finance Coding')}
${dim('Three questions. Press Enter to skip any of them.')}
`);

  console.log(bold('1. Your email'));
  console.log(dim('   The SEC gives away insider and fund filings for free, but they'));
  console.log(dim('   require a contact address on each request. Nothing is sent to it.\n'));
  const guess = guessEmail();
  const email = await ask(`   Email${guess ? ` ${dim(`[${guess}]`)}` : ''}: `, guess);

  console.log(`\n${bold('2. Plaid keys')} ${dim('(for linking your bank + Robinhood)')}`);
  console.log(dim('   Free signup: https://dashboard.plaid.com/signup'));
  console.log(dim('   Then Developers -> Keys. Copy client_id and the Sandbox secret.'));
  console.log(dim('   Press Enter to skip - everything else still works.\n'));
  const clientId = await ask('   client_id: ');
  const secret = clientId ? await ask('   Sandbox secret: ') : '';

  console.log(`\n${bold('3. Analyst ratings')} ${dim('(optional)')}`);
  console.log(dim('   Free key: https://finnhub.io/register - press Enter to skip.\n'));
  const finnhub = await ask('   Finnhub key: ');

  rl.close();

  writeEnv({ email, clientId, secret, finnhub });
  console.log(`\n${green('✓')} Saved to .env`);

  const seeded = await seedFollows();
  if (seeded) console.log(`${green('✓')} Following ${seeded} well-known funds to start`);

  const missing = [];
  if (!email) missing.push('your email — SEC filings stay off until it is set');
  if (!clientId || !secret) missing.push('Plaid keys — account linking stays off until they are set');
  if (missing.length) {
    console.log(`\n${dim('Add these to .env whenever you want them:')}`);
    for (const m of missing) console.log(dim(`  - ${m}`));
  }

  console.log('');
  return true;
}

// `npm run setup` re-runs against an existing .env.
if (import.meta.filename === process.argv[1]) {
  await runSetup({ force: true });
  console.log(`${bold('Done.')} Now run: ${bold('npm start')}\n`);
}
