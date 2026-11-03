"""One shared, 60-second cache of the live Alpaca data for every dashboard page."""
import streamlit as st

from dashboard.data import load_live


@st.cache_data(ttl=60, show_spinner="Loading your paper account…")
def live():
    return load_live()
