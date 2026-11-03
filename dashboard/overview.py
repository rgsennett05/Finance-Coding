"""Overview page: account numbers, performance vs. VOO, positions, orders, agent reasoning."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.data import latest_run
from dashboard.live_cache import live

FUND_COLOR, BENCH_COLOR = "#2a78d6", "#eb6834"   # categorical slots 1 and 2


def money(x: float | None) -> str:
    return "—" if x is None or pd.isna(x) else f"${x:,.2f}"


# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------
top = st.columns([4, 1])
top[0].title("🏙️ Trading City")
if top[1].button("↻ Refresh", width="stretch"):
    st.cache_data.clear()

try:
    d = live()
except Exception as err:  # keys missing, live key refused, network down
    st.error(f"Couldn't load the Alpaca paper account: {err}")
    st.stop()

run = latest_run(include_dry_runs=False) or latest_run()  # prefer the run that actually traded
clock = d["clock"]
status = "🟢 Market open" if clock.is_open else f"🔴 Market closed · opens {clock.next_open:%a %b %d, %H:%M} ET"
last = (f"Last run: {run['run_at'][:16].replace('T', ' ')} UTC "
        f"({'preview only, no orders' if run['mode'] == 'dry-run' else 'paper trades'})") if run else "No runs logged yet"
st.caption(f"Paper account (fake money) · {status} · {last}")

# --------------------------------------------------------------------------
# Headline numbers
# --------------------------------------------------------------------------
acct, perf = d["account"], d["performance"]
fund_rows = perf[perf.series == "Trading City"]
bench_rows = perf[perf.series == "VOO"]
fund_days = len(fund_rows)
fund_total = fund_rows["pct"].iloc[-1] if fund_days else 0.0
bench_total = bench_rows["pct"].iloc[-1] if fund_days >= 2 and not bench_rows.empty else None

c = st.columns(4)
c[0].metric("Portfolio value", money(acct["portfolio_value"]))
c[1].metric("Cash", money(acct["cash"]), f"{acct['cash'] / acct['portfolio_value']:.0%} of portfolio", delta_color="off")
c[2].metric("Today", money(acct["today_change"]), f"{acct['today_pct']:+.2%}")
c[3].metric(
    f"Since start vs {d['benchmark']}",
    f"{fund_total:+.2%}",
    "comparison starts after 2 days of history" if bench_total is None
    else f"{fund_total - bench_total:+.2%} vs {d['benchmark']} ({bench_total:+.2%})",
    delta_color="off" if bench_total is None else "normal",
)

# --------------------------------------------------------------------------
# Performance chart
# --------------------------------------------------------------------------
st.subheader(f"Performance vs. {d['benchmark']}")
if fund_days < 2:
    st.info("This chart fills in as the fund runs. It needs at least two trading days of history.")
else:
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False)
    base = alt.Chart(perf).encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("pct:Q", title="Change since start", axis=alt.Axis(format="%")),
        color=alt.Color("series:N", title=None,
                        scale=alt.Scale(domain=["Trading City", "VOO"], range=[FUND_COLOR, BENCH_COLOR]),
                        legend=alt.Legend(orient="top")),
    )
    lines = base.mark_line(strokeWidth=2)
    points = base.mark_circle(size=64).encode(opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    rule = alt.Chart(perf).mark_rule(color="gray", opacity=0.4).encode(
        x="date:T",
        opacity=alt.condition(hover, alt.value(0.4), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("series:N", title=""),
                 alt.Tooltip("pct:Q", title="Change", format="+.2%")],
    ).add_params(hover)
    st.altair_chart((lines + points + rule).properties(height=320), width="stretch")
    with st.expander("Show as a table"):
        st.dataframe(perf.pivot(index="date", columns="series", values="pct").style.format("{:+.2%}"))

# --------------------------------------------------------------------------
# Positions and orders
# --------------------------------------------------------------------------
left, right = st.columns([3, 2])
with left:
    st.subheader("Open positions")
    pos = d["positions"]
    if pos.empty:
        msg = "No positions yet."
        if d["open_orders"]:
            msg += f" {d['open_orders']} order(s) are waiting to fill — see Recent orders."
        st.info(msg)
    else:
        pos = pos.assign(**{"Stop-loss": pos["Stop-loss"].map(money)})
        st.dataframe(
            pos.style.format(na_rep="—", formatter={
                "Avg cost": "${:,.2f}", "Price": "${:,.2f}", "Value": "${:,.2f}",
                "Gain/loss $": "${:+,.2f}", "Gain/loss %": "{:+.2%}", "Weight": "{:.1%}",
            }),
            hide_index=True, width="stretch",
        )
        over = pos[pos["Weight"] > 0.10]
        if not over.empty:
            st.warning(f"Above the 10% position limit after price moves: {', '.join(over['Stock'])}. "
                       "Nothing trims positions automatically yet.")

with right:
    st.subheader("Recent orders")
    orders = d["orders"]
    if orders.empty:
        st.info("No orders yet.")
    else:
        shown = orders.copy()
        shown["Submitted"] = pd.to_datetime(shown["Submitted"]).dt.tz_convert("America/New_York").dt.strftime("%b %d %H:%M")
        for col in ("Fill price", "Stop-loss"):
            shown[col] = shown[col].map(money)
        st.dataframe(shown, hide_index=True, width="stretch")
        st.caption("Times are New York time. 'accepted' means waiting for the market to open.")

# --------------------------------------------------------------------------
# What each agent thought in the latest run
# --------------------------------------------------------------------------
st.subheader("Latest run — what each agent thought")
if not run:
    st.info("No runs yet. Run `python -m trading.run --dry-run` to create one.")
else:
    with st.expander("📈 Market Analyst — signals for each stock", expanded=False):
        sig = pd.DataFrame(run.get("signals", []))
        if not sig.empty:
            table = sig[["ticker", "label", "score", "price", "momentum_12_1", "rsi14", "volatility"]].sort_values("score", ascending=False)
            table.columns = ["Stock", "Signal", "Score", "Price", "12-1 momentum", "RSI", "Volatility"]
            st.dataframe(table.style.format({"Score": "{:+.2f}", "Price": "${:,.2f}", "12-1 momentum": "{:+.1%}",
                                             "RSI": "{:.0f}", "Volatility": "{:.0%}"}, na_rep="—"),
                         hide_index=True, width="stretch")
            for s in sorted(run["signals"], key=lambda s: -s["score"]):
                st.markdown(f"**{s['ticker']}** — {s['explanation']}  \n<small>explained by {s['explained_by']}</small>",
                            unsafe_allow_html=True)

    with st.expander("🧠 Portfolio Manager — buy, sell or hold", expanded=True):
        icon = {"buy": "🟢", "sell": "🔴", "hold": "⚪"}
        for dec in run.get("decisions", []):
            st.markdown(f"{icon.get(dec['action'], '•')} **{dec['ticker']}** — {dec['reason']}")

    with st.expander("🛡️ Risk Manager — checks on each proposed trade", expanded=True):
        reviews = run.get("risk_review", [])
        if not reviews:
            st.write("Nothing was proposed.")
        for r in reviews:
            if r["approved"]:
                head = f"✅ **{r['side'].upper()} {r['qty']} {r['ticker']}** at {money(r['price'])} ({money(r['value'])})"
                if r.get("stop_price"):
                    head += f", stop-loss {money(r['stop_price'])}"
            else:
                head = f"⛔ **{r['side'].upper()} {r['ticker']} blocked**"
            st.markdown(head + "".join(f"\n- {n}" for n in r.get("notes", [])))

    with st.expander("🧯 Stop-loss check — is every position protected?", expanded=False):
        acts = run.get("stop_maintenance")
        if acts is None:
            st.write("This run happened before the stop-loss check existed.")
        elif not acts:
            st.write("No positions to protect yet.")
        for a in acts or []:
            icon = {"ok": "✅", "create": "➕", "replace": "🔧", "exit": "🔴", "skip": "⏭️"}.get(a["action"], "•")
            st.markdown(f"{icon} **{a['ticker']}** — {a['detail']} `{a['status']}`")

    with st.expander("📨 Orders sent this run", expanded=False):
        for o in run.get("orders", []):
            st.markdown(f"`{o['status'].upper()}` {o['side'].upper()} {o['qty']} **{o['ticker']}** — {o['detail']}")
