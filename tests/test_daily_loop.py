"""End-to-end test of the whole daily loop (python -m trading.run) against a pretend Alpaca account.

No internet, no real orders. It runs the real agents, Risk Manager, order placement, stop-loss
check, alerts and log over several "days", so a change anywhere can't silently break trading.
"""
import itertools
import json
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from trading import alerts, journal
from trading import run as daily

PAPER_URL = "https://paper-api.alpaca.markets"
E = lambda v: NS(value=v)   # Alpaca returns enums with a .value


class FakeAlpaca:
    """Just enough of Alpaca's trading client for the daily loop."""

    _base_url = PAPER_URL

    def __init__(self, cash=100_000.0):
        self.cash = cash
        self.positions = {}          # ticker -> dict(qty, entry, price)
        self.orders = {}             # id -> order namespace
        self.ids = (f"o{i}" for i in itertools.count(1))
        self.prices = {}
        self.reject_next = False

    # --- account -------------------------------------------------------------
    def get_clock(self):
        return NS(is_open=True, next_open=datetime(2026, 11, 4, 9, 30, tzinfo=timezone.utc))

    def get_account(self):
        value = self.cash + sum(p["qty"] * self.prices[t] for t, p in self.positions.items())
        return NS(portfolio_value=str(value), equity=str(value), cash=str(self.cash), last_equity=str(value))

    def get_all_positions(self):
        return [NS(symbol=t, qty=str(p["qty"]), avg_entry_price=str(p["entry"]), current_price=str(self.prices[t]),
                   market_value=str(p["qty"] * self.prices[t])) for t, p in self.positions.items() if p["qty"] > 0]

    # --- orders --------------------------------------------------------------
    def _new(self, **kw):
        o = NS(**{"id": next(self.ids), "legs": [], "filled_qty": "0", "limit_price": None, "stop_price": None,
                  "filled_at": None, **kw})
        self.orders[o.id] = o
        return o

    def get_orders(self, req):
        want = str(getattr(req.status, "value", req.status))
        open_states = {"accepted", "new", "held", "pending_replace"}
        top = [o for o in self.orders.values() if not getattr(o, "is_leg", False)]
        if want == "open":
            out = []
            for o in self.orders.values():
                if o.status.value in open_states and (not getattr(o, "is_leg", False) or o.status.value != "held"):
                    out.append(o)
            return out
        return [o for o in top if o.status.value not in open_states]

    def get_order_by_id(self, oid):
        return self.orders[oid]

    def submit_order(self, req):
        side, typ = str(req.side.value), str(req.type.value)
        status = "rejected" if self.reject_next else "accepted"
        self.reject_next = False
        o = self._new(symbol=req.symbol, side=E(side), type=E(typ), qty=str(int(req.qty)), status=E(status),
                      stop_price=getattr(req, "stop_price", None))
        sl = getattr(req, "stop_loss", None)
        if sl and status == "accepted":
            leg = self._new(symbol=req.symbol, side=E("sell"), type=E("stop"), qty=str(int(req.qty)), status=E("held"),
                            stop_price=str(sl.stop_price), is_leg=True)
            o.legs = [leg]
        return o

    def cancel_order_by_id(self, oid):
        self.orders[oid].status = E("canceled")

    def replace_order_by_id(self, oid, req):
        o = self.orders[oid]
        if req.qty is not None:
            o.qty = str(int(req.qty))
        if req.stop_price is not None:
            o.stop_price = str(req.stop_price)
        return o

    # --- the market opens: every waiting market order fills at today's price ---
    def open_market(self, fill_prices):
        self.prices.update(fill_prices)
        for o in list(self.orders.values()):
            if getattr(o, "is_leg", False) or o.status.value != "accepted" or o.type.value != "market":
                continue
            t, qty, px = o.symbol, int(o.qty), self.prices[o.symbol]
            p = self.positions.setdefault(t, {"qty": 0, "entry": px})
            if o.side.value == "buy":
                p["entry"] = (p["entry"] * p["qty"] + px * qty) / (p["qty"] + qty)
                p["qty"] += qty
                self.cash -= qty * px
                for leg in o.legs:
                    leg.status = E("new")          # the attached stop-loss goes live
            else:
                p["qty"] -= qty
                self.cash += qty * px
            o.status, o.filled_qty, o.filled_at = E("filled"), o.qty, datetime.now(timezone.utc)

    def stops_for(self, t):
        return [o for o in self.orders.values() if o.symbol == t and o.type.value == "stop" and o.status.value in ("accepted", "new", "held")]


# ------------------------------------------------------------------------------------------
# Wiring: fake broker, fake price history, logs in a temp folder
# ------------------------------------------------------------------------------------------

def bars_for(tickers, last_prices):
    idx = pd.bdate_range("2025-06-02", periods=300)
    out = {}
    for t in tickers:
        if t == "AAPL":      # steady uptrend -> bullish
            closes = np.linspace(60, last_prices["AAPL"], len(idx))
        else:                # flat -> neutral, never traded
            closes = np.full(len(idx), last_prices.get(t, 100.0))
        out[t] = pd.DataFrame({"close": closes, "volume": 1_000.0}, index=idx)
    return out


@pytest.fixture
def world(monkeypatch, tmp_path):
    broker = FakeAlpaca()
    signal_price = {"AAPL": 100.0}
    monkeypatch.setattr(daily, "trading_client", lambda: broker)
    monkeypatch.setattr("data.market_data.daily_bars", lambda tickers, days=400: bars_for(tickers, signal_price))
    monkeypatch.setattr("trading.portfolio._latest_prices", lambda tickers: {t: broker.prices.get(t, signal_price.get(t, 100.0)) for t in tickers})
    real_write = journal.write
    monkeypatch.setattr(journal, "write", lambda record: real_write(record, tmp_path))
    monkeypatch.setattr(alerts.time, "sleep", lambda s: None)
    return NS(broker=broker, signal_price=signal_price, logs=tmp_path)


def last_log(logs):
    return json.loads(sorted(logs.glob("run_*.json"))[-1].read_text())


def test_full_daily_loop_over_several_days(world):
    b = world.broker

    # Day 1: empty account. The Market Analyst rates AAPL bullish -> one buy with a stop attached.
    assert daily.main(["--yes"]) == 0
    log = last_log(world.logs)
    assert [(o["ticker"], o["status"]) for o in log["orders"]] == [("AAPL", "submitted")]
    buy = next(o for o in b.orders.values() if o.side.value == "buy")
    assert float(buy.legs[0].stop_price) == 92.0                # 8% under the $100 signal price
    assert log["alerts"] == []

    # Running again before the market opens must not buy twice.
    assert daily.main(["--yes"]) == 0
    assert sum(o.side.value == "buy" for o in b.orders.values()) == 1

    # Day 2: the buy fills at $104, not $100. The stop must move to 8% under the real price.
    world.signal_price["AAPL"] = 104.0
    b.open_market({"AAPL": 104.0})
    assert daily.main(["--yes"]) == 0
    [stop] = b.stops_for("AAPL")
    assert float(stop.stop_price) == round(104 * 0.92, 2)
    assert int(stop.qty) == b.positions["AAPL"]["qty"]
    assert last_log(world.logs)["stop_maintenance"][0]["action"] == "replace"

    # Day 3: AAPL jumps so it's over 11% of the portfolio -> trimmed back toward 10%.
    world.signal_price["AAPL"] = 140.0
    b.prices["AAPL"] = 140.0
    assert daily.main(["--yes"]) == 0
    trims = [o for o in b.orders.values() if o.side.value == "sell" and o.type.value == "market"]
    assert len(trims) == 1
    log = last_log(world.logs)
    assert log["trims"] and log["trims"][0]["ticker"] == "AAPL"
    # The stop now covers only the shares that aren't being sold.
    [stop] = b.stops_for("AAPL")
    assert int(stop.qty) == b.positions["AAPL"]["qty"] - int(trims[0].qty)


def test_missing_stop_is_recreated(world):
    b = world.broker
    daily.main(["--yes"])
    b.open_market({"AAPL": 100.0})
    for s in b.stops_for("AAPL"):
        b.cancel_order_by_id(s.id)                              # someone cancelled the stop by hand
    assert daily.main(["--yes"]) == 0
    [stop] = b.stops_for("AAPL")
    assert float(stop.stop_price) == 92.0
    assert last_log(world.logs)["stop_maintenance"][0]["action"] == "create"


def test_rejected_order_raises_an_alert_and_fails_the_run(world, capsys):
    world.broker.reject_next = True
    assert daily.main(["--yes"]) == 1
    log = last_log(world.logs)
    assert any("rejected" in a for a in log["alerts"])
    assert "ALERTS" in capsys.readouterr().out


def test_dry_run_sends_nothing(world):
    assert daily.main(["--dry-run"]) == 0
    assert world.broker.orders == {}
