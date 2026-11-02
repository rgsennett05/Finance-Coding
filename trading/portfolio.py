"""A snapshot of the account: what we own and how much cash we have."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Position:
    ticker: str
    qty: int
    market_value: float


@dataclass
class PortfolioState:
    portfolio_value: float          # cash + everything we own, at today's prices
    cash: float                     # actual cash; we never use borrowed "buying power"
    positions: dict[str, Position] = field(default_factory=dict)


def from_alpaca() -> PortfolioState:
    """Read the paper account's current cash and positions."""
    from data.broker import trading_client

    client = trading_client()
    acct = client.get_account()
    positions = {
        p.symbol: Position(p.symbol, int(float(p.qty)), float(p.market_value))
        for p in client.get_all_positions()
    }
    return PortfolioState(float(acct.portfolio_value), float(acct.cash), positions)
