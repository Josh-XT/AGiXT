# Main.py
import streamlit as st
from components.agent_selector import agent_selector

st.set_page_config(
    page_title="AGiXT",
    page_icon=":robot:",
    layout="wide",
    initial_sidebar_state="expanded",
)
agent_name, agent = agent_selector()
st.markdown(
    """
    <img src="https://josh-xt.github.io/AGiXT/images/AGiXT.svg" width="100%">
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
