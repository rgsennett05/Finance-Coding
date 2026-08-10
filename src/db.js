import Database from 'better-sqlite3';
import { config, ensureDirs } from './config.js';

ensureDirs();

export const db = new Database(config.dbPath);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
-- A linked institution (one Plaid Item = one login at one bank/broker).
CREATE TABLE IF NOT EXISTS items (
  item_id             TEXT PRIMARY KEY,
  access_token        TEXT NOT NULL,
  institution_id      TEXT,
  institution_name    TEXT,
  transactions_cursor TEXT,
  last_synced_at      TEXT,
  created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
  account_id        TEXT PRIMARY KEY,
  item_id           TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  name              TEXT,
  official_name     TEXT,
  mask              TEXT,
  type              TEXT,   -- depository | investment | credit | loan
  subtype           TEXT,   -- checking | savings | brokerage | ira | 401k ...
  current_balance   REAL,
  available_balance REAL,
  iso_currency      TEXT DEFAULT 'USD',
  updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS securities (
  security_id       TEXT PRIMARY KEY,
  ticker            TEXT,
  name              TEXT,
  type              TEXT,   -- equity | etf | mutual fund | fixed income | cash | cryptocurrency | derivative | other
  close_price       REAL,
  close_price_as_of TEXT,
  iso_currency      TEXT DEFAULT 'USD',
  is_cash_equivalent INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS holdings (
  account_id        TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
  security_id       TEXT NOT NULL REFERENCES securities(security_id),
  quantity          REAL,
  cost_basis        REAL,
  institution_price REAL,
  institution_value REAL,
  iso_currency      TEXT DEFAULT 'USD',
  updated_at        TEXT,
  PRIMARY KEY (account_id, security_id)
);

CREATE TABLE IF NOT EXISTS bank_transactions (
  transaction_id TEXT PRIMARY KEY,
  account_id     TEXT NOT NULL,
  date           TEXT NOT NULL,
  name           TEXT,
  merchant_name  TEXT,
  amount         REAL,        -- Plaid sign convention: positive = money OUT
  category       TEXT,
  pending        INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bank_tx_date ON bank_transactions(date);

CREATE TABLE IF NOT EXISTS investment_transactions (
  investment_transaction_id TEXT PRIMARY KEY,
  account_id  TEXT NOT NULL,
  security_id TEXT,
  date        TEXT NOT NULL,
  name        TEXT,
  quantity    REAL,
  amount      REAL,           -- positive = cash out of the account (a buy)
  price       REAL,
  fees        REAL,
  type        TEXT,           -- buy | sell | cash | fee | transfer | cancel
  subtype     TEXT            -- 'dividend reinvestment', 'dividend', 'interest' ...
);
CREATE INDEX IF NOT EXISTS idx_inv_tx_date ON investment_transactions(date);
CREATE INDEX IF NOT EXISTS idx_inv_tx_subtype ON investment_transactions(subtype);

-- One row per day we synced, so the bank-vs-invested ratio has a trend line.
CREATE TABLE IF NOT EXISTS balance_history (
  as_of         TEXT PRIMARY KEY,
  bank_total    REAL,
  invested_total REAL,
  credit_total  REAL,
  recorded_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prefs (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- People and institutions whose disclosed trades you want surfaced.
CREATE TABLE IF NOT EXISTS follows (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  kind       TEXT NOT NULL,   -- congress | institution | insider | analyst
  identifier TEXT NOT NULL,   -- CIK, member name, or analyst id
  label      TEXT,
  active     INTEGER DEFAULT 1,
  added_at   TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (kind, identifier)
);

-- Normalised disclosure rows from every signal source.
CREATE TABLE IF NOT EXISTS signals (
  id            TEXT PRIMARY KEY,   -- deterministic hash, so re-syncs dedupe
  source        TEXT NOT NULL,      -- congress | 13f | form4 | analyst
  actor         TEXT,               -- CIK or canonical name
  actor_label   TEXT,               -- human-readable
  ticker        TEXT,
  security_name TEXT,
  action        TEXT,               -- buy | sell | hold | new | exit | upgrade | downgrade
  quantity      REAL,
  amount_low    REAL,
  amount_high   REAL,
  transacted_at TEXT,               -- when the trade happened
  filed_at      TEXT,               -- when it became public
  url           TEXT,
  raw           TEXT,
  fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_signals_filed ON signals(filed_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);

-- Plaid does not return sector, so sector-level diversification is filled in
-- here (bundled defaults + anything you tag yourself).
CREATE TABLE IF NOT EXISTS sector_map (
  ticker      TEXT PRIMARY KEY,
  sector      TEXT,
  asset_class TEXT,
  source      TEXT DEFAULT 'manual'
);
`);

const DEFAULT_PREFS = {
  // Cash runway: how many months of expenses you want sitting in the bank.
  target_buffer_months: '6',
  // Ignore transfers into brokerage when computing "expenses".
  exclude_transfer_categories: JSON.stringify(['Transfer', 'Payment']),
  // Warn when any single position exceeds this share of the portfolio.
  concentration_warn_pct: '20',
  // How many days back the signal feeds look.
  signal_lookback_days: '90',
};

const upsertPref = db.prepare(
  'INSERT INTO prefs (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING'
);
for (const [key, value] of Object.entries(DEFAULT_PREFS)) upsertPref.run(key, value);

export function getPref(key, fallback = null) {
  const row = db.prepare('SELECT value FROM prefs WHERE key = ?').get(key);
  return row ? row.value : fallback;
}

export function getPrefNumber(key, fallback = 0) {
  const v = getPref(key);
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export function setPref(key, value) {
  db.prepare(
    'INSERT INTO prefs (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value'
  ).run(key, String(value));
}

export function allPrefs() {
  return Object.fromEntries(
    db.prepare('SELECT key, value FROM prefs').all().map((r) => [r.key, r.value])
  );
}
