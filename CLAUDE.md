# CLAUDE.md — AI Hedge Fund ("Trading City")

## About this project
A multi-agent AI hedge fund. Each agent has one job (research, debate, risk, decisions, audit), and
together they paper trade through Alpaca. The end goal is a polished app with a clean dashboard and
an animated "city" view where each agent is a building that lights up as it works, eventually usable
by other people.

## About me (the owner)
- I'm a finance student with no coding background. Explain what you're doing in plain English,
  briefly, before and after big changes.
- Never assume I know Git, Python, or terminal commands. If I need to do something by hand (API keys,
  logins, GitHub settings), give me exact steps.
- Keep the project clean and organized. No random files at the root, no leftover experiments.

## Hard rules
- **Paper trading only.** Never use live Alpaca keys or place real-money trades. The code must:
  1. always connect with `paper=True` (Alpaca's paper endpoint), and
  2. refuse to start if a key doesn't look like a paper key (paper keys start with `PK`).
  If live keys are ever detected, stop and warn me.
- **Risk limits are enforced by code, not by an AI.** Models may propose and explain; the Risk
  Manager's checks are plain Python that no prompt can override.
- **Never commit secrets.** API keys go in `.env`, which is listed in `.gitignore`. `.env.example`
  has blank values.
- **Finish one stage before starting the next** (see Roadmap). If I ask for something from a later
  stage, remind me where we are.
- **Commit and push after every working change** with a clear, plain-English commit message. Run
  `pytest` first. If something breaks, offer to roll back to the last working commit.
- **Credit borrowed ideas.** When code or design is adapted from another repo, note it in
  `CREDITS.md` with the link and license.
- Keep `README.md` and this file up to date as the project grows.

## Tech stack
- **Language:** Python 3.11+
- **Market data + broker:** Alpaca paper account.
  - The app talks to Alpaca through the official Python SDK (`alpaca-py`), via `data/broker.py`.
  - Price data uses Alpaca's free IEX feed (`DataFeed.IEX`); the paid SIP feed is not needed.
    IEX volume is only one exchange's share of trading, so use volume as a ratio, never an absolute.
  - The official Alpaca MCP server is optional and only for chatting with Claude about the account;
    the app never depends on it.
- **Models:** Claude Haiku or Sonnet for routine agents; Claude Opus for the Portfolio Manager.
  Model names live in `config/settings.toml`.
- **Dashboard:** Streamlit (Stage 2), animated city view built on top (Stage 3)
- **Version control:** Git + GitHub, default branch `main`

## The agents
Each agent lives in its own file in `agents/` with a short, clear instruction prompt in `prompts/`.
Agents explain their reasoning in plain language so it can be shown on the dashboard.

| Agent | Job | How |
|---|---|---|
| Market Analyst | Pulls price/volume data and technical signals | Code computes signals; model explains them |
| Fundamentals Analyst | Earnings, valuation, company health | Code scores SEC annual-report data (`agents/fundamentals_analyst.py`); feeds 40% of the Portfolio Manager's blended score |
| News/Sentiment Analyst | Summarizes recent news and market mood | Stage 3 |
| Bull Researcher | Strongest case FOR a trade | Stage 3 |
| Bear Researcher | Strongest case AGAINST a trade | Stage 3 |
| Risk Manager | Position sizes and limits; can veto trades | **Plain code** enforces limits; model may explain a veto |
| Portfolio Manager | Weighs everything and makes the final call | Rules mode: blended score = 60% market + 40% fundamentals; buy above +0.33, sell below −0.33 (all in settings.toml). Claude Opus later. |
| Auditor | Logs every decision and checks it followed the rules | Stage 3 |

**Default risk limits** (in `config/settings.toml`, enforced by the Risk Manager):
- No single position over 10% of the portfolio
- Keep at least 10% in cash
- Maximum 10 open positions
- Stop-loss on every position, 8% below the price we **actually paid**. Buys are sent with a stop
  attached; after every run `trading/stops.py` checks each position and moves, re-creates or fixes
  its stop (or sells at market if the price is already below the stop level). Alpaca only attaches
  stop-losses to whole-share orders, so we trade whole shares.
- Trim: a position that grows past 11% (10% limit + `trim_buffer_pct` 1%) is sold back to 10%.
- Cool-down: no re-buying a stock within `cooldown_days` (7) of a stop-loss selling it.
- Buys still waiting to fill count against cash and the position/count limits; a stock with a
  waiting buy never gets a second one.

## Folder structure
```
├── CLAUDE.md
├── README.md
├── CREDITS.md
├── .env.example
├── .gitignore
├── requirements.txt
├── config/          # settings.toml (watchlist, risk limits, models) + loader
├── agents/          # one file per agent
├── prompts/         # instruction text for each agent
├── data/            # market data helpers (Alpaca)
├── trading/         # order placement (paper only)
├── backtest/        # replays the real rules on past prices: python -m backtest.run
├── logs/            # decision + trade logs (Auditor writes here; not uploaded to GitHub)
├── dashboard/       # Streamlit app: app.py (navigation), overview.py, city_page.py + city.html
├── .streamlit/      # Streamlit settings (no usage tracking, minimal toolbar)
├── .github/         # daily automatic run on GitHub Actions (history saved to the fund-history branch)
└── tests/           # simple checks that things work (run: pytest)
```

## Roadmap
### Stage 1 — Working core ✅ complete (2026-11-02)
Start small: Market Analyst, Risk Manager, Portfolio Manager only.
- [x] Project skeleton (folders, settings, tests, docs)
- [x] Connect Alpaca paper account (with the paper-only safety check) — `python -m data.broker`
- [x] Market Analyst — `python -m agents.market_analyst` (AI explanations switch on once
      `ANTHROPIC_API_KEY` is set; until then explanations are rule-based and labeled so)
- [x] Risk Manager — plain code in `agents/risk_manager.py`; dry run: `python -m agents.risk_manager`
- [x] Portfolio Manager — **rules mode (free)**, the owner's choice for now: buy bullish stocks we
      don't own, sell owned stocks that turn bearish, hold the rest; benchmark never traded.
      AI mode (Claude Opus) is a later addition and needs an `ANTHROPIC_API_KEY`.
- [x] Place paper trades and log every decision — `trading/orders.py`, `trading/journal.py`
- [x] One command runs the full loop on the watchlist — `python -m trading.run`. First paper orders
      placed 2026-11-02 (XOM, KO, AAPL with stop-losses).

**Done when:** one command runs the full loop end to end without errors.

Risk rules tightened on 2026-11-03 (owner's request, no new features): stops at the real fill price,
trimming, re-buy cool-down, and waiting buys counted against cash. The daily loop is now
analyze → decide → trim → risk review → orders → stop-loss check → log.

**Backtest (2026-11-03)** — `python -m backtest.run` replays the live rules (same agent functions) on
split/dividend-adjusted IEX daily bars: decide after the close, fill at the next open (+0.05%
slippage), stops filled at the stop or a gap-down open, cool-down applied. Results save to
`logs/backtest_latest.json`. First result, Nov 2021 → Nov 2026, $100k:
fund +66% (worst drop −9%, Sharpe 1.38) vs. hold VOO +75% (worst −24%, Sharpe 0.75) vs. VOO at the
fund's own invested share +28%. Findings: only ~46% invested on average (6 tradable stocks × 10% cap);
about half the return came from NVDA (hindsight: the watchlist was picked in 2026) — without NVDA
+35% vs. +22%; trimming cut return (+125% without it) but halved the worst drop; stop-losses barely
mattered (+71% without). Known limits: hindsight watchlist, cash earns 0%, no taxes, IEX prices.

### Stage 2 — Dashboard ← current stage
Streamlit app showing: portfolio value over time vs. VOO, open positions, recent trades, and each
agent's reasoning for the latest run.
- [x] First version — `streamlit run dashboard/app.py` (data in `dashboard/data.py`, page in
      `dashboard/app.py`). Chart colors follow the dataviz palette (fund blue `#2a78d6`, VOO orange
      `#eb6834`); the chart waits for 2+ days of history rather than drawing a misleading line.
- [ ] Owner opens it and confirms they understand what happened today (needs filled positions)
- [x] Daily automatic run — `.github/workflows/daily-run.yml`, weekdays 15:07 UTC (10:07am ET winter,
      11:07am ET summer). Runs `pytest` first. Every run log is saved permanently on the
      `fund-history` branch (loaded into `logs/` before each run; `python -m trading.history`
      downloads it locally). The repo is public, so this paper-account history is public too.
- [x] Alerts (`trading/alerts.py`): a failed or rejected order, a failed stop change, or a position
      with no stop-loss ends the run with an error (red ✕ on GitHub → email) and shows as a red
      banner on the dashboard.

**Done when:** I can open it in a browser and understand what happened today.

### Stage 3 — Grow the team + the city
Add Fundamentals, News/Sentiment, Bull vs. Bear debate, and Auditor (one at a time). Build the
animated city view: each agent is a building that lights up when active, with trades flowing between
them.
- [x] 3D city, first version — started early on 2026-11-02 at the owner's request while Stage 2 waits
      for orders to fill. "City" page in the dashboard (`dashboard/city_page.py`); the scene is
      `dashboard/city.html` (Three.js 0.160 from jsDelivr) and its data comes from
      `dashboard/city_data.py`. Style chosen by the owner: clean, bright, daylight future city.
      Agents = buildings on Agent Row; stocks = towers in the Market District (height = value,
      crown = gain/loss, scaffolding = waiting order); VOO = monument; Stage 3 agents = dashed lots.
      "Replay latest run" animates the run log as pulses between buildings.
- [x] 3D city, realistic version (2026-11-03): physically based sky with the sun on the real New
      York time (no time controls — removed at the owner's request), stars, lit windows, street lights and car
      lights at night; a merged skyline of procedural towers around the fund's district (Exchange
      Park keeps the view open); instanced trees, cars and pedestrians whose numbers follow the
      fund's activity level; fading trade-trail arcs for past orders; live mode (auto-replay of a
      new run); optional sound (off by default).
- [x] Live market data (2026-11-03, owner's request: "focus on live data"): latest trade prices and
      today's change from Alpaca snapshots (`data/market_data.live_quotes`) on every tower label, a live
      price strip in the city, and a "Live prices" table on the Overview. The Overview refreshes every
      minute; the City page every minute while the market is open (10 minutes when closed) and keeps
      the viewer's camera across refreshes. The backtest is kept but not run by default.
- [x] City quality pass (2026-11-03): street flicker fixed (logarithmic depth buffer, ground layers at
      distinct heights with polygon offset, merged per layer, no overlapping road segments);
      sharper facades (frames, floor slabs, glass with roughness maps so glass reflects and frames
      don't, five materials incl. brick and dark steel), reflections from a copy of the real sky,
      podium + tower / stepped forms, parapets, water tanks, antennas, glowing street-level lobbies,
      per-building tint and ground-level shading.
- [x] Fundamentals Analyst (2026-11-03, started while Stage 2 waits on fills): reads each company's
      latest 10-K from the SEC's free XBRL data (`data/sec.py`, needs `SEC_USER_AGENT` with a contact
      email) plus the live price; scores valuation (P/E, FCF yield), growth (revenue), profitability
      (operating margin, ROE) and health (debt/equity) from −1 to +1 → strong/average/weak. Banks skip
      margin/FCF/debt; funds (VOO) are skipped; reports older than ~18 months aren't judged. Runs in
      the daily loop. Owner chose option B (2026-11-03): the Portfolio Manager blends 60% market score +
      40% fundamentals score (missing fundamentals → market score alone). The backtest passes no
      fundamentals (there's no point-in-time history), so it still tests the market-only rules.
      Known gap: XOM's current SEC filer has no 10-K figures yet.
      In the city it's the Valuation Bank (columned portico, gold dome) on Research Row, and replays
      send a gold "fundamentals" pulse to Headquarters.
**Done when:** the city runs live alongside a real paper-trading run.

### Stage 4 — Polish and share
Clean design, onboarding, and docs so someone else could set it up with their own paper keys.
Performance report vs. simply holding VOO over at least 3 months.
**Done when:** a friend can install and run it from the README.

### Stage 5 — The research firm (owner's long-term vision, recorded 2026-11-03)
Starts only after Stages 3 and 4 are done.
- **One goal for every agent:** maximize the owner's (shareholder's) wealth, measured as risk-adjusted
  return vs. holding VOO. The Risk Manager's hard limits still apply; no agent can trade around them.
- **A department for every criterion**, each with one exact, strict job (e.g. technicals, fundamentals,
  valuation, macro, sector/industry, sentiment, insider & institutional flows, risk). Each department
  does deep research daily on its criterion.
- **Learn from the market's experts:** study what hedge funds and other experts are doing (SEC 13F
  holdings, insider filings, analyst views, market data such as yfinance) and adjust accordingly.
- **News Center:** a building that scans world events every day and briefs all departments.
- **Daily meeting:** departments report, debate, and agree on how today's research serves the primary
  goal; the minutes are shown in the city and on the dashboard.
- **Presentations and charts:** clicking a department in the city opens its high-level briefing
  (slides) and its charts.
- **Portfolio Manager on the most capable Claude model** (above Opus; currently Claude Fable 5.1).
  Requires an `ANTHROPIC_API_KEY` with paid credit.
- **"Perfect" made measurable:** every agent has tests, a scorecard of its past calls vs. what actually
  happened, and is judged by its contribution to returns vs. VOO. Agents that don't add value are
  changed or removed.

Notes to revisit before building: 13F data is quarterly and ~45 days late (it shows conviction, not
timing); yfinance is an unofficial Yahoo scraper that can break, so it needs a fallback; daily deep
research across many agents costs real money (rough guess $2–10/day, to be measured), so budgets and
caching come first.

## Inspiration (study, borrow pieces, credit them)
- https://github.com/virattt/ai-hedge-fund — investor-persona agents, risk + portfolio manager
- https://github.com/tauricresearch/tradingagents — firm-style structure, bull/bear debate
- https://github.com/The-Swarm-Corporation/AutoHedge — simple analysis → risk → execution flow
- https://github.com/DanisHack/ai-hedge-fund — smaller, readable example with paper trading
- Our own earlier JavaScript prototype, Ticker City (branch `archive/ticker-city-v1`): city map,
  SEC-based DCF valuation, momentum and risk scores — candidates for Stage 3.

When borrowing, explain what the piece does and why it fits, then adapt it to this project's
structure rather than copying whole repos. Check each repo's license before borrowing.

## How to start each session
1. Read this file.
2. Tell me which stage we're on and what's left in it.
3. Suggest the next small step.
