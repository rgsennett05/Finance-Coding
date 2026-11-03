"""City page: the 3D view of the fund's agents and stocks.

Live: the page refreshes every minute while the market is open (every 10 minutes when it's
closed) and redraws the city when anything changed: live prices, a new run, an order filled.
The city remembers the camera, so a refresh doesn't move your view.
"""
import hashlib
import json

import streamlit as st
import streamlit.components.v1 as components

from config.settings import load_settings
from dashboard.city_data import city_state, render
from dashboard.data import latest_run
from dashboard.live_cache import live

top = st.columns([4, 1])
top[0].title("🏙️ The City")
if top[1].button("↻ Refresh", width="stretch"):
    st.cache_data.clear()
st.caption("Live: tower labels show each stock's latest price and today's change. The sky follows the real time "
           "in New York, and the streets get busier when the fund is. Press ▶ to replay the latest run, drag to look "
           "around, tap a building for its reasoning.")


def fingerprint(state: dict) -> str:
    """What should trigger a redraw: live prices, the run, positions, orders."""
    key = {
        "run": state["run"],
        "stocks": [(s["ticker"], s["shares"], s["pending"], round(s["price"] or 0, 2)) for s in state["stocks"]],
        "trades": [(t["ticker"], t["status"]) for t in state["trades"]],
    }
    return hashlib.sha1(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()


try:
    _open = bool(live()["clock"].is_open)
except Exception:
    _open = False


@st.fragment(run_every="60s" if _open else "600s")
def city():
    settings = load_settings()
    try:
        data = live()
    except Exception as err:
        st.warning(f"Couldn't reach the Alpaca paper account ({err}). Showing the latest run only.")
        data = None
    state = city_state(latest_run(include_dry_runs=False) or latest_run(), data, settings.tickers, settings.benchmark)
    fp = fingerprint(state)
    if st.session_state.get("city_fp") != fp:
        st.session_state["city_fp"] = fp
        st.session_state["city_html"] = render(state)
    components.html(st.session_state["city_html"], height=780, scrolling=False)


city()
