"""The 'Did we make money?' section: profit from finished trades vs. stocks still held."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from dashboard.data import closed_trades, profit_breakdown
from dashboard.overview import profit_sentence

E = lambda v: NS(value=v)
T0 = datetime(2026, 11, 3, 14, 30, tzinfo=timezone.utc)


def order(sym, side, qty, price, day, kind="market", legs=()):
    return NS(symbol=sym, side=E(side), type=E(kind), status=E("filled"), qty=str(qty), filled_qty=str(qty),
              filled_avg_price=str(price), filled_at=T0 + timedelta(days=day), legs=list(legs))


def test_stop_loss_sale_is_measured_against_the_price_we_paid():
    stop = order("XOM", "sell", 55, 163.88, 3, kind="stop")
    trades = closed_trades([order("XOM", "buy", 55, 179.20, 0, legs=[stop])])
    [t] = trades.to_dict("records")
    assert t["Shares"] == 55 and t["Paid"] == pytest.approx(179.20)
    assert t["Profit/loss $"] == pytest.approx((163.88 - 179.20) * 55)
    assert t["Why sold"].startswith("Stop-loss")


def test_rebuying_after_a_sale_starts_a_fresh_cost():
    trades = closed_trades([
        order("XOM", "buy", 10, 100, 0), order("XOM", "sell", 10, 90, 1, kind="stop"),
        order("XOM", "buy", 10, 80, 5), order("XOM", "sell", 10, 88, 9),
    ])
    assert list(trades["Profit/loss $"]) == pytest.approx([-100, 80])


def test_unfilled_orders_are_ignored():
    o = order("AAPL", "buy", 5, 100, 0)
    o.status = E("canceled")
    assert closed_trades([o]).empty


def test_breakdown_and_plain_sentence():
    closed = pd.DataFrame({"Profit/loss $": [-2447.0]})
    pos = pd.DataFrame({"Gain/loss $": [894.0]})
    p = profit_breakdown(100_000, 98_447, closed, pos, bench_change=-0.024)
    assert p["total"] == pytest.approx(-1553) and p["other"] == pytest.approx(0)
    text = profit_sentence(p)
    assert "lost \\$1,553.00" in text and "did **better than** simply holding VOO" in text


def test_money_puts_the_minus_sign_first():
    from dashboard.overview import money
    assert money(-2446.93) == "-$2,446.93" and money(785.6) == "$785.60"
