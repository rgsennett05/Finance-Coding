"""Daily price and volume history from Alpaca (free IEX feed)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from data.broker import data_client


def daily_bars(tickers: list[str], days: int = 400) -> dict[str, pd.DataFrame]:
    """Return {ticker: DataFrame with 'close' and 'volume', oldest row first}.

    `days` is calendar days; 400 gives about 275 trading days, enough for a
    200-day average and 12-month momentum.
    """
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    request = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Day,
        start=datetime.now(timezone.utc) - timedelta(days=days),
        feed=DataFeed.IEX,
    )
    df = data_client().get_stock_bars(request).df
    out: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        if ticker in df.index.get_level_values(0):
            frame = df.xs(ticker, level=0)[["close", "volume"]].sort_index()
            out[ticker] = frame
    return out


def live_quotes(tickers: list[str]) -> dict[str, dict]:
    """Latest trade price for each ticker and today's change vs. yesterday's close (free IEX feed)."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockSnapshotRequest

    snaps = data_client().get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=tickers, feed=DataFeed.IEX))
    out = {}
    for t, s in snaps.items():
        if not s or not s.latest_trade:
            continue
        price = float(s.latest_trade.price)
        prev = float(s.previous_daily_bar.close) if s.previous_daily_bar else None
        out[t] = {
            "price": price,
            "prev_close": prev,
            "change_pct": (price / prev - 1) if prev else None,
            "at": s.latest_trade.timestamp.isoformat(),
        }
    return out
