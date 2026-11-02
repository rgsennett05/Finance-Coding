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
| Fundamentals Analyst | Earnings, valuation, company health | Stage 3 |
| News/Sentiment Analyst | Summarizes recent news and market mood | Stage 3 |
| Bull Researcher | Strongest case FOR a trade | Stage 3 |
| Bear Researcher | Strongest case AGAINST a trade | Stage 3 |
| Risk Manager | Position sizes and limits; can veto trades | **Plain code** enforces limits; model may explain a veto |
| Portfolio Manager | Weighs everything and makes the final call | Claude Opus proposes orders |
| Auditor | Logs every decision and checks it followed the rules | Stage 3 |

**Default risk limits** (in `config/settings.toml`, enforced by the Risk Manager):
- No single position over 10% of the portfolio
- Keep at least 10% in cash
- Maximum 10 open positions
- Stop-loss on every position (8% below entry by default). Alpaca only attaches stop-losses
  to whole-share orders, so we trade whole shares.

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
├── logs/            # decision + trade logs (Auditor writes here; not uploaded to GitHub)
├── dashboard/       # Streamlit app and city view
└── tests/           # simple checks that things work (run: pytest)
```

## Roadmap
### Stage 1 — Working core ← current stage
Start small: Market Analyst, Risk Manager, Portfolio Manager only.
- [x] Project skeleton (folders, settings, tests, docs)
- [x] Connect Alpaca paper account (with the paper-only safety check) — `python -m data.broker`
- [x] Market Analyst — `python -m agents.market_analyst` (AI explanations switch on once
      `ANTHROPIC_API_KEY` is set; until then explanations are rule-based and labeled so)
- [x] Risk Manager — plain code in `agents/risk_manager.py`; dry run: `python -m agents.risk_manager`
- [x] Portfolio Manager — **rules mode (free)**, the owner's choice for now: buy bullish stocks we
      don't own, sell owned stocks that turn bearish, hold the rest; benchmark never traded.
      AI mode (Claude Opus) is a later addition and needs an `ANTHROPIC_API_KEY`.
- [ ] Place paper trades and log every decision
- [ ] One command runs the full loop on the watchlist

**Done when:** one command runs the full loop end to end without errors.

### Stage 2 — Dashboard
Streamlit app showing: portfolio value over time vs. VOO, open positions, recent trades, and each
agent's reasoning for the latest run.
**Done when:** I can open it in a browser and understand what happened today.

### Stage 3 — Grow the team + the city
Add Fundamentals, News/Sentiment, Bull vs. Bear debate, and Auditor (one at a time). Build the
animated city view: each agent is a building that lights up when active, with trades flowing between
them.
**Done when:** the city runs live alongside a real paper-trading run.

### Stage 4 — Polish and share
Clean design, onboarding, and docs so someone else could set it up with their own paper keys.
Performance report vs. simply holding VOO over at least 3 months.
**Done when:** a friend can install and run it from the README.

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
