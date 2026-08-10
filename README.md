# Finance Coding

A personal money tracker: what's in the bank versus what's in Robinhood, how diversified the
portfolio is, where dividends get reinvested, and what the investors you follow have disclosed.

Everything runs on your machine. Credentials never leave it.

---

## Quick start

You need [Node.js](https://nodejs.org) installed. Then:

```bash
npm install
npm start
```

That's it. The first run asks three short questions — all skippable — writes your settings, and
opens the dashboard at **http://localhost:4000**.

To change an answer later: `npm run setup`, or just edit `.env` by hand.

### The three questions

| It asks for | Used for | If you skip it |
|---|---|---|
| **Your email** | The SEC requires a contact address on every request. Nothing is sent to it. | Insider and fund filings stay off |
| **Plaid keys** | Linking your bank and Robinhood. Free signup at [dashboard.plaid.com](https://dashboard.plaid.com/signup) → Developers → Keys | Account linking stays off |
| **Finnhub key** | Analyst ratings. Free at [finnhub.io/register](https://finnhub.io/register) | Ratings stay off, nothing else changes |

Every part works independently — the SEC feeds need no Plaid, and the dashboard needs no SEC.

### Trying it with fake data first

Setup starts you in Plaid's **sandbox**, where you link pretend institutions with pretend
credentials — username `user_good`, password `pass_good`, and `1234` if it asks for a code. The
whole app works end to end on fake money, so you can see it before requesting production access.

When you're ready for real accounts, change `PLAID_ENV=sandbox` to `PLAID_ENV=production` in
`.env`, swap in your production secret, then unlink and re-link from the Settings tab.

---

## Linking

Bank and brokerage link as **two separate connections**, because Plaid rejects a connection
requesting a product the institution doesn't serve — Robinhood serves `investments`, a checking
account serves `transactions`. The two buttons handle this; there's nothing to configure.

If a login expires, the Settings tab flags it and Link reopens in update mode to re-auth.

---

## What the dashboard shows

**Money** — net worth, and the bank-versus-invested split as a ratio and a trend line. Cash
runway in months, measured against a buffer target you set. Concentration via the Herfindahl
index, with a warning when any single position crosses your ceiling. Diversification by asset
class and by sector.

**Holdings** — every position with cost basis, unrealized gain/loss, and portfolio weight.

**Dividends & DRIP** — income received over twelve months, how much was automatically
reinvested, and *what it bought*. This comes from Plaid's transaction subtypes
(`dividend reinvestment`, `interest reinvestment`, `long-term capital gain reinvestment`), which
your broker reports directly — it is not inferred by matching cash flows to purchases.

**Who I follow** — disclosed activity from the investors you track.

**Settings** — buffer target, concentration ceiling, signal lookback, linked institutions.

### A note on sectors

Plaid returns an asset class for each security but **not a sector**. Asset-class diversification
is therefore exact; sector diversification is only as complete as the `sector_map` table, and the
UI shows the coverage percentage so you know how much is unclassified. Tag tickers yourself:

```sql
INSERT INTO sector_map (ticker, sector) VALUES ('NVDA', 'Technology');
```

---

## Following other investors

```bash
npm run follow -- search "berkshire"          # find a fund's CIK on EDGAR
npm run follow -- institution 1067983 "Berkshire Hathaway"
npm run follow -- insider 320193 "Apple insiders"
npm run follow -- congress "Nancy Pelosi"
npm run follow -- list

npm run signals                                # fetch and print the latest disclosures
```

### What these feeds actually are

Every one of them is a **public disclosure with a legally mandated delay**. None is a live trade
feed, and no such feed legally exists for ordinary investors. The lag is shown on every row.

| Source | What it is | Delay | Cost |
|---|---|---|---|
| **Form 4** | Officers, directors and 10% owners trading their own company's stock | ~2 business days | Free (SEC) |
| **Congress** | STOCK Act periodic transaction reports | Up to 45 days | Free (House Clerk) |
| **13F** | Institutional long US equity positions | Quarterly, +45 days | Free (SEC) |
| **Analyst ratings** | Street consensus and price targets | Live | Paid vendor |

Form 4 rows carry an `openMarket` flag. Only codes `P` (purchase) and `S` (sale) are discretionary
decisions — grants, option exercises and tax withholding are mechanical and say little about
conviction, so they're marked rather than mixed in.

13F gives you conviction, never timing: a position you read about in mid-August was held as of
June 30 and may already be gone.

**Two known gaps, stated plainly:**

- *Congressional trades are filing-level, not ticker-level.* The House Clerk publishes a
  machine-readable index of who filed and when, but the trades themselves are inside the linked
  PDF. Extracting them needs a PDF text layer (e-filed reports have one; scanned ones need OCR).
  Set `CONGRESS_TX_API` to a service returning normalized rows to fill this in.
- *The Senate is not covered.* `efdsearch.senate.gov` gates results behind a terms-acceptance
  session cookie. It's left explicitly unsupported rather than silently returning nothing.

---

## Viewing it on your phone

The app is local-only by design. To read it on your phone, publish a snapshot as a **private
Artifact** on claude.ai — visible only to your account, in the Claude app:

```bash
npm run snapshot                  # build the page from your synced data
npm run snapshot -- --redact      # same page, every dollar figure masked
npm run snapshot -- --demo        # example figures, for reviewing the layout
```

This writes `snapshots/snapshot.html`. Ask Claude to publish that file as an artifact, and
re-publish it to the same URL whenever you want it refreshed.

**The tradeoff, so it's a real choice:** the snapshot is a point-in-time copy uploaded to your
private claude.ai space — not a live connection to your accounts. Nothing refreshes on its own.
`--redact` keeps every ratio, weight and percentage exact while masking the amounts, which is a
reasonable default for a page you open in public.

---

## Layout

```
src/
  config.js           env loading, path resolution
  db.js               SQLite schema, preferences
  analytics.js        net worth, diversification, runway, positions, DRIP
  render.js           snapshot -> self-contained HTML
  demo-data.js        example figures for --demo
  plaid/
    client.js         API client, error unwrapping
    link.js           link tokens, token exchange, item management
    sync.js           balances, transactions, holdings, investment transactions
  signals/
    sec.js            throttled EDGAR client, XML helpers
    form4.js          insider trades
    thirteenf.js      institutional holdings + quarter-over-quarter diff
    congress.js       House Clerk disclosure index
    analysts.js       Finnhub adapter (degrades to empty without a key)
    index.js          follow list, refresh orchestration, signal queries
  server.js           Express API + static hosting
public/               dashboard UI
scripts/              sync, signals, follow, snapshot
test/                 offline parser and render tests
```

```bash
npm test              # runs without network access
```

---

## Security

- `.env` and `*.db` are gitignored. Plaid access tokens live in your local SQLite file.
- The server binds locally and has no authentication — don't expose it to the internet as-is.
- Unlinking an institution calls Plaid's `/item/remove` and deletes the local token.
