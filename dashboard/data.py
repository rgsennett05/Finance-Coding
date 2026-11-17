"""Everything the dashboard shows, gathered in one place.

Reads the Alpaca paper account (live) and the run logs in logs/ (what each
agent decided and why). The page itself (dashboard/app.py) only draws.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


# --------------------------------------------------------------------------
# Run logs
# --------------------------------------------------------------------------

def run_logs(log_dir: Path = LOG_DIR) -> list[dict]:
    """All run logs, newest first. Unreadable files are skipped."""
    runs = []
    for path in sorted(log_dir.glob("run_*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
            data["_file"] = path.name
            runs.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return runs


def latest_run(log_dir: Path = LOG_DIR, include_dry_runs: bool = True) -> dict | None:
    for run in run_logs(log_dir):
        if include_dry_runs or run.get("mode") == "paper":
            return run
    return None


# --------------------------------------------------------------------------
# Performance vs. benchmark (pure math, tested)
# --------------------------------------------------------------------------

def performance_vs_benchmark(fund: pd.Series, benchmark: pd.Series) -> pd.DataFrame:
    """Both series as % change since the fund's first day with money in it.

    `fund` and `benchmark` are indexed by date. Days the fund had no money
    (before the account was funded) are dropped. Returns long-format rows:
    date, series, pct.
    """
    fund = fund[fund > 0].sort_index()
    if fund.empty:
        return pd.DataFrame(columns=["date", "series", "pct"])
    start = fund.index[0]
    benchmark = benchmark.sort_index()
    before = benchmark[benchmark.index <= start]
    bench = benchmark[benchmark.index >= start]
    # Base VOO on its last close on or before the fund's first day, so both lines share a start.
    base = before.iloc[-1] if not before.empty else (bench.iloc[0] if not bench.empty else None)
    if not before.empty:
        bench = pd.concat([pd.Series([base], index=[start]), bench[bench.index > start]])
    out = [pd.DataFrame({"date": fund.index, "series": "Trading City", "pct": fund / fund.iloc[0] - 1})]
    if base:
        out.append(pd.DataFrame({"date": bench.index, "series": "VOO", "pct": bench / base - 1}))
    return pd.concat(out, ignore_index=True)


# --------------------------------------------------------------------------
# Live account (Alpaca paper)
# --------------------------------------------------------------------------

def account_overview(client) -> dict:
    a = client.get_account()
    equity, last = float(a.equity), float(a.last_equity or 0)
    return {
        "portfolio_value": equity,
        "cash": float(a.cash),
        "today_change": equity - last if last else 0.0,
        "today_pct": (equity / last - 1) if last else 0.0,
    }


def _stops_by_ticker(orders) -> dict[str, float]:
    """Stop-loss price for each stock, from open stop orders or held OTO legs."""
    stops: dict[str, float] = {}
    for o in orders:
        for leg in [o, *(o.legs or [])]:
            if getattr(leg, "stop_price", None) and str(leg.side.value) == "sell":
                stops[leg.symbol] = float(leg.stop_price)
    return stops


def positions_table(client, open_orders) -> pd.DataFrame:
    stops = _stops_by_ticker(open_orders)
    acct_value = float(client.get_account().equity) or 1.0
    rows = []
    for p in client.get_all_positions():
        rows.append({
            "Stock": p.symbol,
            "Shares": int(float(p.qty)),
            "Avg cost": float(p.avg_entry_price),
            "Price": float(p.current_price),
            "Value": float(p.market_value),
            "Gain/loss $": float(p.unrealized_pl),
            "Gain/loss %": float(p.unrealized_plpc),
            "Weight": float(p.market_value) / acct_value,
            "Stop-loss": stops.get(p.symbol, float("nan")),
        })
    return pd.DataFrame(rows)


def orders_table(orders) -> pd.DataFrame:
    rows = []
    for o in orders:
        stop = next((float(l.stop_price) for l in (o.legs or []) if getattr(l, "stop_price", None)), None)
        rows.append({
            "Submitted": o.submitted_at,
            "Stock": o.symbol,
            "Side": o.side.value.upper(),
            "Shares": int(float(o.qty or 0)),
            "Status": o.status.value.replace("_", " "),
            "Fill price": float(o.filled_avg_price) if o.filled_avg_price else float("nan"),
            "Stop-loss": stop if stop else (float(o.stop_price) if o.stop_price else float("nan")),
        })
    return pd.DataFrame(rows)


def _fills(orders) -> list[dict]:
    """Every filled buy/sell (including stop-loss legs), oldest first."""
    out = []
    for o in orders:
        for leg in [o, *(getattr(o, "legs", None) or [])]:
            if str(leg.status.value) != "filled" or not leg.filled_at or not leg.filled_avg_price:
                continue
            kind = str(leg.type.value)
            out.append({
                "ticker": leg.symbol, "side": str(leg.side.value), "time": leg.filled_at,
                "qty": int(float(leg.filled_qty or leg.qty)), "price": float(leg.filled_avg_price),
                "how": "stop-loss" if "stop" in kind else ("sell" if str(leg.side.value) == "sell" else "buy"),
            })
    return sorted(out, key=lambda f: f["time"])


def closed_trades(orders) -> pd.DataFrame:
    """Every sale with its profit or loss, measured against the average price we paid."""
    held: dict[str, list[float]] = {}          # ticker -> [shares, avg cost, first buy time]
    rows = []
    for f in _fills(orders):
        t = f["ticker"]
        qty, cost, since = held.get(t, [0, 0.0, None])
        if f["side"] == "buy":
            held[t] = [qty + f["qty"], (qty * cost + f["qty"] * f["price"]) / (qty + f["qty"]), since or f["time"]]
            continue
        sold = min(f["qty"], qty) if qty else f["qty"]
        rows.append({
            "Stock": t, "Shares": sold, "Bought": since, "Paid": cost, "Sold": f["time"], "Sold at": f["price"],
            "Profit/loss $": (f["price"] - cost) * sold,
            "Profit/loss %": (f["price"] / cost - 1) if cost else float("nan"),
            "Why sold": {"stop-loss": "Stop-loss (fell 8% below what we paid)", "sell": "Fund decided to sell / trim"}[f["how"]],
        })
        held[t] = [qty - sold, cost, since if qty - sold > 0 else None]
    return pd.DataFrame(rows, columns=["Stock", "Shares", "Bought", "Paid", "Sold", "Sold at",
                                       "Profit/loss $", "Profit/loss %", "Why sold"])


def profit_breakdown(start_value: float, value_now: float, closed: pd.DataFrame, positions: pd.DataFrame,
                     bench_change: float | None) -> dict:
    """The numbers behind 'did we make money?', split into finished trades and stocks still held."""
    realized = float(closed["Profit/loss $"].sum()) if not closed.empty else 0.0
    unrealized = float(positions["Gain/loss $"].sum()) if not positions.empty else 0.0
    total = value_now - start_value
    return {
        "start": start_value, "now": value_now, "total": total, "total_pct": total / start_value if start_value else 0.0,
        "realized": realized, "unrealized": unrealized,
        "other": total - realized - unrealized,       # e.g. dividends or fees; normally ~0
        "bench_pct": bench_change,
        "bench_total": None if bench_change is None else start_value * bench_change,
    }


def load_live(days: int = 90) -> dict:
    """One call that gathers everything live from Alpaca."""
    from datetime import timedelta

    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest, GetPortfolioHistoryRequest

    from config.settings import load_settings
    from data.broker import data_client, trading_client

    client = trading_client()
    settings = load_settings()
    open_orders = list(client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True)))
    recent = list(client.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, limit=50, nested=True)))
    every = list(client.get_orders(GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=500, nested=True,
                                                    after=datetime.now(timezone.utc) - timedelta(days=730))))

    hist = client.get_portfolio_history(GetPortfolioHistoryRequest(period="3M", timeframe="1D"))
    fund = pd.Series(
        [float(e or 0) for e in hist.equity],
        index=[datetime.fromtimestamp(t, tz=timezone.utc).date() for t in hist.timestamp],
    )
    bars = data_client().get_stock_bars(StockBarsRequest(
        symbol_or_symbols=settings.benchmark, timeframe=TimeFrame.Day,
        start=datetime.now(timezone.utc) - timedelta(days=days), feed=DataFeed.IEX,
    )).df
    bench = pd.Series(dtype=float)
    if not bars.empty:
        b = bars.xs(settings.benchmark, level=0)["close"]
        bench = pd.Series(b.values, index=[ts.date() for ts in b.index])

    from data.market_data import live_quotes

    try:
        quotes = live_quotes(sorted(set(settings.tickers) | {settings.benchmark}))
    except Exception:
        quotes = {}

    perf = performance_vs_benchmark(fund, bench)
    positions = positions_table(client, open_orders)
    account = account_overview(client)
    closed = closed_trades(every)
    started = fund[fund > 0]
    bench_rows = perf[perf.series == settings.benchmark]
    profit = profit_breakdown(
        float(started.iloc[0]) if not started.empty else account["portfolio_value"], account["portfolio_value"],
        closed, positions, float(bench_rows["pct"].iloc[-1]) if len(bench_rows) >= 2 else None)

    return {
        "profit": profit,
        "closed_trades": closed,
        "quotes": quotes,
        "account": account,
        "positions": positions,
        "orders": orders_table(recent),
        "open_orders": len(open_orders),
        "performance": perf,
        "clock": client.get_clock(),
        "benchmark": settings.benchmark,
    }
