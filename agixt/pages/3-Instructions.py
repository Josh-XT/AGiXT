import streamlit as st
import os
from AGiXT import AGiXT
from Agent import Agent
from streamlit import (
    markdown,
    header,
    checkbox,
    container,
    file_uploader,
    text_input,
    button,
    spinner,
    error,
    warning,
)

from auth_libs.Users import check_auth_status
from components.agent_selector import agent_selector

check_auth_status()
agent_name, agent = agent_selector()


def render_history(instruct_container, chat_history):
    instruct_container.empty()
    with instruct_container:
        for instruct in chat_history:
            if "sender" in instruct and "message" in instruct:
                if instruct["sender"] == "User":
                    markdown(
                        f'<div style="text-align: left; margin-bottom: 5px;"><strong>User:</strong> {instruct["message"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    markdown(
                        f'<div style="text-align: left; margin-bottom: 5px;"><strong>Agent:</strong> {instruct["message"]}</div>',
                        unsafe_allow_html=True,
                    )


header("Instruct an Agent")

smart_instruct_toggle = checkbox("Enable Smart Instruct")

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = {}

instruct_container = container()

if agent_name:
    learn_file_upload = file_uploader("Upload a file to learn from")
    learn_file_path = ""
    agent = Agent(agent_name)
    if learn_file_upload is not None:
        if not os.path.exists(os.path.join("data", "uploaded_files")):
            os.makedirs(os.path.join("data", "uploaded_files"))
        learn_file_path = os.path.join("data", "uploaded_files", learn_file_upload.name)
        with open(learn_file_path, "wb") as f:
            f.write(learn_file_upload.getbuffer())

    try:
        st.session_state.chat_history[agent_name] = agent.get_chat_history(agent_name)
    except:
        st.session_state.chat_history[agent_name] = {}

    render_history(instruct_container, st.session_state.chat_history[agent_name])

    instruct_prompt = text_input("Enter your message", key="instruct_prompt")
    send_button = button("Send Message")

    if send_button:
        if agent_name and instruct_prompt:
            with spinner("Thinking, please wait..."):
                agent = AGiXT(agent_name)
                if smart_instruct_toggle:
                    response = agent.smart_instruct(
                        instruct_prompt,
                        shots=3,
                        async_exec=True,
                        learn_file=learn_file_path,
                    )
                else:
                    response = agent.run(
                        instruct_prompt,
                        prompt="instruct",
                        context_results=6,
                        learn_file=learn_file_path,
                    )
            instruct_entry = [
                {"sender": "User", "message": instruct_prompt},
                {"sender": "Agent", "message": response},
            ]
            st.session_state.chat_history[agent_name].extend(instruct_entry)
            render_history(
                instruct_container,
                st.session_state.chat_history[agent_name],
            )
        else:
            error("Agent name and message are required.")
else:
    warning("Please select an agent to start instructting.")
