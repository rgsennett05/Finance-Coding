"""Backtest engine — replays the fund's real rules day by day on past prices.

It calls the same functions the live fund uses (Market Analyst signals,
Portfolio Manager rules, Risk Manager review and trims), so what's tested is
the actual strategy, not a copy of it.

Timing, chosen to avoid peeking at the future:
  - Decisions are made after a day's close, using prices up to that close.
  - Orders fill at the NEXT trading day's opening price (plus a small slippage cost).
  - A new position's stop-loss is set 8% under its actual fill price.
  - During each day, if the low touches a stop, the position is sold at the stop
    price — or at the open, if the stock opened below the stop (a gap down).
  - A stock sold by its stop can't be re-bought for `cooldown_days`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from agents.market_analyst import compute_signals
from agents.portfolio_manager import decide_rules, proposals as pm_proposals
from agents.risk_manager import review, trim_proposals
from config.settings import Settings
from trading.portfolio import PortfolioState, Position

LOOKBACK_ROWS = 300   # enough history for a 200-day average and 12-1 month momentum


@dataclass
class Holding:
    qty: int
    entry: float          # average price paid
    stop: float


@dataclass
class Trade:
    date: str
    ticker: str
    side: str             # buy | sell
    qty: int
    price: float
    kind: str             # buy | sell (signal) | trim | stop
    pnl_pct: float | None = None   # for exits: return vs. average entry


@dataclass
class Result:
    start: str
    end: str
    starting_cash: float
    equity: pd.Series                 # fund value each day
    benchmark: pd.Series              # VOO buy-and-hold value each day
    invested: pd.Series               # share of the fund in stocks each day
    matched: pd.Series = None         # VOO held at the fund's own invested share each day (fair comparison)
    trades: list[Trade] = field(default_factory=list)


def run(bars: dict[str, pd.DataFrame], settings: Settings, start: str, end: str | None = None,
        cash: float = 100_000.0, slippage: float = 0.0005) -> Result:
    limits = settings.risk
    bench = bars[settings.benchmark]
    days = [d for d in bench.index if d >= pd.Timestamp(start) and (end is None or d <= pd.Timestamp(end))]
    if len(days) < 2:
        raise ValueError("Not enough trading days in the chosen period.")

    start_cash = cash
    holdings: dict[str, Holding] = {}
    stopped: dict[str, object] = {}
    pending: list = []               # approved RiskDecisions waiting for the next open
    trades: list[Trade] = []
    equity, invested = {}, {}

    def bar(t, d):
        df = bars.get(t)
        return df.loc[d] if df is not None and d in df.index else None

    for i, day in enumerate(days):
        # 1) Yesterday's decisions fill at today's open. Sells first, so their cash can fund buys.
        for d in sorted(pending, key=lambda x: x.side != "sell"):
            b = bar(d.ticker, day)
            if b is None:
                continue
            if d.side == "sell" and d.ticker in holdings:
                h = holdings[d.ticker]
                qty = min(d.qty, h.qty)
                px = b.open * (1 - slippage)
                cash += qty * px
                kind = "trim" if any(n.startswith("TRIM") for n in d.notes) else "sell"
                trades.append(Trade(str(day.date()), d.ticker, "sell", qty, round(px, 2), kind, px / h.entry - 1))
                h.qty -= qty
                if h.qty == 0:
                    del holdings[d.ticker]
            elif d.side == "buy":
                px = b.open * (1 + slippage)
                qty = min(d.qty, math.floor(cash / px))       # a gap up can make the order slightly too big
                if qty < 1:
                    continue
                cash -= qty * px
                h = holdings.get(d.ticker)
                if h:
                    h.entry = (h.entry * h.qty + px * qty) / (h.qty + qty)
                    h.qty += qty
                else:
                    h = holdings[d.ticker] = Holding(qty, px, 0.0)
                h.stop = round(h.entry * (1 - limits.stop_loss_pct), 2)   # stop maintenance: 8% under what we paid
                trades.append(Trade(str(day.date()), d.ticker, "buy", qty, round(px, 2), "buy"))
        pending = []

        # 2) Stop-losses during the day.
        for t in list(holdings):
            b = bar(t, day)
            h = holdings[t]
            if b is None or b.low > h.stop:
                continue
            px = min(b.open, h.stop) * (1 - slippage)
            cash += h.qty * px
            trades.append(Trade(str(day.date()), t, "sell", h.qty, round(px, 2), "stop", px / h.entry - 1))
            stopped[t] = day.date()
            del holdings[t]

        # 3) Value the fund at the close.
        def close(t):
            b = bar(t, day)
            if b is not None:
                return b.close
            prior = bars[t].loc[:day]
            return prior.close.iloc[-1] if len(prior) else 0.0

        stock_value = sum(h.qty * close(t) for t, h in holdings.items())
        total = cash + stock_value
        equity[day] = total
        invested[day] = stock_value / total if total else 0.0

        # 4) After the close: the real agents decide tomorrow's orders.
        if i == len(days) - 1:
            break
        signals = []
        for t in settings.tickers:
            df = bars.get(t)
            if df is None or day not in df.index:
                continue
            hist = df.loc[:day].tail(LOOKBACK_ROWS)
            if len(hist) >= 60:
                signals.append(compute_signals(t, hist[["close", "volume"]]))
        state = PortfolioState(
            portfolio_value=total, cash=cash,
            positions={t: Position(t, h.qty, h.qty * close(t), h.entry) for t, h in holdings.items()},
            recently_stopped=dict(stopped),
        )
        decisions = decide_rules(signals, state, settings)
        props = pm_proposals(decisions)
        selling = {p.ticker for p in props if p.side == "sell"}
        props += [p for p in trim_proposals(state, limits) if p.ticker not in selling]
        pending = [r for r in review(props, state, limits, today=day.date()) if r.approved]

    return _finish(bars, settings, days, equity, invested, trades, slippage, start_cash)


def _finish(bars, settings, days, equity, invested, trades, slippage, cash) -> Result:
    """Benchmark: put the same starting cash into VOO at the first open and hold it."""
    bench = bars[settings.benchmark]
    px0 = bench.loc[days[0]].open * (1 + slippage)
    shares = math.floor(cash / px0)
    left = cash - shares * px0
    bench_curve = pd.Series({d: left + shares * bench.loc[d].close for d in days})
    # Same amount invested as the fund each day, but in VOO, rest in cash.
    inv = pd.Series(invested)
    voo_ret = pd.Series({d: bench.loc[d].close for d in days}).pct_change().fillna(0.0)
    matched = cash * (1 + inv.shift(1).fillna(0.0) * voo_ret).cumprod()
    return Result(start=str(days[0].date()), end=str(days[-1].date()), starting_cash=cash, equity=pd.Series(equity),
                  benchmark=bench_curve, invested=inv, matched=matched, trades=trades)


# ------------------------------------------------------------------------------
# Scorecard
# ------------------------------------------------------------------------------

def stats(curve: pd.Series) -> dict:
    """Total return, yearly return (CAGR), volatility, Sharpe (risk-free rate 0), worst drop."""
    rets = curve.pct_change().dropna()
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    total = curve.iloc[-1] / curve.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 else 0.0
    vol = rets.std() * math.sqrt(252) if len(rets) > 1 else 0.0
    sharpe = (rets.mean() * 252) / vol if vol else 0.0
    drawdown = (curve / curve.cummax() - 1).min()
    return {"total_return": total, "cagr": cagr, "volatility": vol, "sharpe": sharpe, "max_drawdown": drawdown,
            "final_value": curve.iloc[-1]}


def scorecard(result: Result) -> dict:
    exits = [t for t in result.trades if t.side == "sell" and t.pnl_pct is not None]
    wins = [t for t in exits if t.pnl_pct > 0]
    by_year = {}
    for y in sorted({d.year for d in result.equity.index}):
        f = result.equity[result.equity.index.year == y]
        b = result.benchmark[result.benchmark.index.year == y]
        prev_f = result.equity[result.equity.index.year < y]
        prev_b = result.benchmark[result.benchmark.index.year < y]
        f0 = prev_f.iloc[-1] if len(prev_f) else f.iloc[0]
        b0 = prev_b.iloc[-1] if len(prev_b) else b.iloc[0]
        by_year[y] = {"fund": f.iloc[-1] / f0 - 1, "voo": b.iloc[-1] / b0 - 1}
    return {
        "fund": stats(result.equity),
        "voo": stats(result.benchmark),
        "voo_same_exposure": stats(result.matched),
        "trades": len(result.trades),
        "buys": sum(t.kind == "buy" for t in result.trades),
        "signal_sells": sum(t.kind == "sell" for t in result.trades),
        "trims": sum(t.kind == "trim" for t in result.trades),
        "stop_outs": sum(t.kind == "stop" for t in result.trades),
        "win_rate": len(wins) / len(exits) if exits else None,
        "avg_exit_return": sum(t.pnl_pct for t in exits) / len(exits) if exits else None,
        "avg_invested": float(result.invested.mean()),
        "by_year": by_year,
    }
