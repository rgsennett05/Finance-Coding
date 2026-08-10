import { plaid, plaidError } from './client.js';
import { db } from '../db.js';

const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);

const upsertAccount = db.prepare(
  `INSERT INTO accounts (account_id, item_id, name, official_name, mask, type, subtype,
                         current_balance, available_balance, iso_currency, updated_at)
   VALUES (@account_id, @item_id, @name, @official_name, @mask, @type, @subtype,
           @current_balance, @available_balance, @iso_currency, @updated_at)
   ON CONFLICT(account_id) DO UPDATE SET
     name = excluded.name, official_name = excluded.official_name, mask = excluded.mask,
     type = excluded.type, subtype = excluded.subtype,
     current_balance = excluded.current_balance, available_balance = excluded.available_balance,
     iso_currency = excluded.iso_currency, updated_at = excluded.updated_at`
);

const upsertSecurity = db.prepare(
  `INSERT INTO securities (security_id, ticker, name, type, close_price, close_price_as_of,
                           iso_currency, is_cash_equivalent)
   VALUES (@security_id, @ticker, @name, @type, @close_price, @close_price_as_of,
           @iso_currency, @is_cash_equivalent)
   ON CONFLICT(security_id) DO UPDATE SET
     ticker = excluded.ticker, name = excluded.name, type = excluded.type,
     close_price = excluded.close_price, close_price_as_of = excluded.close_price_as_of,
     is_cash_equivalent = excluded.is_cash_equivalent`
);

const upsertHolding = db.prepare(
  `INSERT INTO holdings (account_id, security_id, quantity, cost_basis, institution_price,
                         institution_value, iso_currency, updated_at)
   VALUES (@account_id, @security_id, @quantity, @cost_basis, @institution_price,
           @institution_value, @iso_currency, @updated_at)
   ON CONFLICT(account_id, security_id) DO UPDATE SET
     quantity = excluded.quantity, cost_basis = excluded.cost_basis,
     institution_price = excluded.institution_price,
     institution_value = excluded.institution_value, updated_at = excluded.updated_at`
);

const upsertBankTx = db.prepare(
  `INSERT INTO bank_transactions (transaction_id, account_id, date, name, merchant_name,
                                  amount, category, pending)
   VALUES (@transaction_id, @account_id, @date, @name, @merchant_name, @amount, @category, @pending)
   ON CONFLICT(transaction_id) DO UPDATE SET
     date = excluded.date, name = excluded.name, merchant_name = excluded.merchant_name,
     amount = excluded.amount, category = excluded.category, pending = excluded.pending`
);

const upsertInvTx = db.prepare(
  `INSERT INTO investment_transactions (investment_transaction_id, account_id, security_id, date,
                                        name, quantity, amount, price, fees, type, subtype)
   VALUES (@investment_transaction_id, @account_id, @security_id, @date, @name, @quantity,
           @amount, @price, @fees, @type, @subtype)
   ON CONFLICT(investment_transaction_id) DO UPDATE SET
     quantity = excluded.quantity, amount = excluded.amount, price = excluded.price,
     fees = excluded.fees, type = excluded.type, subtype = excluded.subtype`
);

function saveAccounts(itemId, accounts) {
  const now = new Date().toISOString();
  const run = db.transaction((rows) => {
    for (const a of rows) {
      upsertAccount.run({
        account_id: a.account_id,
        item_id: itemId,
        name: a.name,
        official_name: a.official_name ?? null,
        mask: a.mask ?? null,
        type: a.type,
        subtype: a.subtype ?? null,
        current_balance: a.balances?.current ?? null,
        available_balance: a.balances?.available ?? null,
        iso_currency: a.balances?.iso_currency_code ?? 'USD',
        updated_at: now,
      });
    }
  });
  run(accounts);
}

function saveSecurities(securities) {
  const run = db.transaction((rows) => {
    for (const s of rows) {
      upsertSecurity.run({
        security_id: s.security_id,
        ticker: s.ticker_symbol ?? null,
        name: s.name ?? null,
        type: s.type ?? null,
        close_price: s.close_price ?? null,
        close_price_as_of: s.close_price_as_of ?? null,
        iso_currency: s.iso_currency_code ?? 'USD',
        is_cash_equivalent: s.is_cash_equivalent ? 1 : 0,
      });
    }
  });
  run(securities);
}

async function syncBalances(api, item) {
  const res = await api.accountsBalanceGet({ access_token: item.access_token });
  saveAccounts(item.item_id, res.data.accounts);
  return res.data.accounts.length;
}

async function syncBankTransactions(api, item) {
  let cursor = item.transactions_cursor || undefined;
  let added = 0;
  let removed = 0;
  let hasMore = true;

  while (hasMore) {
    const res = await api.transactionsSync({
      access_token: item.access_token,
      cursor,
      count: 500,
    });
    const data = res.data;

    const write = db.transaction(() => {
      for (const t of [...data.added, ...data.modified]) {
        upsertBankTx.run({
          transaction_id: t.transaction_id,
          account_id: t.account_id,
          date: t.date,
          name: t.name ?? null,
          merchant_name: t.merchant_name ?? null,
          amount: t.amount,
          category:
            t.personal_finance_category?.primary ??
            (Array.isArray(t.category) ? t.category[0] : null),
          pending: t.pending ? 1 : 0,
        });
      }
      for (const r of data.removed) {
        db.prepare('DELETE FROM bank_transactions WHERE transaction_id = ?').run(r.transaction_id);
      }
    });
    write();

    added += data.added.length;
    removed += data.removed.length;
    cursor = data.next_cursor;
    hasMore = data.has_more;
  }

  db.prepare('UPDATE items SET transactions_cursor = ? WHERE item_id = ?').run(cursor, item.item_id);
  return { added, removed };
}

async function syncHoldings(api, item) {
  const res = await api.investmentsHoldingsGet({ access_token: item.access_token });
  saveAccounts(item.item_id, res.data.accounts);
  saveSecurities(res.data.securities);

  const now = new Date().toISOString();
  const accountIds = new Set(res.data.accounts.map((a) => a.account_id));

  const write = db.transaction(() => {
    // Holdings are a full snapshot, so clear this item's rows first - otherwise
    // a position you fully sold would linger forever.
    for (const id of accountIds) {
      db.prepare('DELETE FROM holdings WHERE account_id = ?').run(id);
    }
    for (const h of res.data.holdings) {
      upsertHolding.run({
        account_id: h.account_id,
        security_id: h.security_id,
        quantity: h.quantity,
        cost_basis: h.cost_basis ?? null,
        institution_price: h.institution_price ?? null,
        institution_value: h.institution_value ?? null,
        iso_currency: h.iso_currency_code ?? 'USD',
        updated_at: now,
      });
    }
  });
  write();

  return res.data.holdings.length;
}

async function syncInvestmentTransactions(api, item, lookbackDays = 730) {
  const start = daysAgo(lookbackDays);
  const end = today();
  const count = 500;
  let offset = 0;
  let total = Infinity;
  let saved = 0;

  while (offset < total) {
    const res = await api.investmentsTransactionsGet({
      access_token: item.access_token,
      start_date: start,
      end_date: end,
      options: { count, offset },
    });
    const data = res.data;
    total = data.total_investment_transactions;
    saveSecurities(data.securities);

    const write = db.transaction(() => {
      for (const t of data.investment_transactions) {
        upsertInvTx.run({
          investment_transaction_id: t.investment_transaction_id,
          account_id: t.account_id,
          security_id: t.security_id ?? null,
          date: t.date,
          name: t.name ?? null,
          quantity: t.quantity ?? null,
          amount: t.amount ?? null,
          price: t.price ?? null,
          fees: t.fees ?? null,
          type: t.type ?? null,
          subtype: t.subtype ?? null,
        });
      }
    });
    write();

    saved += data.investment_transactions.length;
    offset += count;
    if (data.investment_transactions.length === 0) break;
  }

  return saved;
}

/** Record today's bank/invested totals so the split has a trend line. */
export function recordBalanceSnapshot() {
  const row = db
    .prepare(
      `SELECT
         COALESCE(SUM(CASE WHEN type = 'depository' THEN current_balance END), 0) AS bank_total,
         COALESCE(SUM(CASE WHEN type = 'investment' THEN current_balance END), 0) AS invested_total,
         COALESCE(SUM(CASE WHEN type = 'credit'     THEN current_balance END), 0) AS credit_total
       FROM accounts`
    )
    .get();

  db.prepare(
    `INSERT INTO balance_history (as_of, bank_total, invested_total, credit_total)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(as_of) DO UPDATE SET
       bank_total = excluded.bank_total,
       invested_total = excluded.invested_total,
       credit_total = excluded.credit_total,
       recorded_at = datetime('now')`
  ).run(today(), row.bank_total, row.invested_total, row.credit_total);

  return row;
}

/**
 * Sync every linked item. Products are probed rather than assumed: an item may
 * support holdings, transactions, or both, and a product the institution does
 * not serve returns PRODUCTS_NOT_SUPPORTED rather than failing the whole run.
 */
export async function syncAll({ onProgress = () => {} } = {}) {
  const api = plaid();
  const items = db.prepare('SELECT * FROM items').all();
  const results = [];

  for (const item of items) {
    const label = item.institution_name || item.item_id;
    const result = { item: label, itemId: item.item_id, errors: [] };

    try {
      result.accounts = await syncBalances(api, item);
    } catch (err) {
      const e = plaidError(err);
      result.errors.push(`balances: ${e.message}`);
      // A dead login fails everything downstream - flag it and move on.
      if (e.plaid?.error_code === 'ITEM_LOGIN_REQUIRED') {
        result.needsReauth = true;
        results.push(result);
        onProgress(result);
        continue;
      }
    }

    for (const [key, fn] of [
      ['bankTransactions', () => syncBankTransactions(api, item)],
      ['holdings', () => syncHoldings(api, item)],
      ['investmentTransactions', () => syncInvestmentTransactions(api, item)],
    ]) {
      try {
        result[key] = await fn();
      } catch (err) {
        const e = plaidError(err);
        const code = e.plaid?.error_code;
        // Expected: banks have no holdings, brokerages have no bank feed.
        if (code === 'PRODUCTS_NOT_SUPPORTED' || code === 'NO_INVESTMENT_ACCOUNTS') {
          result[key] = 'n/a';
        } else if (code === 'PRODUCT_NOT_READY') {
          result[key] = 'not ready yet - Plaid is still pulling this, retry shortly';
        } else {
          result.errors.push(`${key}: ${e.message}`);
        }
      }
    }

    db.prepare('UPDATE items SET last_synced_at = datetime(\'now\') WHERE item_id = ?').run(
      item.item_id
    );
    results.push(result);
    onProgress(result);
  }

  const totals = recordBalanceSnapshot();
  return { items: results, totals };
}
