import streamlit as st
import os
from AGiXT import AGiXT
from Config import Config
from Agent import Agent
from streamlit import (
    markdown,
    header,
    selectbox,
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

check_auth_status()
CFG = Config()


def render_chat_history(chat_container, chat_history):
    chat_container.empty()
    with chat_container:
        for chat in chat_history:
            if "sender" in chat and "message" in chat:
                if chat["sender"] == "User":
                    markdown(
                        f'<div style="text-align: left; margin-bottom: 5px;"><strong>User:</strong> {chat["message"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    markdown(
                        f'<div style="text-align: left; margin-bottom: 5px;"><strong>Agent:</strong> {chat["message"]}</div>',
                        unsafe_allow_html=True,
                    )


header("Chat with Agent")

agent_name = selectbox(
    "Select Agent",
    options=[""] + [agent["name"] for agent in CFG.get_agents()],
    index=0,
)

smart_chat_toggle = checkbox("Enable Smart Chat")

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = {}

chat_container = container()

if agent_name:
    learn_file_upload = file_uploader("Upload a file to learn from")
    learn_file_path = ""
    if learn_file_upload is not None:
        if not os.path.exists(os.path.join("data", "uploaded_files")):
            os.makedirs(os.path.join("data", "uploaded_files"))
        learn_file_path = os.path.join("data", "uploaded_files", learn_file_upload.name)
        with open(learn_file_path, "wb") as f:
            f.write(learn_file_upload.getbuffer())

    try:
        st.session_state.chat_history[agent_name] = Agent(agent_name).get_chat_history(
            agent_name
        )
    except:
        st.session_state.chat_history[agent_name] = {}

    render_chat_history(chat_container, st.session_state.chat_history[agent_name])

    chat_prompt = text_input("Enter your message", key="chat_prompt")
    send_button = button("Send Message")

    if send_button:
        if agent_name and chat_prompt:
            with spinner("Thinking, please wait..."):
                agent = AGiXT(agent_name)
                if smart_chat_toggle:
                    response = agent.smart_chat(
                        chat_prompt,
                        shots=3,
                        async_exec=True,
                        learn_file=learn_file_path,
                    )
                else:
                    response = agent.run(
                        chat_prompt,
                        prompt="Chat",
                        context_results=6,
                        learn_file=learn_file_path,
                    )
            chat_entry = [
                {"sender": "User", "message": chat_prompt},
                {"sender": "Agent", "message": response},
            ]
            st.session_state.chat_history[agent_name].extend(chat_entry)
            render_chat_history(
                chat_container, st.session_state.chat_history[agent_name]
            )
        else:
            error("Agent name and message are required.")
else:
    warning("Please select an agent to start chatting.")
