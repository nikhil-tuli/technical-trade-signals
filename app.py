"""
App entry point — Streamlit multi-page navigation setup only.
No screening logic here; see pages/0_Signal_Screener.py and
pages/1_How_This_Works.py for actual page content.

Both pages are file-based (st.Page with a file path, not a callable)
deliberately — mixing a callable-based page with a file-based page was
the suspected cause of filter/result state not persisting when
switching between sidebar pages.
"""
import streamlit as st

st.set_page_config(page_title="Signal Screener", layout="wide")

if __name__ == "__main__":
    screener_page = st.Page("pages/0_Signal_Screener.py", title="Signal Screener", icon="\U0001F4C8", default=True)
    how_it_works_page = st.Page("pages/1_How_This_Works.py", title="How This Works", icon="\U0001F4D8")
    pg = st.navigation([screener_page, how_it_works_page])
    pg.run()