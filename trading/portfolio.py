"""A snapshot of the account: what we own, how much cash we have, and what's in flight."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone


@dataclass(frozen=True)
class Position:
    ticker: str
    qty: int
    market_value: float
    avg_entry: float = 0.0        # average price we paid per share

    @property
    def price(self) -> float:
        return self.market_value / self.qty if self.qty else 0.0


@dataclass
class PortfolioState:
    portfolio_value: float          # cash + everything we own, at today's prices
    cash: float                     # actual cash; we never use borrowed "buying power"
    positions: dict[str, Position] = field(default_factory=dict)
    pending_buys: dict[str, float] = field(default_factory=dict)      # ticker -> estimated cost of a buy still waiting to fill
    recently_stopped: dict[str, date] = field(default_factory=dict)   # ticker -> day a stop-loss sold it

    @property
    def pending_cost(self) -> float:
        return sum(self.pending_buys.values())


def _latest_prices(tickers: list[str]) -> dict[str, float]:
    if not tickers:
        return {}
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockLatestTradeRequest

    from data.broker import data_client

    trades = data_client().get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=tickers, feed=DataFeed.IEX))
    return {t: float(tr.price) for t, tr in trades.items()}


def from_alpaca(client=None, cooldown_days: int = 7) -> PortfolioState:
    """Read the paper account: cash, positions, waiting buys, and recent stop-outs."""
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    if client is None:
        from data.broker import trading_client
        client = trading_client()
    acct = client.get_account()
    positions = {
        p.symbol: Position(p.symbol, int(float(p.qty)), float(p.market_value), float(p.avg_entry_price))
        for p in client.get_all_positions()
    }

    # Buys still waiting to fill: count their cost against cash so new buys can't overspend.
    open_orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True))
    waiting = [o for o in open_orders if str(o.side.value) == "buy"]
    prices = _latest_prices(sorted({o.symbol for o in waiting if not o.limit_price}))
    pending: dict[str, float] = {}
    for o in waiting:
        remaining = float(o.qty or 0) - float(o.filled_qty or 0)
        price = float(o.limit_price) if o.limit_price else prices.get(o.symbol, 0.0)
        pending[o.symbol] = pending.get(o.symbol, 0.0) + remaining * price

    # Stop-losses that fired recently (for the re-buy cool-down).
    since = datetime.now(timezone.utc) - timedelta(days=cooldown_days)
    closed = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=since, limit=500, nested=False))
    stopped: dict[str, date] = {}
    for o in closed:
        if str(o.type.value) in ("stop", "stop_limit", "trailing_stop") and str(o.side.value) == "sell" \
                and str(o.status.value) == "filled" and o.filled_at:
            d = o.filled_at.date()
            stopped[o.symbol] = max(d, stopped.get(o.symbol, d))

    return PortfolioState(float(acct.portfolio_value), float(acct.cash), positions, pending, stopped)
