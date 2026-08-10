import express from 'express';
import path from 'node:path';
import { config } from './config.js';
import { db, allPrefs, setPref } from './db.js';
import { createLinkToken, createUpdateLinkToken, exchangePublicToken, listItems, removeItem } from './plaid/link.js';
import { syncAll } from './plaid/sync.js';
import { fullSnapshot, netWorth, positions, diversification, cashRunway, incomeAndReinvestment } from './analytics.js';
import {
  listFollows,
  addFollow,
  removeFollow,
  findEntity,
  refreshSignals,
  recentSignals,
  signalsOnMyHoldings,
  SUGGESTED_INSTITUTIONS,
} from './signals/index.js';

const app = express();
app.use(express.json());
app.use(express.static(path.join(config.root, 'public')));

const ok = (fn) => async (req, res, next) => {
  try {
    res.json(await fn(req, res));
  } catch (err) {
    next(err);
  }
};

// --- Linking ---------------------------------------------------------------

app.get('/api/config', ok(async () => ({
  plaidEnv: config.plaid.env,
  plaidConfigured: Boolean(config.plaid.clientId && config.plaid.secret),
  secConfigured: Boolean(config.sec.userAgent && config.sec.userAgent.includes('@')),
  analystsConfigured: Boolean(config.finnhubKey),
})));

app.post('/api/link/token', ok(async (req) => ({
  linkToken: await createLinkToken(req.body?.mode || 'bank'),
})));

app.post('/api/link/token/update', ok(async (req) => ({
  linkToken: await createUpdateLinkToken(req.body.itemId),
})));

app.post('/api/link/exchange', ok(async (req) => {
  const result = await exchangePublicToken(req.body.publicToken);
  // Pull data immediately so the dashboard is never empty after linking.
  const sync = await syncAll();
  return { ...result, sync };
}));

app.get('/api/items', ok(async () => ({ items: listItems() })));
app.delete('/api/items/:itemId', ok(async (req) => ({ removed: await removeItem(req.params.itemId) })));

// --- Sync + analytics ------------------------------------------------------

app.post('/api/sync', ok(async () => syncAll()));

app.get('/api/overview', ok(async () => fullSnapshot()));
app.get('/api/networth', ok(async () => netWorth()));
app.get('/api/positions', ok(async () => positions()));
app.get('/api/diversification', ok(async () => diversification()));
app.get('/api/runway', ok(async () => cashRunway()));
app.get('/api/income', ok(async (req) => incomeAndReinvestment({ days: Number(req.query.days) || 365 })));

// --- Preferences -----------------------------------------------------------

app.get('/api/prefs', ok(async () => allPrefs()));
app.post('/api/prefs', ok(async (req) => {
  for (const [k, v] of Object.entries(req.body || {})) setPref(k, v);
  return allPrefs();
}));

// --- Who you follow --------------------------------------------------------

app.get('/api/follows', ok(async () => ({
  follows: listFollows(),
  suggestions: SUGGESTED_INSTITUTIONS,
})));

app.post('/api/follows', ok(async (req) => {
  const { kind, identifier, label } = req.body;
  return addFollow(kind, identifier, label);
}));

app.delete('/api/follows/:kind/:identifier', ok(async (req) =>
  ({ removed: removeFollow(req.params.kind, req.params.identifier) })
));

app.get('/api/follows/search', ok(async (req) =>
  ({ results: await findEntity(req.query.name, req.query.form || '13F-HR') })
));

// --- Signals ---------------------------------------------------------------

app.post('/api/signals/refresh', ok(async (req) =>
  ({ report: await refreshSignals({ sources: req.body?.sources }) })
));

app.get('/api/signals', ok(async (req) => ({
  signals: recentSignals({
    source: req.query.source || null,
    ticker: req.query.ticker || null,
    limit: Number(req.query.limit) || 100,
  }),
})));

app.get('/api/signals/mine', ok(async () => ({ signals: signalsOnMyHoldings() })));

// --- Errors ----------------------------------------------------------------

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(err.status || 500).json({
    error: err.message || 'Something went wrong',
    plaid: err.plaid || undefined,
  });
});

app.listen(config.port, () => {
  const linked = db.prepare('SELECT COUNT(*) AS n FROM items').get().n;
  console.log(`\n  Finance Coding  →  http://localhost:${config.port}`);
  console.log(`  Plaid env: ${config.plaid.env}   Linked institutions: ${linked}\n`);
});
