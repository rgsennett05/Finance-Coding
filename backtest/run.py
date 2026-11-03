"""Backtest the fund's current rules against simply holding VOO.

    python -m backtest.run                       # default: Nov 2021 to today
    python -m backtest.run --start 2023-01-01    # a different period

Results are printed and saved to logs/backtest_latest.json (kept on your computer).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from backtest import engine
from backtest.data import history
from config.settings import load_settings

OUT = Path(__file__).resolve().parent.parent / "logs" / "backtest_latest.json"


def pct(x):
    return "—" if x is None else f"{x * 100:+.1f}%"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2021-11-01", help="first trading day of the test (YYYY-MM-DD)")
    ap.add_argument("--end", default=None, help="last day (default: latest data)")
    ap.add_argument("--cash", type=float, default=100_000.0)
    opts = ap.parse_args(argv)

    settings = load_settings()
    start = datetime.fromisoformat(opts.start)
    tickers = sorted(set(settings.tickers) | {settings.benchmark})
    print(f"Loading prices for {', '.join(tickers)} …")
    bars = history(tickers, start - timedelta(days=460))     # extra history so signals have a full year to look back on
    result = engine.run(bars, settings, opts.start, opts.end, cash=opts.cash)
    card = engine.scorecard(result)
    f, v, m = card["fund"], card["voo"], card["voo_same_exposure"]

    print(f"\nBacktest {result.start} → {result.end} · starting cash ${opts.cash:,.0f}\n")
    print(f"{'':<22}{'Trading City':>14}{'Hold VOO':>12}{'VOO, same % invested':>22}")
    for label, key in [("Final value", "final_value"), ("Total return", "total_return"), ("Per year (CAGR)", "cagr"),
                       ("Worst drop", "max_drawdown"), ("Volatility", "volatility"), ("Sharpe ratio", "sharpe")]:
        fx, vx, mx = f[key], v[key], m[key]
        fmt = (lambda x: f"${x:,.0f}") if key == "final_value" else (lambda x: f"{x:.2f}") if key == "sharpe" else pct
        print(f"{label:<22}{fmt(fx):>14}{fmt(vx):>12}{fmt(mx):>22}")
    print(f"\nTrades: {card['trades']} ({card['buys']} buys, {card['signal_sells']} signal sells, "
          f"{card['trims']} trims, {card['stop_outs']} stop-outs)")
    print(f"Winning exits: {pct(card['win_rate']).lstrip('+')} · average exit {pct(card['avg_exit_return'])} · "
          f"average invested {card['avg_invested']:.0%}")
    print("\nYear by year:")
    for y, r in card["by_year"].items():
        print(f"  {y}   fund {pct(r['fund']):>8}   VOO {pct(r['voo']):>8}")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "settings": {"tickers": settings.tickers, "benchmark": settings.benchmark, "risk": settings.risk.__dict__},
        "start": result.start, "end": result.end, "cash": opts.cash, "scorecard": card,
        "equity": {str(k.date()): round(v, 2) for k, v in result.equity.items()},
        "benchmark": {str(k.date()): round(v, 2) for k, v in result.benchmark.items()},
        "matched": {str(k.date()): round(v, 2) for k, v in result.matched.items()},
        "invested": {str(k.date()): round(v, 4) for k, v in result.invested.items()},
        "trades": [t.__dict__ for t in result.trades],
    }, indent=1, default=float))
    print(f"\nSaved to {OUT.relative_to(OUT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
