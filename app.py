"""
App entry point — Streamlit multi-page navigation setup only.
No screening logic here; see pages/0_Signal_Screener.py and
pages/1_Momentum_Screener.py for actual page content.

Both pages are file-based (st.Page with a file path, not a callable)
deliberately — mixing a callable-based page with a file-based page was
the suspected cause of filter/result state not persisting when
switching between sidebar pages.

"How this works" is no longer a separate sidebar page (it was, for the
Signal Screener, before this change) — it's now a tab inside each
screener page, via st.tabs(). Sidebar nav is 3 entries (Signal, Momentum, Algo Signals). See
how_it_works.py and each page file's docstring for why.
"""
import streamlit as st

st.set_page_config(page_title="Signal Screener", layout="wide")

if __name__ == "__main__":
    signal_page = st.Page("pages/0_Signal_Screener.py", title="Signal Screener", icon="\U0001F4C8", default=True)
    momentum_page = st.Page("pages/1_Momentum_Screener.py", title="Momentum Screener", icon="\U0001F4C8")
    algo_page = st.Page("pages/2_Algo_Signals.py", title="Algo Signals", icon="\U0001F4C9")
    pg = st.navigation([signal_page, momentum_page, algo_page])
    pg.run()