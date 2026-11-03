"""Trading City dashboard.

Open it with:
    streamlit run dashboard/app.py
Then visit the address it prints (usually http://localhost:8501).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `config`, `data`, ... import

import streamlit as st

st.set_page_config(page_title="Trading City", page_icon="🏙️", layout="wide")

here = Path(__file__).parent
st.navigation([
    st.Page(here / "overview.py", title="Overview", icon="📊", default=True),
    st.Page(here / "city_page.py", title="City", icon="🏙️", url_path="city"),
]).run()
