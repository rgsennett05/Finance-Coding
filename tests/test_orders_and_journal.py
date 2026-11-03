"""Checks order building, the no-double-buy guard, and the run log (no real orders)."""
import json
from types import SimpleNamespace as NS

import pytest

from agents.risk_manager import RiskDecision
from trading import journal, orders


def buy(t="AAA", qty=10, stop=92.0):
    return RiskDecision(t, "buy", True, qty, 100.0, stop)


class FakeClient:
    _base_url = "https://paper-api.alpaca.markets"

    def __init__(self, open_orders=()):
        self._open = list(open_orders)
        self.submitted, self.canceled = [], []

    def get_orders(self, _):
        return self._open

    def cancel_order_by_id(self, oid):
        self.canceled.append(oid)

    def submit_order(self, req):
        self.submitted.append(req)
        return NS(id=f"id{len(self.submitted)}", status="accepted")


def test_buy_has_whole_shares_and_a_stop_that_stays():
    req = orders.buy_request(buy())
    body = req.model_dump(exclude_none=True)
    assert body["qty"] == 10 and body["stop_loss"]["stop_price"] == 92.0
    assert str(body["time_in_force"].value) == "gtc"
    assert str(body["order_class"].value) == "oto"


def test_buy_without_stop_is_refused():
    with pytest.raises(ValueError):
        orders.buy_request(buy(stop=None))


def test_dry_run_sends_nothing():
    c = FakeClient()
    res = orders.place([buy()], client=c, dry_run=True)
    assert c.submitted == [] and res[0].status == "dry-run"


def test_blocked_decisions_are_never_sent():
    c = FakeClient()
    orders.place([RiskDecision("X", "buy", False)], client=c, dry_run=False)
    assert c.submitted == []


def test_no_second_buy_for_a_stock_already_waiting():
    c = FakeClient([NS(id="o1", symbol="OLD", side="buy")])
    res = orders.place([buy("OLD"), buy("NEW")], client=c, dry_run=False)
    assert [r.status for r in res] == ["skipped", "submitted"]
    assert len(c.submitted) == 1


def test_dry_run_preview_matches_a_real_run():
    c = FakeClient([NS(id="o1", symbol="OLD", side="buy")])
    res = orders.place([buy("OLD"), buy("NEW")], client=c, dry_run=True)
    assert [r.status for r in res] == ["skipped", "dry-run"]


def test_sell_cancels_that_stocks_stop_first():
    c = FakeClient([NS(id="stop1", symbol="AAA", side="sell"), NS(id="other", symbol="BBB", side="sell")])
    orders.place([RiskDecision("AAA", "sell", True, 5, 100.0)], client=c, dry_run=False)
    assert c.canceled == ["stop1"] and len(c.submitted) == 1


def test_refuses_a_non_paper_client():
    c = FakeClient()
    c._base_url = "https://api.alpaca.markets"
    with pytest.raises(RuntimeError, match="paper"):
        orders.place([buy()], client=c, dry_run=False)


def test_journal_writes_readable_json(tmp_path):
    path = journal.write({"orders": [orders.OrderResult("A", "buy", 1, "dry-run", "x")], "n": float("nan")}, tmp_path)
    data = json.loads(path.read_text())
    assert data["orders"][0]["ticker"] == "A" and data["n"] is None and "run_at" in data


def test_real_alpaca_client_is_recognized_as_paper(monkeypatch):
    # Uses the actual alpaca-py client (no network), not the fake one above.
    from data.broker import trading_client
    monkeypatch.setenv("ALPACA_API_KEY", "PKTEST")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    assert orders.is_paper(trading_client())


def test_live_alpaca_client_is_not_paper():
    from alpaca.trading.client import TradingClient
    assert not orders.is_paper(TradingClient("AKLIVE", "secret", paper=False))
