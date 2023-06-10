import streamlit as st
from components.verify_backend import verify_backend
from components.docs import agixt_docs
from streamlit_autorefresh import st_autorefresh


st.set_page_config(
    page_title="AGiXT",
    page_icon=":robot:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Run the autorefresh about (5 seconds) and stop running in the corner after the 2nd time
count = st_autorefresh(interval=5000, limit=2)


try:
    with open("./.streamlit/config.toml") as f:
        if "Dark" in f.read():
            light_theme = False
except:
    light_theme = False


agixt_docs()
if light_theme == True:
    st.markdown(
        """
        <div style="text-align: center;">
        <img src="https://josh-xt.github.io/AGiXT/images/AGiXT-gradient-flat.svg" width="65%">
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"""
        <div style="text-align: center;">
        <img src="https://josh-xt.github.io/AGiXT/images/AGiXT-gradient-light.svg" width="65%">
        </div>
        """,
        unsafe_allow_html=True,
    )


if not verify_backend():
    verify_backend()
