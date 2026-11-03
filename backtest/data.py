"""Daily price history for the backtest, adjusted for splits and dividends (free IEX feed)."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def history(tickers: list[str], start: datetime) -> dict[str, pd.DataFrame]:
    """{ticker: DataFrame[open, high, low, close, volume]} indexed by trading date, oldest first."""
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    from data.broker import data_client

    df = data_client().get_stock_bars(StockBarsRequest(
        symbol_or_symbols=tickers, timeframe=TimeFrame.Day, start=start.replace(tzinfo=timezone.utc),
        feed=DataFeed.IEX, adjustment=Adjustment.ALL,
    )).df
    out = {}
    for t in tickers:
        if t in df.index.get_level_values(0):
            frame = df.xs(t, level=0)[["open", "high", "low", "close", "volume"]].astype(float).sort_index()
            frame.index = pd.DatetimeIndex([ts.date() for ts in frame.index])
            out[t] = frame
    return out
