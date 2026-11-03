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
| `SEC_USER_AGENT` | Company financials for the Fundamentals Analyst. The SEC requires a name and contact email, e.g. `TradingCity Jane Doe jane@example.com` | You choose it |
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
python -m agents.fundamentals_analyst  # valuation, growth, profitability and debt from SEC filings
# The Portfolio Manager blends both analysts: 60% market + 40% fundamentals (config/settings.toml)
python -m agents.risk_manager     # dry run: what the risk limits would allow (no orders placed)
python -m agents.portfolio_manager  # dry run: buy/sell/hold decisions + risk review (no orders placed)
```

## Daily automatic run

GitHub runs the fund every weekday at 10:07am New York time (11:07am in summer) — your computer can
be off. One-time setup: in the repo, **Settings → Secrets and variables → Actions → New repository
secret**, add `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` (your paper keys).

Every run's log is saved permanently on the `fund-history` branch. To copy that history to your
computer so the dashboard shows every day:

```bash
python -m trading.history
```

If an order is rejected, a step fails, or a stock is left without a stop-loss, the run ends with a
red ✕ in the **Actions** tab (GitHub emails you) and the dashboard shows a red alert banner.

## The dashboard

```bash
streamlit run dashboard/app.py
```

Then open the address it prints (usually http://localhost:8501). Two pages:

- **Overview** — live prices for the watchlist, portfolio value vs. VOO, open positions, recent
  orders, and what each agent decided in the latest run. Refreshes itself every minute.
- **City** — downtown Tampa in 3D, built from OpenStreetMap: the fund's agents work in real towers
  (the Portfolio Manager in Bank of America Plaza, the Market Analyst in 100 North Tampa, the Risk
  Manager in Rivergate Tower, the Fundamentals Analyst in Truist Place) and each stock is a glowing
  pillar on the Riverwalk labeled with its live price. The sky follows the real time in New York and
  the streets get busier when the fund is. Add `#lite` to the address on a slow device. Refreshes every minute while the market is open. Press **▶ Replay
  latest run** to watch signals, decisions and orders travel between buildings; past orders show as
  fading light trails. Drag to rotate, scroll to zoom, click a building for its reasoning. Needs an
  internet connection (it loads Three.js and two Google fonts).

Press **Refresh** to reload from Alpaca.

## Risk rules

Enforced by plain code (`agents/risk_manager.py`, `trading/stops.py`), never by an AI:

- At most 10% of the portfolio in one stock; positions that grow past 11% are trimmed back to 10%
- At least 10% cash; buys still waiting to fill count as already spent
- At most 10 positions
- Every position has a stop-loss 8% below the price actually paid, checked after every run
- No re-buying a stock for 7 days after its stop-loss sells it
- Whole shares only, no short selling, no borrowed money

## Backtest

```bash
python -m backtest.run                      # replay the current rules from Nov 2021 to today
python -m backtest.run --start 2023-01-01   # a different period
```

It uses the same agent code as the live fund, decides after each day's close and fills at the next
day's open, so it never peeks at the future. It compares the fund with holding VOO, and with VOO held
at the same share invested as the fund (the fair comparison when the fund holds a lot of cash).
Results are saved to `logs/backtest_latest.json`.

Read the results with care: the watchlist was picked today, so stocks that later did well (like NVDA)
make the past look better than it would have felt at the time.

## Settings
Watchlist, risk limits and which Claude model each agent uses are in
[`config/settings.toml`](config/settings.toml).

## Glossary

The same definitions appear as ⓘ tooltips on the dashboard.

| Term | Meaning |
|---|---|
| **12-1 momentum** | The return over the past 12 months, leaving out the most recent month — a standard way to measure a lasting trend. |
| **Avg cost** | The average price paid per share. |
| **Benchmark** | VOO, a fund that tracks the S&P 500. If we can't beat simply holding VOO, the strategy isn't adding value. |
| **Cash** | Money not invested. The fund always keeps at least 10% of the portfolio in cash. |
| **Cool-down** | After a stop-loss sells a stock, the fund waits 7 days before it may buy it again. |
| **Drawdown** | The drop from a previous peak to a low. 'Worst drawdown' is the biggest such fall. |
| **Gain/loss $** | Profit or loss in dollars since buying, not yet locked in by selling (unrealized). |
| **Gain/loss %** | Profit or loss as a percentage of what we paid. |
| **Paper trading** | Practice trading with fake money on a real market. Nothing here uses real money. |
| **Portfolio value** | Everything the account is worth right now: cash plus all stocks at today's prices. |
| **RSI** | Relative Strength Index, 0–100. Above 70 means heavily bought lately (overbought); below 30 means heavily sold (oversold). |
| **Score** | The Market Analyst's combined rating from −1 (very bearish) to +1 (very bullish). |
| **Sharpe ratio** | Return per unit of risk (volatility). Higher is better; around 1 is good. |
| **Signal** | The Market Analyst's verdict: bullish (trend and momentum look strong), bearish (weak) or neutral. |
| **Stop-loss** | An automatic sell order 8% below what we paid, so a single stock can't lose much more than 8%. |
| **Trim** | Selling part of a position that grew too big, to bring it back to the 10% limit. |
| **Volatility** | How much the price typically swings in a year. Higher means riskier. |
| **Weight** | This stock's share of the whole portfolio. The limit is 10%; above 11% the fund trims it back. |

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
