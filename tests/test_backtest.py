"""Checks the backtest engine on made-up prices (no internet needed)."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from backtest import engine
from config.settings import load_settings

DAYS = pd.bdate_range("2023-01-02", periods=420)
START = str(DAYS[320].date())


def frame(closes, gap_open=None):
    c = pd.Series(closes, index=DAYS, dtype=float)
    o = c.shift(1).fillna(c.iloc[0]) if gap_open is None else gap_open
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.002, "low": np.minimum(o, c) * 0.998,
                         "close": c, "volume": 1_000.0})


def settings(tickers):
    s = load_settings()
    return replace(s, tickers=tickers, benchmark="VOO")


def bars_with(**series):
    flat = frame(np.full(len(DAYS), 100.0))
    return {"VOO": flat, **series}


def test_a_steady_riser_is_bought_at_the_next_open_not_the_signal_day():
    up = frame(np.linspace(50, 150, len(DAYS)))
    r = engine.run(bars_with(UP=up), settings(["UP", "VOO"]), START)
    first = r.trades[0]
    assert first.ticker == "UP" and first.side == "buy"
    assert first.date == str(DAYS[321].date())                       # decided after day 320's close
    assert first.price == pytest.approx(up.loc[DAYS[321], "open"] * 1.0005, abs=0.01)


def test_stop_fills_at_the_stop_or_at_a_gap_down_open():
    closes = np.linspace(50, 150, len(DAYS))
    closes[340:] = closes[339] * 0.7                                  # crash on day 340
    opens = pd.Series(closes, index=DAYS).shift(1).fillna(closes[0])
    opens.iloc[340] = closes[339] * 0.7                               # opens 30% lower: gap down
    r = engine.run(bars_with(UP=frame(closes, opens)), settings(["UP", "VOO"]), START)
    stop = next(t for t in r.trades if t.kind == "stop")
    assert stop.date == str(DAYS[340].date())
    assert stop.pnl_pct < -0.2                                        # gap down: sold at the open, not the stop


def test_no_rebuy_during_cooldown_after_a_stop():
    closes = np.linspace(50, 150, len(DAYS))
    closes[340] = closes[339] * 0.85                                  # one bad day, then the uptrend resumes
    closes[341:] = np.linspace(closes[339] * 0.86, closes[339] * 1.3, len(DAYS) - 341)
    r = engine.run(bars_with(UP=frame(closes)), settings(["UP", "VOO"]), START)
    stop = next(t for t in r.trades if t.kind == "stop")
    rebuys = [t for t in r.trades if t.kind == "buy" and t.date > stop.date]
    assert rebuys and (pd.Timestamp(rebuys[0].date) - pd.Timestamp(stop.date)).days >= 7


def test_cash_never_negative_and_positions_respect_limits():
    rng = np.random.default_rng(7)
    series = {f"S{i}": frame(100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, len(DAYS))))) for i in range(12)}
    r = engine.run(bars_with(**series), settings(list(series) + ["VOO"]), START)
    assert (r.invested <= 0.9 + 1e-9).all()                           # 10% cash reserve
    assert (r.equity > 0).all()
    assert len({t.ticker for t in r.trades}) <= 12


def test_benchmark_and_same_exposure_curve():
    voo = frame(np.linspace(100, 200, len(DAYS)))
    r = engine.run({"VOO": voo}, settings(["VOO"]), START)
    assert r.benchmark.iloc[-1] > r.benchmark.iloc[0]
    assert (r.matched == r.starting_cash).all()                       # fund never invests -> matched stays flat
    card = engine.scorecard(r)
    assert card["fund"]["total_return"] == 0 and card["trades"] == 0
