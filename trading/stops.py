"""Stop maintenance — keeps every position protected by the right stop-loss. Plain code, no AI.

Runs after orders are placed. For every stock we own it makes sure there is
exactly one stop-loss order that:
  - covers every share that isn't already being sold, and
  - sits stop_loss_pct below the price we actually paid (not the price we
    expected when the order was placed — a buy can fill higher or lower).

What it can do, per stock:
  ok       the stop is already right
  create   no stop existed (e.g. one was cancelled), so it adds one
  replace  moves an existing stop to the right price and/or share count
  exit     the price is already below where the stop belongs, so it sells
           at market — exactly what the stop would have done
  skip     nothing to protect (a buy is still filling, or every share is
           already being sold)
"""
from __future__ import annotations

from dataclasses import dataclass

from config.settings import RiskLimits

STOP_TYPES = ("stop", "stop_limit", "trailing_stop")


@dataclass
class StopAction:
    ticker: str
    action: str          # ok | create | replace | exit | skip
    qty: int
    stop_price: float | None
    detail: str
    status: str = "planned"   # planned | done | failed | dry-run


def _v(x) -> str:
    return str(getattr(x, "value", x))


def plan(positions: list, open_orders: list, limits: RiskLimits) -> list[tuple[StopAction, list, object]]:
    """Decide what each position needs. Returns (action, stop orders found, position)."""
    out = []
    for pos in positions:
        t = pos.symbol
        qty = int(float(pos.qty))
        if qty <= 0:
            continue                                    # long-only fund; nothing to protect
        entry = float(pos.avg_entry_price)
        price = float(pos.current_price)
        target = round(entry * (1 - limits.stop_loss_pct), 2)
        mine = [o for o in open_orders if o.symbol == t]
        if any(_v(o.side) == "buy" for o in mine):
            out.append((StopAction(t, "skip", 0, None, "A buy for this stock is still filling; its stop is set when it completes."), [], pos))
            continue
        stops = [o for o in mine if _v(o.side) == "sell" and _v(o.type) in STOP_TYPES]
        exits = [o for o in mine if _v(o.side) == "sell" and _v(o.type) not in STOP_TYPES]
        selling = sum(int(float(o.qty or 0)) - int(float(o.filled_qty or 0)) for o in exits)
        protect = qty - selling
        if protect <= 0:
            out.append((StopAction(t, "skip", 0, None, "Every share is already being sold."), stops, pos))
            continue
        if price <= target:
            out.append((StopAction(t, "exit", protect, target,
                f"Price ${price:,.2f} is already at or below the stop level ${target:,.2f} "
                f"({limits.stop_loss_pct:.0%} under the ${entry:,.2f} we paid); selling {protect} shares at market."), stops, pos))
            continue
        if not stops:
            out.append((StopAction(t, "create", protect, target,
                f"No stop-loss found; adding one for {protect} shares at ${target:,.2f} "
                f"({limits.stop_loss_pct:.0%} under the ${entry:,.2f} we paid)."), stops, pos))
            continue
        s = stops[0]
        cur_stop = float(s.stop_price) if s.stop_price else None
        cur_qty = int(float(s.qty or 0))
        if len(stops) == 1 and cur_qty == protect and cur_stop is not None and abs(cur_stop - target) < 0.01:
            out.append((StopAction(t, "ok", protect, target, f"Stop-loss in place: {protect} shares at ${target:,.2f}."), stops, pos))
            continue
        changes = []
        if cur_stop is None or abs(cur_stop - target) >= 0.01:
            changes.append(f"price ${cur_stop or 0:,.2f} → ${target:,.2f} ({limits.stop_loss_pct:.0%} under the ${entry:,.2f} we paid)")
        if cur_qty != protect:
            changes.append(f"shares {cur_qty} → {protect}")
        if len(stops) > 1:
            changes.append(f"removing {len(stops) - 1} extra stop order(s)")
        out.append((StopAction(t, "replace", protect, target, "Adjusting stop-loss: " + "; ".join(changes) + "."), stops, pos))
    return out


def maintain(client, limits: RiskLimits, dry_run: bool = True) -> list[StopAction]:
    """Check and fix every position's stop-loss on the paper account."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest, ReplaceOrderRequest, StopOrderRequest

    from trading.orders import is_paper, open_orders

    if not is_paper(client):
        raise RuntimeError("STOP: trading client is not pointed at Alpaca's paper endpoint. No stop changes made.")

    actions = []
    for action, stops, _pos in plan(client.get_all_positions(), open_orders(client), limits):
        actions.append(action)
        if action.action in ("ok", "skip"):
            action.status = "done"
            continue
        if dry_run:
            action.status = "dry-run"
            continue
        try:
            if action.action == "create":
                client.submit_order(StopOrderRequest(symbol=action.ticker, qty=action.qty, side=OrderSide.SELL,
                                                     time_in_force=TimeInForce.GTC, stop_price=action.stop_price))
            elif action.action == "replace":
                for extra in stops[1:]:
                    client.cancel_order_by_id(extra.id)
                client.replace_order_by_id(stops[0].id, ReplaceOrderRequest(qty=action.qty, stop_price=action.stop_price))
            elif action.action == "exit":
                for s in stops:
                    client.cancel_order_by_id(s.id)
                client.submit_order(MarketOrderRequest(symbol=action.ticker, qty=action.qty, side=OrderSide.SELL,
                                                       time_in_force=TimeInForce.DAY))
            action.status = "done"
        except Exception as err:  # one failure must not stop the others
            action.status = "failed"
            action.detail += f" FAILED: {type(err).__name__}: {err}"
    return actions
