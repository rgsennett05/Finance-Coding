"""Checks the Portfolio Manager's rules with made-up signals (no internet needed)."""
from dataclasses import replace

import pytest

from agents.market_analyst import MarketSignals
from agents.portfolio_manager import decide, proposals
from config.settings import load_settings
from trading.portfolio import PortfolioState, Position

SETTINGS = load_settings()


def sig(ticker, label, score, price=100.0):
    return MarketSignals(
        ticker=ticker, price=price, sma50=None, sma200=None, return_1m=None, return_3m=None,
        momentum_12_1=None, rsi14=None, volatility=None, volume_ratio=None,
        trend_score=0, momentum_score=0, rsi_score=0, score=score, label=label,
    )


def actions(decisions):
    return {d.ticker: d.action for d in decisions}


def test_buys_bullish_we_dont_own_strongest_first():
    sigs = [sig("B", "bullish", 0.5), sig("A", "bullish", 0.9), sig("C", "neutral", 0.1)]
    ds = decide(sigs, PortfolioState(100_000, 100_000), SETTINGS)
    assert actions(ds) == {"A": "buy", "B": "buy", "C": "hold"}
    assert [p.ticker for p in proposals(ds)] == ["A", "B"]


def test_sells_owned_bearish_and_holds_owned_others():
    held = {"X": Position("X", 10, 1_000), "Y": Position("Y", 5, 500)}
    ds = decide([sig("X", "bearish", -0.6), sig("Y", "bullish", 0.7)], PortfolioState(100_000, 98_500, held), SETTINGS)
    assert actions(ds) == {"X": "sell", "Y": "hold"}


def test_benchmark_is_never_traded():
    ds = decide([sig(SETTINGS.benchmark, "bullish", 0.9)], PortfolioState(100_000, 100_000), SETTINGS)
    assert actions(ds) == {SETTINGS.benchmark: "hold"}
    assert proposals(ds) == []


def test_unwatched_holding_is_flagged_not_sold():
    held = {"OLD": Position("OLD", 3, 300)}
    ds = decide([], PortfolioState(100_000, 99_700, held), SETTINGS)
    assert actions(ds) == {"OLD": "hold"} and "by hand" in ds[0].reason


def test_every_decision_has_a_reason():
    ds = decide([sig("A", "bullish", 0.9), sig("B", "bearish", -0.9)], PortfolioState(100_000, 100_000), SETTINGS)
    assert all(d.reason for d in ds)


def test_ai_mode_is_not_silently_ignored():
    with pytest.raises(NotImplementedError):
        decide([], PortfolioState(1, 1), replace(SETTINGS, portfolio_manager_mode="ai"))
