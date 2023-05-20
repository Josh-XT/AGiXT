import streamlit as st

st.set_page_config(
    page_title="AGiXT",
    page_icon=":robot:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <iframe src="https://josh-xt.github.io/AGiXT/" width="100%" height="500">
    </iframe>
    """,
    unsafe_allow_html=True,
)
