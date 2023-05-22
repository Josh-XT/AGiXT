import streamlit as st
from AGiXT import AGiXT
from streamlit import (
    markdown,
    header,
    checkbox,
    container,
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

smart_chat_toggle = checkbox("Enable Smart Chat")

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = {}

chat_container = container()

if agent_name:
    try:
        st.session_state.chat_history[agent_name] = agent.get_chat_history(agent_name)
    except:
        st.session_state.chat_history[
            agent_name
        ] = []  # initialize as an empty list, not a dictionary

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
                    )
                else:
                    response = agent.run(
                        chat_prompt,
                        prompt="Chat",
                        context_results=6,
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
