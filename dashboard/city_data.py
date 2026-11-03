"""Turns the latest run log + live account into the "city state" the 3D city draws.

Pure functions only (no network), so it can be tested. The page calls
city_state(latest_run(), load_live()) and hands the result to city.html.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

TEMPLATE = Path(__file__).with_name("city.html")
PENDING = {"accepted", "new", "pending new", "held", "partially filled", "accepted for bidding"}

# Agents in the plan. Built ones light up; planned ones are outlines until Stage 3.
AGENTS = [
    ("market_analyst", "Market Analyst", "Analyst Tower", "Reads prices and calculates trend, momentum, RSI and volatility.", True),
    ("portfolio_manager", "Portfolio Manager", "Headquarters", "Weighs the signals and decides buy, sell or hold.", True),
    ("risk_manager", "Risk Manager", "Risk Fortress", "Plain-code limits: sizes every trade, adds stop-losses, can veto.", True),
    ("fundamentals", "Fundamentals Analyst", "Valuation Bank", "Reads company annual reports from the SEC: valuation, growth, profitability, debt.", True),
    ("news", "News/Sentiment Analyst", "Newsroom", "Recent news and market mood.", False),
    ("bull", "Bull Researcher", "Bull Hall", "Strongest case FOR a trade.", False),
    ("bear", "Bear Researcher", "Bear Hall", "Strongest case AGAINST a trade.", False),
    ("auditor", "Auditor", "Audit Office", "Checks every decision followed the rules.", False),
]


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def agent_details(run: dict | None) -> dict[str, list[str]]:
    """Plain-English lines for each built agent, from the run log."""
    if not run:
        return {}
    signals = sorted(run.get("signals", []), key=lambda s: -s.get("score", 0))
    risk = run.get("risk_review", [])
    funds = run.get("fundamentals")
    out = {
        "fundamentals": (["Counts for 40% of the Portfolio Manager's blended score."] +
                         [f"{f['ticker']}: {f['label']} (score {f['score']:+.2f}) — {f['explanation']}" if f["available"] and f.get("score") is not None
                          else f"{f['ticker']}: {f['reason']}" for f in funds]) if funds is not None else ["Didn't run in this run."],
        "market_analyst": [f"{s['ticker']}: {s['label']} (score {s['score']:+.2f}) — {s.get('explanation', '')}" for s in signals],
        "portfolio_manager": [f"{d['ticker']}: {d['reason']}" for d in run.get("decisions", [])],
        "risk_manager": [],
    }
    for r in risk:
        if r.get("approved"):
            line = f"✅ {r['side'].upper()} {r['qty']} {r['ticker']} at ${r['price']:,.2f}"
            if r.get("stop_price"):
                line += f", stop-loss ${r['stop_price']:,.2f}"
        else:
            line = f"⛔ {r['side'].upper()} {r['ticker']} blocked"
        notes = [n for n in r.get("notes", []) if not n.startswith("Stop-loss set")]
        out["risk_manager"].append(line + (" — " + " ".join(notes) if notes else ""))
    if not out["risk_manager"]:
        out["risk_manager"] = ["Nothing was proposed this run."]
    return out


def flows(run: dict | None) -> list[dict]:
    """The animation script: what travels where, in order."""
    if not run:
        return []
    steps = []
    n_sig = len(run.get("signals", []))
    proposals = [d for d in run.get("decisions", []) if d.get("action") in ("buy", "sell")]
    steps.append({"from": "market_analyst", "to": "portfolio_manager", "kind": "signal",
                  "label": f"{n_sig} signals"})
    funds = [f for f in run.get("fundamentals") or [] if f.get("available")]
    if funds:
        steps.append({"from": "fundamentals", "to": "portfolio_manager", "kind": "fundamentals",
                      "label": f"Fundamentals on {len(funds)} companies"})
    if proposals:
        steps.append({"from": "portfolio_manager", "to": "risk_manager", "kind": "proposal",
                      "label": f"{len(proposals)} proposed trade(s)"})
    orders = {(o["ticker"], o["side"]): o for o in run.get("orders", [])}
    for r in run.get("risk_review", []):
        if not r.get("approved"):
            steps.append({"from": "risk_manager", "to": r["ticker"], "kind": "blocked",
                          "label": f"{r['side'].upper()} {r['ticker']} blocked"})
            continue
        o = orders.get((r["ticker"], r["side"]), {})
        status = o.get("status", "dry-run")
        kind = "order" if status == "submitted" else "skipped" if status == "skipped" else "preview"
        steps.append({"from": "risk_manager", "to": r["ticker"], "kind": kind,
                      "label": f"{r['side'].upper()} {r['qty']} {r['ticker']} — {status}"})
    return steps


def stocks(run: dict | None, live: dict | None, tickers: list[str], benchmark: str) -> list[dict]:
    sig = {s["ticker"]: s for s in (run or {}).get("signals", [])}
    pos = {}
    if live is not None and not live["positions"].empty:
        pos = {r["Stock"]: r for r in live["positions"].to_dict("records")}
    pending, stops = set(), {}
    if live is not None and not live["orders"].empty:
        for r in live["orders"].to_dict("records"):
            if str(r["Status"]).lower() in PENDING and r["Side"] == "BUY":
                pending.add(r["Stock"])
                if _num(r.get("Stop-loss")):
                    stops[r["Stock"]] = _num(r["Stop-loss"])
    quotes = (live or {}).get("quotes", {}) if live is not None else {}
    out = []
    for t in dict.fromkeys([*tickers, *pos]):
        s, p, q = sig.get(t, {}), pos.get(t, {}), quotes.get(t, {})
        out.append({
            "ticker": t,
            "benchmark": t == benchmark,
            "label": s.get("label"),
            "score": _num(s.get("score")),
            "price": _num(q.get("price")) or _num(p.get("Price")) or _num(s.get("price")),
            "change_pct": _num(q.get("change_pct")),
            "live": bool(q),
            "shares": int(p.get("Shares", 0) or 0),
            "value": _num(p.get("Value")) or 0.0,
            "pl_pct": _num(p.get("Gain/loss %")),
            "weight": _num(p.get("Weight")) or 0.0,
            "stop": _num(p.get("Stop-loss")) or stops.get(t),
            "pending": t in pending,
        })
    return out


def trades(live: dict | None) -> list[dict]:
    """Recent orders, newest first, for the light trails between the Risk Fortress and the towers."""
    if live is None or live["orders"].empty:
        return []
    out = []
    for r in live["orders"].to_dict("records"):
        submitted = pd.to_datetime(r.get("Submitted"), utc=True, errors="coerce")
        out.append({
            "ticker": r["Stock"], "side": str(r.get("Side", "")).lower(), "shares": int(r.get("Shares") or 0),
            "status": str(r.get("Status", "")).lower(),
            "submitted": None if pd.isna(submitted) else submitted.isoformat(),
            "fill_price": _num(r.get("Fill price")),
        })
    return out


def activity(run: dict | None, live: dict | None, now: pd.Timestamp | None = None) -> dict:
    """How busy the fund is: drives traffic, crowds and lit windows in the city (0 = quiet, 1 = busy)."""
    now = now or pd.Timestamp.now(tz="UTC")
    recent = [t for t in trades(live) if t["submitted"] and now - pd.Timestamp(t["submitted"]) < pd.Timedelta(hours=24)]
    market_open = bool(getattr((live or {}).get("clock"), "is_open", False))
    ran_recently = False
    if run and run.get("run_at"):
        at = pd.Timestamp(run["run_at"])
        at = at.tz_localize("UTC") if at.tzinfo is None else at
        ran_recently = now - at < pd.Timedelta(hours=24)
    level = 0.15 + 0.35 * market_open + 0.1 * min(len(recent), 4) + 0.1 * bool(ran_recently)
    return {"level": round(min(level, 1.0), 2), "orders_24h": len(recent), "market_open": market_open}


def city_state(run: dict | None, live: dict | None, tickers: list[str], benchmark: str) -> dict:
    details = agent_details(run)
    ran = bool(run)
    acct = (live or {}).get("account", {})
    return {
        "trades": trades(live),
        "quotes_at": max((q["at"] for q in (live or {}).get("quotes", {}).values()), default=None) if live else None,
        "activity": activity(run, live),
        "run": {"at": run.get("run_at") if run else None, "mode": run.get("mode") if run else None},
        "market_open": bool(getattr((live or {}).get("clock"), "is_open", False)),
        "account": {k: _num(v) for k, v in acct.items()},
        "agents": [
            {"id": a, "name": n, "building": b, "role": role,
             "status": ("active" if ran and (a != "fundamentals" or run.get("fundamentals") is not None) else "idle") if built else "planned",
             "details": details.get(a, []) if built else ["Planned for Stage 3."]}
            for a, n, b, role, built in AGENTS
        ],
        "flows": flows(run),
        "stocks": stocks(run, live, tickers, benchmark),
    }


def render(state: dict) -> str:
    """city.html with the state baked in (safe inside a <script> tag)."""
    data = json.dumps(state, default=str).replace("</", "<\\/")
    return TEMPLATE.read_text().replace("/*__CITY_STATE__*/null", data)
