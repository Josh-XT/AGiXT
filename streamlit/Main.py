# Main.py
import streamlit as st
from components.agent_selector import agent_selector

from components.verify_backend import verify_backend

verify_backend()

with open('./.streamlit/config.toml') as f:
    if 'Dark' in f.read():
        light_theme = False

st.set_page_config(
    page_title="AGiXT",
    page_icon=":robot:",
    layout="wide",
    initial_sidebar_state="expanded",
)


if light_theme == True:
    st.markdown(
        """
        <div style="text-align: center;">
        <center><img src="https://josh-xt.github.io/AGiXT/images/AGiXT.svg" width="65%"></center>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
        <div style="text-align: center;">
        <img src="https://josh-xt.github.io/AGiXT/images/AGiXTwhiteborder.svg" width="65%">
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("## Useful Links")
st.markdown(
    """
- [AGiXT Documentation](https://josh-xt.github.io/AGiXT/)
- [AGiXT GitHub](https://github.com/Josh-XT/AGiXT)
- [AGiXT Discord](https://discord.gg/d3TkHRZcjD)"""
)
