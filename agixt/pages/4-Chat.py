import streamlit as st
from auth_libs.Users import check_auth_status
from components.agent_selector import agent_selector
from ApiClient import ApiClient

st.set_page_config(
    page_title="Chat",
    page_icon=":speech_balloon:",
    layout="wide",
)

check_auth_status()
agent_name = agent_selector()

def render_chat_history(chat_container, chat_history):
    chat_container.empty()
    with chat_container:
        for chat in chat_history:
            if "role" in chat and "message" in chat:
                st.markdown(
                    f'<div style="text-align: left; margin-bottom: 5px;"><strong>{chat["role"]}:</strong> {chat["message"]}</div>',
                    unsafe_allow_html=True,
                )

st.title(":speech_balloon: Chat with Agent")
smart_chat_toggle = st.checkbox("Enable Smart Chat")
st.session_state["chat_history"] = {}

chat_container = st.container()

if agent_name:
    try:
        st.session_state["chat_history"][agent_name] = ApiClient.get_chat_history(
            agent_name=agent_name
        )
    except:
        st.session_state["chat_history"][agent_name] = []

    with st.container():
        st.write(
            f'<div style="width: 80%;">',
            unsafe_allow_html=True,
        )
        render_chat_history(
            chat_container=chat_container,
            chat_history=st.session_state["chat_history"][agent_name],
        )

    st.write("---")
    chat_prompt = st.text_input("Enter your message", key="chat_prompt")
    send_button = st.button("Send Message")

    if send_button:
        if agent_name and chat_prompt:
            with st.spinner("Thinking, please wait..."):
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
            with st.container():
                st.write(
                    f'<div style="width: 80%;">',
                    unsafe_allow_html=True,
                )
                render_chat_history(
                    chat_container=chat_container,
                    chat_history=st.session_state["chat_history"][agent_name],
                )
        else:
            st.error("Agent name and message are required.")
else:
    st.warning("Please select an agent to start chatting.")