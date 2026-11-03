"""Checks the Portfolio Manager's blend of market and fundamentals scores."""
from dataclasses import replace

import pytest

from agents.market_analyst import MarketSignals
from agents.portfolio_manager import blend, decide
from config.settings import load_settings
from trading.portfolio import PortfolioState, Position

S = load_settings()   # 60% market, 40% fundamentals, buy above +0.33, sell below -0.33


def sig(t, score):
    label = "bullish" if score > 0.33 else "bearish" if score < -0.33 else "neutral"
    return MarketSignals(t, 100.0, None, None, None, None, None, None, None, None, 0, 0, 0, score, label)


def fund(t, score, available=True):
    return {"ticker": t, "available": available, "score": score}


def acts(decisions):
    return {d.ticker: d.action for d in decisions}


def test_blend_math_and_explanation():
    score, why = blend(sig("A", 0.8), fund("A", 0.0), S)
    assert score == pytest.approx(0.48)
    assert "market +0.80 × 60%" in why and "fundamentals +0.00 × 40%" in why


def test_weak_fundamentals_can_stop_a_bullish_trend():
    # Market +0.50 is a buy on its own; with fundamentals -0.60 the blend is +0.06 -> stay out.
    d = decide([sig("A", 0.5)], PortfolioState(100_000, 100_000), S, [fund("A", -0.6)])
    assert acts(d) == {"A": "hold"}


def test_strong_fundamentals_can_lift_a_neutral_trend_into_a_buy():
    # Market +0.20 alone is neutral; with fundamentals +0.90 the blend is +0.48 -> buy.
    d = decide([sig("A", 0.2)], PortfolioState(100_000, 100_000), S, [fund("A", 0.9)])
    assert acts(d) == {"A": "buy"} and "blended score +0.48" in d[0].reason


def test_missing_fundamentals_fall_back_to_the_market_score():
    d = decide([sig("A", 0.5), sig("B", 0.5)], PortfolioState(100_000, 100_000), S, [fund("B", None, available=False)])
    assert acts(d) == {"A": "buy", "B": "buy"} and "no fundamentals available" in d[0].reason


def test_owned_stock_is_sold_when_the_blend_turns_negative():
    owned = PortfolioState(100_000, 90_000, {"A": Position("A", 10, 1_000, 100.0)})
    d = decide([sig("A", -0.2)], owned, S, [fund("A", -0.8)])        # blend -0.44
    assert acts(d) == {"A": "sell"}


def test_buys_are_ranked_by_blended_score():
    d = decide([sig("A", 0.9), sig("B", 0.5)], PortfolioState(100_000, 100_000), S, [fund("A", -0.5), fund("B", 0.9)])
    # B blends to +0.66, A to +0.34 (just above +0.33): both buy, highest first.
    assert [x.ticker for x in d if x.action == "buy"] == ["B", "A"]


def test_without_fundamentals_behaviour_is_unchanged():
    # The backtest passes no fundamentals: decisions must match the old market-only rules.
    d = decide([sig("A", 0.34), sig("B", 0.33)], PortfolioState(100_000, 100_000), S)
    assert acts(d) == {"A": "buy", "B": "hold"}


def test_bad_settings_are_rejected(tmp_path):
    text = (load_settings.__globals__["SETTINGS_PATH"]).read_text()
    bad = tmp_path / "s.toml"
    bad.write_text(text.replace("sell_below = -0.33", "sell_below = 0.5"))
    with pytest.raises(ValueError, match="sell_below"):
        load_settings(bad)
