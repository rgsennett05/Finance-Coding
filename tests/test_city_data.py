"""Checks the 3D city's data (no internet, no browser)."""
import json

import pandas as pd

from dashboard.city_data import activity, city_state, flows, render, trades

RUN = {
    "run_at": "2026-11-02T23:27:21", "mode": "paper",
    "signals": [{"ticker": "AAA", "label": "bullish", "score": 0.9, "price": 10.0, "explanation": "Up."},
                {"ticker": "VOO", "label": "neutral", "score": 0.2, "price": 600.0, "explanation": "Flat."}],
    "decisions": [{"ticker": "AAA", "action": "buy", "reason": "BUY: bullish."},
                  {"ticker": "VOO", "action": "hold", "reason": "Benchmark."}],
    "risk_review": [{"ticker": "AAA", "side": "buy", "approved": True, "qty": 5, "price": 10.0,
                     "stop_price": 9.2, "notes": ["Stop-loss set 8% below entry."]},
                    {"ticker": "BBB", "side": "buy", "approved": False, "qty": 0, "price": 1e5,
                     "notes": ["One share costs too much."]}],
    "orders": [{"ticker": "AAA", "side": "buy", "qty": 5, "status": "submitted", "detail": "ok"}],
}

LIVE = {
    "account": {"portfolio_value": 100_000.0, "cash": 99_950.0, "today_change": 0.0, "today_pct": 0.0},
    "positions": pd.DataFrame(),
    "orders": pd.DataFrame([{"Stock": "AAA", "Side": "BUY", "Status": "accepted", "Stop-loss": 9.2}]),
    "clock": None,
}


def test_flow_goes_analyst_to_pm_to_risk_to_stocks():
    f = flows(RUN)
    assert [(x["from"], x["to"], x["kind"]) for x in f] == [
        ("market_analyst", "portfolio_manager", "signal"),
        ("portfolio_manager", "risk_manager", "proposal"),
        ("risk_manager", "AAA", "order"),
        ("risk_manager", "BBB", "blocked"),
    ]


def test_state_marks_built_and_planned_agents_and_pending_orders():
    s = city_state(RUN, LIVE, ["AAA", "VOO"], "VOO")
    status = {a["id"]: a["status"] for a in s["agents"]}
    assert status["market_analyst"] == "active" and status["auditor"] == "planned"
    aaa = next(x for x in s["stocks"] if x["ticker"] == "AAA")
    assert aaa["pending"] and aaa["stop"] == 9.2 and aaa["shares"] == 0
    assert next(x for x in s["stocks"] if x["ticker"] == "VOO")["benchmark"]


def test_no_run_yet_still_draws_a_city():
    s = city_state(None, None, ["AAA"], "VOO")
    assert s["flows"] == [] and {a["status"] for a in s["agents"]} == {"idle", "planned"}


def test_render_embeds_state_safely():
    state = city_state(RUN, LIVE, ["AAA"], "VOO")
    state["agents"][0]["details"].append("</script><b>x</b>")
    html = render(state)
    assert "</script><b>" not in html
    start = html.index("const CITY = ") + len("const CITY = ")
    assert json.loads(html[start:html.index(";\n", start)])["run"]["mode"] == "paper"


def test_trades_and_activity():
    live = dict(LIVE, orders=pd.DataFrame([
        {"Submitted": pd.Timestamp("2026-11-02T23:27:21Z"), "Stock": "AAA", "Side": "BUY", "Shares": 5,
         "Status": "accepted", "Fill price": float("nan"), "Stop-loss": 9.2},
    ]))
    t = trades(live)
    assert t[0]["ticker"] == "AAA" and t[0]["side"] == "buy" and t[0]["fill_price"] is None
    busy = activity(RUN, live, now=pd.Timestamp("2026-11-03T01:00:00Z"))
    quiet = activity(None, None, now=pd.Timestamp("2026-11-10T01:00:00Z"))
    assert busy["orders_24h"] == 1 and busy["level"] > quiet["level"]
