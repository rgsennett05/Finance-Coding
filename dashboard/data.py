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

    return {
        "account": account_overview(client),
        "positions": positions_table(client, open_orders),
        "orders": orders_table(recent),
        "open_orders": len(open_orders),
        "performance": performance_vs_benchmark(fund, bench),
        "clock": client.get_clock(),
        "benchmark": settings.benchmark,
    }
