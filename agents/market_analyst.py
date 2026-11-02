"""Market Analyst — technical signals for each ticker, explained in plain English.

Code calculates every number. A Claude model (the "routine" model in
config/settings.toml) only writes the explanation. Without an
ANTHROPIC_API_KEY, a rule-based explanation is used instead and labeled so.

Run it on the watchlist:
    python -m agents.market_analyst
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from config.settings import load_settings

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "market_analyst.md"
TRADING_DAYS = 252


@dataclass
class MarketSignals:
    ticker: str
    price: float
    sma50: float | None
    sma200: float | None
    return_1m: float | None
    return_3m: float | None
    momentum_12_1: float | None   # last 12 months excluding the most recent month
    rsi14: float | None
    volatility: float | None      # annualized
    volume_ratio: float | None    # last 5 days vs. previous 50 days
    trend_score: float
    momentum_score: float
    rsi_score: float
    score: float                  # -1 (very bearish) .. +1 (very bullish)
    label: str                    # bullish | neutral | bearish
    explanation: str = ""
    explained_by: str = ""


# --------------------------------------------------------------------------
# Signal math (plain code — no AI)
# --------------------------------------------------------------------------

def _ret(closes: pd.Series, n: int) -> float | None:
    return float(closes.iloc[-1] / closes.iloc[-1 - n] - 1) if len(closes) > n else None


def rsi(closes: pd.Series, n: int = 14) -> float | None:
    """Wilder's RSI: 0-100. Above 70 = heavily bought recently, below 30 = heavily sold."""
    if len(closes) <= n:
        return None
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    if loss == 0:
        return 100.0
    return float(100 - 100 / (1 + gain / loss))


def compute_signals(ticker: str, bars: pd.DataFrame) -> MarketSignals:
    closes = bars["close"].astype(float)
    volumes = bars["volume"].astype(float)
    price = float(closes.iloc[-1])

    sma50 = float(closes.tail(50).mean()) if len(closes) >= 50 else None
    sma200 = float(closes.tail(200).mean()) if len(closes) >= 200 else None
    mom_12_1 = (
        float(closes.iloc[-22] / closes.iloc[-TRADING_DAYS - 1] - 1) if len(closes) > TRADING_DAYS else None
    )
    daily = closes.pct_change().dropna()
    vol = float(daily.tail(TRADING_DAYS).std() * np.sqrt(TRADING_DAYS)) if len(daily) > 20 else None
    vol_ratio = (
        float(volumes.tail(5).mean() / volumes.iloc[-55:-5].mean())
        if len(volumes) >= 55 and volumes.iloc[-55:-5].mean() > 0
        else None
    )
    r = rsi(closes)

    # Trend: above both long-term averages = +1, below both = -1, mixed = 0.
    above = [price > a for a in (sma50, sma200) if a is not None]
    trend_score = 0.0 if not above else (1.0 if all(above) else -1.0 if not any(above) else 0.0)

    # Momentum: 12-1 month return, where +/-30% maps to +/-1.
    momentum_score = float(np.clip((mom_12_1 if mom_12_1 is not None else (_ret(closes, 63) or 0)) / 0.30, -1, 1))

    # RSI: stretched readings lean against the move.
    rsi_score = 0.0 if r is None else (-0.5 if r > 70 else 0.5 if r < 30 else 0.0)

    score = round(0.45 * trend_score + 0.45 * momentum_score + 0.10 * rsi_score * 2, 3)
    label = "bullish" if score > 0.33 else "bearish" if score < -0.33 else "neutral"

    return MarketSignals(
        ticker=ticker, price=price, sma50=sma50, sma200=sma200,
        return_1m=_ret(closes, 21), return_3m=_ret(closes, 63), momentum_12_1=mom_12_1,
        rsi14=r, volatility=vol, volume_ratio=vol_ratio,
        trend_score=trend_score, momentum_score=momentum_score, rsi_score=rsi_score,
        score=score, label=label,
    )


# --------------------------------------------------------------------------
# Explanations
# --------------------------------------------------------------------------

def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def rule_explanation(s: MarketSignals) -> str:
    """Plain summary built from the numbers, used when no AI key is set."""
    if s.sma200 is None:
        trend = "There isn't enough history for a 200-day trend yet."
    elif s.trend_score > 0:
        trend = f"Price ${s.price:,.2f} is above its 50- and 200-day averages, an uptrend."
    elif s.trend_score < 0:
        trend = f"Price ${s.price:,.2f} is below its 50- and 200-day averages, a downtrend."
    else:
        trend = f"Price ${s.price:,.2f} sits between its 50- and 200-day averages, a mixed trend."
    rsi_txt = "" if s.rsi14 is None else (
        f" RSI {s.rsi14:.0f} is overbought (above 70)." if s.rsi14 > 70 else
        f" RSI {s.rsi14:.0f} is oversold (below 30)." if s.rsi14 < 30 else
        f" RSI {s.rsi14:.0f} is in the normal range."
    )
    return (
        f"{trend} Over the past year (excluding the last month) it moved {_pct(s.momentum_12_1)}, "
        f"and {_pct(s.return_1m)} in the last month.{rsi_txt} Signal: {s.label}."
    )


def ai_explanation(s: MarketSignals, model: str) -> str | None:
    """Ask Claude to explain the numbers. Returns None if it can't."""
    import anthropic

    client = anthropic.Anthropic()
    numbers = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(s).items()
               if k not in ("explanation", "explained_by")}
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        output_config={"effort": "low"},
        system=PROMPT_PATH.read_text(),
        messages=[{"role": "user", "content": f"Signals for {s.ticker}:\n{numbers}"}],
    )
    if response.stop_reason == "refusal":
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None


def explain(signals: list[MarketSignals], model: str) -> list[MarketSignals]:
    load_dotenv()
    use_ai = bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    for s in signals:
        text = None
        if use_ai:
            try:
                text = ai_explanation(s, model)
            except Exception as err:  # network, auth, rate limit: fall back, but say so
                s.explained_by = f"rules (AI unavailable: {type(err).__name__})"
        if text:
            s.explanation, s.explained_by = text, f"AI ({model})"
        else:
            s.explanation = rule_explanation(s)
            s.explained_by = s.explained_by or ("rules (AI declined)" if use_ai else "rules (no AI key set)")
    return signals


# --------------------------------------------------------------------------
# Agent entry point
# --------------------------------------------------------------------------

def run(tickers: list[str] | None = None) -> list[MarketSignals]:
    from data.market_data import daily_bars

    settings = load_settings()
    tickers = tickers or settings.tickers
    bars = daily_bars(tickers)
    missing = [t for t in tickers if t not in bars]
    if missing:
        print(f"⚠️  No price data for: {', '.join(missing)}")
    signals = [compute_signals(t, bars[t]) for t in tickers if t in bars]
    return explain(signals, settings.routine_model)


if __name__ == "__main__":
    results = run()
    print(f"\n{'Ticker':<7}{'Price':>10}{'12-1 mom':>10}{'RSI':>6}{'Vol':>8}{'Score':>8}  Signal")
    for s in sorted(results, key=lambda x: -x.score):
        rsi_txt = "n/a" if s.rsi14 is None else f"{s.rsi14:.0f}"
        vol_txt = "n/a" if s.volatility is None else f"{s.volatility * 100:.0f}%"
        print(f"{s.ticker:<7}{s.price:>10,.2f}{_pct(s.momentum_12_1):>10}{rsi_txt:>6}{vol_txt:>8}{s.score:>8.2f}  {s.label}")
    print()
    for s in results:
        print(f"{s.ticker} — {s.explanation}\n   (explained by {s.explained_by})\n")
