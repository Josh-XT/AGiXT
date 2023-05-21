import streamlit as st
import os
from Agent import Agent
from Config import Config
from auth_libs.Users import check_auth_status

check_auth_status()

st.title("Manage Learning")

# Initialize session state for stop events and agent status if not exist
if "agent_status" not in st.session_state:
    st.session_state.agent_status = {}

agent_name = st.selectbox(
    "Select Agent",
    options=[""] + [agent["name"] for agent in Config().get_agents()],
    index=0,
)

if agent_name:
    agent = Agent(agent_name)
    st.markdown("## Learn from a file")
    learn_file_upload = st.file_uploader(
        "Upload a file for the agent to learn from",
        type=["txt", "doc", "docx", "pdf", "xls", "xlsx", "png", "jpg", "jpeg"],
    )
    if learn_file_upload is not None:
        learn_file_path = os.path.join("data", "uploaded_files", learn_file_upload.name)
        if not os.path.exists(os.path.dirname(learn_file_path)):
            os.makedirs(os.path.dirname(learn_file_path))
        with open(learn_file_path, "wb") as f:
            f.write(learn_file_upload.getbuffer())
        agent.memories.read_file(learn_file_path)
        st.success(f"Agent '{agent_name}' has learned from the uploaded file.")

    st.markdown("## Learn from a URL")
    learn_url = st.text_input("Enter a URL for the agent to learn from")
    if st.button("Learn from URL"):
        if learn_url:
            _, _ = agent.memories.read_website(learn_url)
            st.success(f"Agent '{agent_name}' has learned from the URL.")

    if st.button("Clear agent memory"):
        agent.wipe_agent_memories(agent_name)
        st.success(f"Memory for agent '{agent_name}' has been cleared.")
