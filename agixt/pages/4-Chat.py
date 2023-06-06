import streamlit as st
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
from ApiClient import ApiClient

check_auth_status()
agent_name = agent_selector()


def render_chat_history(chat_container, chat_history):
    chat_container.empty()
    with chat_container:
        for chat in chat_history:
            if "role" in chat and "message" in chat:
                markdown(
                    f'<div style="text-align: left; margin-bottom: 5px;"><strong>{chat["role"]}:</strong> {chat["message"]}</div>',
                    unsafe_allow_html=True,
                )


header("Chat with Agent")

smart_chat_toggle = checkbox("Enable Smart Chat")

st.session_state["chat_history"] = {}

chat_container = container()

if agent_name:
    try:
        st.session_state["chat_history"][agent_name] = ApiClient.get_chat_history(
            agent_name=agent_name
        )
    except:
        st.session_state["chat_history"][
            agent_name
        ] = []  # initialize as an empty list, not a dictionary

    render_chat_history(
        chat_container=chat_container,
        chat_history=st.session_state["chat_history"][agent_name],
    )

    chat_prompt = text_input("Enter your message", key="chat_prompt")
    send_button = button("Send Message")

    if send_button:
        if agent_name and chat_prompt:
            with spinner("Thinking, please wait..."):
                if smart_chat_toggle:
                    response = ApiClient.smartchat(
                        agent_name=agent_name,
                        prompt=chat_prompt,
                        shots=3,
                    )
                else:
                    response = ApiClient.chat(agent_name=agent_name, prompt=chat_prompt)
            chat_entry = [
                {"role": "USER", "message": chat_prompt},
                {"role": agent_name, "message": response},
            ]
            st.session_state["chat_history"][agent_name].extend(chat_entry)
            render_chat_history(
                chat_container=chat_container,
                chat_history=st.session_state["chat_history"][agent_name],
            )
        else:
            error("Agent name and message are required.")
else:
    warning("Please select an agent to start chatting.")
