"""Alerts — problems that need a human, found at the end of every run.

  - an order or stop-loss change that failed to send
  - an order Alpaca accepted at first but then rejected or cancelled
  - a stock we own with no stop-loss at all

Any alert makes the run exit with an error, so the daily GitHub run shows a red ✕
and GitHub emails the owner. On GitHub the alerts also appear on the run's summary page.
"""
from __future__ import annotations

import os
import time

BAD_STATUSES = {"rejected", "canceled", "expired", "suspended"}


def _v(x) -> str:
    return str(getattr(x, "value", x))


def find(results, stop_actions, client=None, dry_run: bool = True, settle_seconds: float = 3.0) -> list[str]:
    alerts = [f"Order failed to send: {o.side.upper()} {o.qty} {o.ticker} — {o.detail}" for o in results if o.status == "failed"]
    alerts += [f"Stop-loss change failed for {a.ticker}: {a.detail}" for a in stop_actions if a.status == "failed"]
    if dry_run or client is None:
        return alerts

    submitted = [o for o in results if o.status == "submitted" and o.order_id]
    if submitted or stop_actions:
        time.sleep(settle_seconds)            # give Alpaca a moment to accept or reject

    for o in submitted:
        try:
            status = _v(client.get_order_by_id(o.order_id).status)
        except Exception as err:
            alerts.append(f"Couldn't confirm the {o.side.upper()} {o.ticker} order: {type(err).__name__}: {err}")
            continue
        if status in BAD_STATUSES:
            alerts.append(f"Alpaca {status} the {o.side.upper()} {o.qty} {o.ticker} order.")

    from trading.orders import open_orders

    stop_types = ("stop", "stop_limit", "trailing_stop")
    orders = open_orders(client)
    for pos in client.get_all_positions():
        t, qty = pos.symbol, int(float(pos.qty))
        if qty <= 0:
            continue
        mine = [o for o in orders if o.symbol == t]
        has_stop = any(_v(o.side) == "sell" and _v(o.type) in stop_types for o in mine)
        being_sold = any(_v(o.side) == "sell" and _v(o.type) not in stop_types for o in mine)
        if not has_stop and not being_sold:
            alerts.append(f"{t}: {qty} shares have NO stop-loss after the stop-loss check.")
    return alerts


def report(alerts: list[str]) -> None:
    if not alerts:
        print("\n✅ No alerts.")
        return
    print("\n🚨 ALERTS — these need your attention:")
    for a in alerts:
        print(f"   • {a}")
        if os.getenv("GITHUB_ACTIONS") == "true":
            print(f"::error title=Trading City alert::{a}")
