import 'dotenv/config';
import path from 'node:path';
import fs from 'node:fs';

const root = path.resolve(import.meta.dirname, '..');

function resolveFromRoot(p) {
  return path.isAbsolute(p) ? p : path.join(root, p);
}

export const config = {
  root,
  port: Number(process.env.PORT || 4000),
  dbPath: resolveFromRoot(process.env.DB_PATH || './data/finance.db'),
  snapshotDir: path.join(root, 'snapshots'),

  plaid: {
    clientId: process.env.PLAID_CLIENT_ID || '',
    secret: process.env.PLAID_SECRET || '',
    env: process.env.PLAID_ENV || 'sandbox',
    products: (process.env.PLAID_PRODUCTS || 'transactions,investments')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    countryCodes: (process.env.PLAID_COUNTRY_CODES || 'US')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  },

  sec: {
    // SEC blocks requests without a contact-bearing User-Agent.
    userAgent: process.env.SEC_USER_AGENT || '',
  },

  finnhubKey: process.env.FINNHUB_API_KEY || '',
};

export function ensureDirs() {
  for (const dir of [path.dirname(config.dbPath), config.snapshotDir]) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

/** Throws with an actionable message when Plaid credentials are missing. */
export function requirePlaid() {
  if (!config.plaid.clientId || !config.plaid.secret) {
    throw new Error(
      'Plaid credentials missing. Copy .env.example to .env and set PLAID_CLIENT_ID and PLAID_SECRET ' +
        '(https://dashboard.plaid.com/developers/keys).'
    );
  }
}
