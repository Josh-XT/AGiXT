import streamlit as st
import os
import asyncio
from auth_libs.Users import check_auth_status
from components.agent_selector import agent_selector

check_auth_status()

agent_name, agent = agent_selector()

st.title("Manage Learning")

# Initialize session state for stop events and agent status if not exist
if "agent_status" not in st.session_state:
    st.session_state.agent_status = {}

if agent_name:
    st.markdown("## Learn from a file")
    learn_file_upload = st.file_uploader(
        "Upload a file for the agent to learn from.", accept_multiple_files=True
    )
    if learn_file_upload is not None:
        for learn_file_upload in learn_file_upload.copy():
            learn_file_path = os.path.join(
                "data", "uploaded_files", learn_file_upload.name
            )
            if not os.path.exists(os.path.dirname(learn_file_path)):
                os.makedirs(os.path.dirname(learn_file_path))
            with open(learn_file_path, "wb") as f:
                f.write(learn_file_upload.getbuffer())
            asyncio.run(agent.memories.mem_read_file(learn_file_path))
            st.success(
                "Agent '"
                + agent_name
                + "' has learned from file: "
                + learn_file_upload.name
            )

    st.markdown("## Learn from a URL")
    learn_url = st.text_input("Enter a URL for the agent to learn from..")
    if st.button("Learn from URL"):
        if learn_url:
            _, _ = asyncio.run(agent.memories.read_website(learn_url))
            st.success(f"Agent '{agent_name}' has learned from the URL.")
    st.markdown("## Wipe Agent Memory")
    st.markdown(
        "The agent can simply learn too much undesired information at times. If you're having an issue with the context being injected from memory with your agent, try wiping the memory."
    )
    if st.button("Wipe agent memory"):
        agent.wipe_agent_memories(agent_name)
        st.success(f"Memory for agent '{agent_name}' has been cleared.")
