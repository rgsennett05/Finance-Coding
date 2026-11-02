"""Checks the Market Analyst's math on made-up price series (no internet needed)."""
import numpy as np
import pandas as pd

from agents.market_analyst import compute_signals, explain, rsi, rule_explanation


def series(prices, volume=1_000):
    idx = pd.date_range("2025-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({"close": prices, "volume": [volume] * len(prices)}, index=idx)


def test_steady_uptrend_is_bullish():
    s = compute_signals("UP", series(np.linspace(100, 200, 300)))
    assert s.trend_score == 1.0
    assert s.momentum_12_1 > 0.3
    assert s.label == "bullish"


def test_steady_downtrend_is_bearish():
    s = compute_signals("DOWN", series(np.linspace(200, 100, 300)))
    assert s.trend_score == -1.0
    assert s.label == "bearish"


def test_rsi_extremes():
    assert rsi(pd.Series(np.arange(1, 40, dtype=float))) == 100.0
    falling = rsi(pd.Series(np.arange(40, 1, -1, dtype=float)))
    assert falling < 1


def test_short_history_does_not_crash():
    s = compute_signals("NEW", series(np.linspace(10, 12, 30)))
    assert s.sma200 is None and s.momentum_12_1 is None
    assert "enough history" in rule_explanation(s)


def test_volume_spike_is_measured():
    df = series(np.linspace(100, 110, 100))
    df.iloc[-5:, df.columns.get_loc("volume")] = 3_000
    assert round(compute_signals("VOL", df).volume_ratio, 2) == 3.0


def test_without_ai_key_explanation_is_labeled(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    s = explain([compute_signals("UP", series(np.linspace(100, 200, 300)))], "any-model")[0]
    assert s.explained_by == "rules (no AI key set)"
    assert "bullish" in s.explanation
