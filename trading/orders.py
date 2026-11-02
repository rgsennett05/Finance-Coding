"""Places approved trades on the Alpaca PAPER account.

Only decisions the Risk Manager approved ever reach this file.

  - Buys are market orders for whole shares with a stop-loss attached
    ("one-triggers-other": once the buy fills, the stop-loss order goes live).
    Both use good-till-canceled, so the stop stays in place after today.
  - Sells first cancel that stock's open stop-loss (Alpaca holds the shares
    for it), then sell at market.
  - If earlier buy orders are still waiting to fill, no new buys are placed,
    so running twice before the market opens can't double-buy.
"""
from __future__ import annotations

from dataclasses import dataclass

from agents.risk_manager import RiskDecision

PAPER_URL_MARK = "paper-api.alpaca.markets"


@dataclass
class OrderResult:
    ticker: str
    side: str
    qty: int
    status: str            # submitted | skipped | failed | dry-run
    detail: str
    order_id: str | None = None


def buy_request(d: RiskDecision):
    from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest, StopLossRequest

    if not d.stop_price:
        raise ValueError(f"{d.ticker}: refusing to buy without a stop-loss")
    return MarketOrderRequest(
        symbol=d.ticker, qty=d.qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
        order_class=OrderClass.OTO, stop_loss={"stop_price": d.stop_price},
    )


def sell_request(d: RiskDecision):
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    return MarketOrderRequest(symbol=d.ticker, qty=d.qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)


def open_orders(client) -> list:
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    return list(client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True)))


def pending_buys(orders) -> set[str]:
    """Tickers with a buy order that hasn't filled yet (stop-loss orders don't count)."""
    return {o.symbol for o in orders if str(getattr(o.side, "value", o.side)) == "buy"}


def place(decisions: list[RiskDecision], client=None, dry_run: bool = True) -> list[OrderResult]:
    approved = [d for d in decisions if d.approved]
    if dry_run:
        return [OrderResult(d.ticker, d.side, d.qty, "dry-run", "Not sent (dry run).") for d in approved]

    if client is None:
        from data.broker import trading_client
        client = trading_client()
    if PAPER_URL_MARK not in str(getattr(client, "_base_url", "")):
        raise RuntimeError("STOP: trading client is not pointed at Alpaca's paper endpoint. No orders sent.")

    orders = open_orders(client)
    waiting = pending_buys(orders)
    results: list[OrderResult] = []

    for d in sorted(approved, key=lambda d: d.side != "sell"):
        try:
            if d.side == "sell":
                for o in orders:
                    if o.symbol == d.ticker:
                        client.cancel_order_by_id(o.id)
                sent = client.submit_order(sell_request(d))
            else:
                if waiting:
                    results.append(OrderResult(d.ticker, "buy", d.qty, "skipped",
                        f"Earlier buy orders are still waiting to fill ({', '.join(sorted(waiting))}); "
                        "no new buys until they do."))
                    continue
                sent = client.submit_order(buy_request(d))
            results.append(OrderResult(d.ticker, d.side, d.qty, "submitted",
                                       f"Order accepted, status {getattr(sent.status, 'value', sent.status)}.",
                                       str(sent.id)))
        except Exception as err:  # one bad order must not stop the others
            results.append(OrderResult(d.ticker, d.side, d.qty, "failed", f"{type(err).__name__}: {err}"))
    return results
