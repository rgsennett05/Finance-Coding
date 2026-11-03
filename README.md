# Trading City — an AI hedge fund (paper trading)

A team of AI agents that research stocks, argue about them, check risk, and place **paper** trades
(practice trades with fake money) through Alpaca. Eventually it gets a dashboard and an animated city
where each agent is a building that lights up as it works.

> **Paper trading only.** This project never places real-money trades.

**Status:** Stage 1 complete — the fund paper trades from one command. Next: Stage 2, the dashboard. See the roadmap in [CLAUDE.md](CLAUDE.md).

---

## Setup

You need [Python 3.11 or newer](https://www.python.org/downloads/).

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then open .env and paste in your keys
pytest                           # checks everything is wired up
python -m data.broker            # confirms your Alpaca paper account connects
```

### Keys you need
| Key | What for | Where to get it |
|---|---|---|
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Market data and paper trades | [alpaca.markets](https://alpaca.markets) → switch to **Paper Trading** → API Keys. Paper keys start with `PK`. |
| `ANTHROPIC_API_KEY` | The AI agents | [console.anthropic.com](https://console.anthropic.com) → API Keys |

## Running the fund

```bash
python -m trading.run --dry-run   # full loop, preview only — no orders
python -m trading.run             # full loop, places PAPER orders (asks you to confirm)
```

Each run writes a log to `logs/` (kept on your computer, not uploaded).

Each agent can also be run on its own:

```bash
python -m agents.market_analyst   # technical signals + plain-English read for each ticker
python -m agents.risk_manager     # dry run: what the risk limits would allow (no orders placed)
python -m agents.portfolio_manager  # dry run: buy/sell/hold decisions + risk review (no orders placed)
```

## Daily automatic run

GitHub runs the fund every weekday at 10:07am New York time (11:07am in summer) — your computer can
be off. One-time setup: in the repo, **Settings → Secrets and variables → Actions → New repository
secret**, add `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` (your paper keys). Each run's log is attached
to the run in the **Actions** tab as `fund-logs`.

## The dashboard

```bash
streamlit run dashboard/app.py
```

Then open the address it prints (usually http://localhost:8501). Two pages:

- **Overview** — portfolio value vs. VOO, open positions, recent orders, and what each agent decided
  in the latest run.
- **City** — a 3D city: each agent is a building, each stock a tower, surrounded by a living city
  whose sky follows New York time and whose streets get busier when the fund is. Press **▶ Replay
  latest run** to watch signals, decisions and orders travel between buildings; past orders show as
  fading light trails. Drag to rotate, scroll to zoom, click a building for its reasoning. Needs an
  internet connection (it loads Three.js and two Google fonts).

Press **Refresh** to reload from Alpaca.

## Settings
Watchlist, risk limits and which Claude model each agent uses are in
[`config/settings.toml`](config/settings.toml).

## Layout
```
config/      settings (watchlist, risk limits, models)
agents/      one file per agent
prompts/     instruction text for each agent
data/        market data helpers (Alpaca)
trading/     order placement (paper only)
logs/        decision and trade logs (stay on your computer)
dashboard/   Streamlit app and city view (Stage 2+)
tests/       checks — run with: pytest
```

See [CREDITS.md](CREDITS.md) for projects this borrows from.
