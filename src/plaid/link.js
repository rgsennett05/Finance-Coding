import { plaid, plaidError } from './client.js';
import { db } from '../db.js';

/**
 * Products differ by institution and Plaid rejects an Item whose institution
 * does not support every requested product. Robinhood serves `investments`;
 * a checking account serves `transactions`. So we link them as separate Items.
 */
const PRODUCTS_BY_MODE = {
  bank: ['transactions'],
  brokerage: ['investments'],
};

export async function createLinkToken(mode = 'bank') {
  const products = PRODUCTS_BY_MODE[mode];
  if (!products) {
    throw new Error(`Unknown link mode "${mode}". Use "bank" or "brokerage".`);
  }

  try {
    const res = await plaid().linkTokenCreate({
      user: { client_user_id: 'local-user' },
      client_name: 'Finance Coding',
      products,
      country_codes: ['US'],
      language: 'en',
    });
    return res.data.link_token;
  } catch (err) {
    throw plaidError(err);
  }
}

/**
 * Re-auth for an Item whose login expired (ITEM_LOGIN_REQUIRED). Plaid returns
 * a token that opens Link straight into update mode for that Item.
 */
export async function createUpdateLinkToken(itemId) {
  const item = db.prepare('SELECT access_token FROM items WHERE item_id = ?').get(itemId);
  if (!item) throw new Error(`No linked item with id ${itemId}`);

  try {
    const res = await plaid().linkTokenCreate({
      user: { client_user_id: 'local-user' },
      client_name: 'Finance Coding',
      country_codes: ['US'],
      language: 'en',
      access_token: item.access_token,
    });
    return res.data.link_token;
  } catch (err) {
    throw plaidError(err);
  }
}

/** Trade the one-time public token from Link for a durable access token. */
export async function exchangePublicToken(publicToken) {
  const api = plaid();
  let itemId;
  let accessToken;

  try {
    const res = await api.itemPublicTokenExchange({ public_token: publicToken });
    accessToken = res.data.access_token;
    itemId = res.data.item_id;
  } catch (err) {
    throw plaidError(err);
  }

  // Name the item after its institution so the UI reads "Robinhood", not a UUID.
  let institutionId = null;
  let institutionName = null;
  try {
    const itemRes = await api.itemGet({ access_token: accessToken });
    institutionId = itemRes.data.item.institution_id;
    if (institutionId) {
      const inst = await api.institutionsGetById({
        institution_id: institutionId,
        country_codes: ['US'],
      });
      institutionName = inst.data.institution.name;
    }
  } catch {
    // Cosmetic only - a missing name must not fail the link.
  }

  db.prepare(
    `INSERT INTO items (item_id, access_token, institution_id, institution_name)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(item_id) DO UPDATE SET
       access_token     = excluded.access_token,
       institution_id   = excluded.institution_id,
       institution_name = excluded.institution_name`
  ).run(itemId, accessToken, institutionId, institutionName);

  return { itemId, institutionName: institutionName || 'Linked institution' };
}

export function listItems() {
  return db
    .prepare(
      `SELECT i.item_id, i.institution_name, i.last_synced_at, i.created_at,
              COUNT(a.account_id) AS account_count
         FROM items i
         LEFT JOIN accounts a ON a.item_id = i.item_id
        GROUP BY i.item_id
        ORDER BY i.created_at`
    )
    .all();
}

export async function removeItem(itemId) {
  const item = db.prepare('SELECT access_token FROM items WHERE item_id = ?').get(itemId);
  if (!item) return false;
  try {
    await plaid().itemRemove({ access_token: item.access_token });
  } catch {
    // Even if Plaid rejects it, drop our local copy so the token is gone.
  }
  db.prepare('DELETE FROM items WHERE item_id = ?').run(itemId);
  return true;
}
