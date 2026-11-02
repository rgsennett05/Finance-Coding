# Trading City — an AI hedge fund (paper trading)

A team of AI agents that research stocks, argue about them, check risk, and place **paper** trades
(practice trades with fake money) through Alpaca. Eventually it gets a dashboard and an animated city
where each agent is a building that lights up as it works.

> **Paper trading only.** This project never places real-money trades.

**Status:** Stage 1 — building the working core. See the roadmap in [CLAUDE.md](CLAUDE.md).

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

## Running the agents

```bash
python -m agents.market_analyst   # technical signals + plain-English read for each ticker
```

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
