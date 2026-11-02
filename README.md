# 🏙️ Ticker City — a research city of agents

Each **agent is a building**. Buildings sit in **districts**, plug into a shared **utility grid** of
tools, and post their results to a **town square** (`board`) that later buildings read. Every
weekday evening the whole city runs one **shift** on GitHub's servers — your computer can be off —
and leaves behind a map: `city/state/city.html`.

```
 Market Exchange ──┬──▶ Quant Tower ──▶ Risk Office ──┐
   (prices)        │    (momentum)      (safety)      │
                   └──▶ Valuation Bank ───────────────┼──▶ City Hall ──▶ Research Library
                        (SEC facts + DCF)  (value)    │    (picks)       (Claude memo)
```

| Building | Agent file | What it does |
|---|---|---|
| Market Exchange | `city/agents/scout.js` | Daily prices for the watchlist (Yahoo → Stooq → synthetic fallback) |
| Quant Tower | `city/agents/quant.js` | SMA-50/200, RSI-14, 12-1 momentum, 3-month return → momentum score |
| Valuation Bank | `city/agents/valuation.js` | 10-K free cash flow from SEC XBRL → two-stage DCF with sensitivity grid |
| Risk Office | `city/agents/risk.js` | Annualized volatility, max drawdown, correlation to the basket → safety score |
| City Hall | `city/agents/mayor.js` | Weighted composite → ranked list and top picks |
| Research Library | `city/agents/research.js` | Claude writes a plain-English memo (only if `ANTHROPIC_API_KEY` is set) |

Scores are **percentile ranks within your watchlist**, so they say "better than the others here",
not "good in absolute terms". This is a research tool, not trading advice.

---

## Run it

```bash
npm install
cp .env.example .env   # then fill in your keys
npm run city:offline     # no network: synthetic prices, proves the plumbing works
npm run city             # real data (set SEC_USER_AGENT in .env for the DCFs)
npm run city -- --only valuation   # one building plus whatever it depends on
```

Open `city/state/city.html` in a browser. Edit the watchlist, DCF assumptions and score weights in
`city/city.config.json`.

## Run it while your computer is off

`.github/workflows/agent-city.yml` runs a shift every weekday at ~6:17pm New York time.

1. Push this branch and merge it into your default branch (schedules only run from there).
2. On GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   - `SEC_USER_AGENT` — e.g. `TickerCity you@example.com` (the SEC requires a contact)
   - `FINNHUB_API_KEY` — optional; turns on live quotes (`city/mods/finnhub-live`)
   - `ANTHROPIC_API_KEY` — optional; without it the Library just stays closed
3. **Actions → Agent City → Run workflow** to try it now.

Each run commits `city/state/` back to the repo and attaches the map as a downloadable artifact.

---

## The three building blocks

### 1. Tools — `city/tools/*.js`
Anything that fetches or computes. A tool is just:

```js
export default {
  name: 'prices',
  description: 'what it does',
  async run(input, ctx) { return { … }; },
};
```

Drop a file in `city/tools/` and it's on the grid at boot.

### 2. Agents — `city/agents/*.js`
A building. It declares which agents it waits for and which tools it may use:

```js
export default {
  id: 'quant', name: 'Momentum Quant', building: 'Quant Tower', district: 'Analytics',
  role: 'one line for the map',
  needs: ['scout'],            // runs after these; reads board.scout
  tools: ['indicators'],       // calling any other tool throws
  async run({ config, board, use }) {
    const x = await use('indicators', { closes: [...] });
    return { summary: 'shown on the map', data: { … } };   // data → board.quant
  },
};
```

If a building it needs fails, it shows **Blocked**; if it throws, it's **on fire** on the map. Nothing
else stops.

### 3. Mods — `city/mods/<name>/index.js`
How you bring in code from GitHub. See the next section.

---

## Bringing in tools and frameworks from GitHub

There are four ways to pull in someone else's code. Pick by what the project ships.

### A. It's published as a package (most common)
Most GitHub JS projects are on npm. The repo's README usually shows `npm install <name>`.

```bash
npm install technicalindicators
```

Then wrap it in a mod. **`city/mods/technical-indicators/` is a complete working example**: it imports
[technicalindicators](https://github.com/anandanand84/technicalindicators), adapts its API to a city
tool, and registers it under the name `indicators` — so every agent gets MACD and Bollinger Bands
without changing. Enable/disable it in `city.config.json → "mods"`.

You can also install straight from a GitHub repo that isn't on npm:

```bash
npm install github:owner/repo            # default branch
npm install github:owner/repo#v1.2.0     # pin a tag — do this; branches move
```

### B. It's a Python library (most quant finance lives here)
Projects like `yfinance`, `pandas-ta`, `QuantLib`, `PyPortfolioOpt` or `vectorbt` are Python. Don't
port them — run them as a subprocess tool that prints JSON:

```js
// tools/pyportfolio.js
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const run = promisify(execFile);

export default {
  name: 'optimize',
  description: 'Max-Sharpe weights via PyPortfolioOpt',
  async run({ prices }) {
    const { stdout } = await run('python3', ['city/py/optimize.py'], { input: JSON.stringify(prices) });
    return JSON.parse(stdout);
  },
};
```

In the workflow add `actions/setup-python@v5` and `pip install -r requirements.txt` before
`npm run city`.

### C. It's an MCP server
Many GitHub projects now ship an [MCP](https://modelcontextprotocol.io) server — a standard way to
hand tools to an AI. Those plug into **Claude** (Claude Code, Claude Desktop, or the API's MCP
connector) rather than into this city's registry. Use them when you want Claude itself to browse
and reason with the tool, e.g. inside the Research Library.

### D. You want the whole repo, not a package
```bash
git submodule add https://github.com/owner/repo vendor/repo
git submodule update --init      # teammates and CI run this after cloning
```
Add `submodules: true` under `actions/checkout` in the workflow. Use this sparingly — you now own
updating it.

### Before you install anything
- **Stars and recent commits** — abandoned finance libraries silently break when data APIs change.
- **License** — MIT/Apache/BSD are fine for personal use; read GPL/AGPL terms before sharing.
- **What it does on install** — `npm install` can run scripts. Prefer well-known packages and pin
  versions (`package-lock.json` already does this).
- **Where its data comes from** — a library that scrapes a website can stop working any day.

---

## Ideas for the next buildings

| Building | District | Would use |
|---|---|---|
| Insider Watch | Civic | SEC Form 4 filings — are executives buying their own stock? |
| Whale Harbor | Harbor | SEC 13F filings — which big funds added the pick last quarter |
| Comps Desk | Financial | EV/EBITDA and P/FCF vs. sector peers from the same SEC facts |
| Backtest Observatory | Analytics | replay the Mayor's rule over past years to see if it ever worked |

To add one: copy a file in `city/agents/`, change `id`/`needs`/`tools`, write `run()`. It appears on the map
on the next shift.

---

## Layout

```
city/
  city.config.json   watchlist, DCF assumptions, score weights, enabled mods
  run.js             City Hall's clock: loads tools and mods, runs agents in order
  registry.js        the tool grid and mod loader
  render.js          draws the city map (city/state/city.html)
  agents/            one file per building
  tools/             prices, indicators, fundamentals, dcf, claude
  mods/              add-ons that wrap outside libraries and services
  lib/sec.js         throttled SEC EDGAR client
test/                offline tests — npm test
.github/workflows/   the weekday evening schedule
```
