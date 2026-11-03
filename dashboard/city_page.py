"""City page: the 3D view of the fund's agents and stocks."""
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
st.caption("Each agent is a building; each stock is a tower in the Market District. "
           "Press ▶ to replay the latest run, drag to look around, click a building for its reasoning.")

settings = load_settings()
try:
    data = live()
except Exception as err:
    st.warning(f"Couldn't reach the Alpaca paper account ({err}). Showing the latest run only.")
    data = None

state = city_state(latest_run(), data, settings.tickers, settings.benchmark)
components.html(render(state), height=760, scrolling=False)
