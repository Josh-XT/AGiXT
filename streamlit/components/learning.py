import streamlit as st
from ApiClient import ApiClient
import os
import base64


def learning_page(agent_name):
    st.markdown("### Choose a Method for Learning")

    if agent_name:
        st.markdown("### Learn from a file")
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
                ApiClient.learn_file(
                    agent_name=agent_name,
                    file_name=learn_file_path,
                    file_content=base64.b64encode(learn_file_upload.read()).decode(
                        "utf-8"
                    ),
                )
                st.success(
                    "Agent '"
                    + agent_name
                    + "' has learned from file: "
                    + learn_file_upload.name
                )

        st.markdown("### Learn from a URL")
        learn_url = st.text_input("Enter a URL for the agent to learn from..")
        if st.button("Learn from URL"):
            if learn_url:
                _, _ = ApiClient.learn_url(agent_name=agent_name, url=learn_url)
                st.success(f"Agent '{agent_name}' has learned from the URL.")
        st.markdown("### Wipe Agent Memory")
        st.markdown(
            "The agent can simply learn too much undesired information at times. If you're having an issue with the context being injected from memory with your agent, try wiping the memory."
        )
        if st.button("Wipe agent memory"):
            ApiClient.wipe_agent_memories(agent_name=agent_name)
            st.success(f"Memory for agent '{agent_name}' has been cleared.")
