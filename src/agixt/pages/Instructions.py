import streamlit as st
import auth_libs.Redirect as redir
import os
from AGiXT import AGiXT
from Config import Config
from Config.Agent import Agent
from auth_libs.Cfig import Cfig
import os

CFG = Config()
CFIG = Cfig()
CONFIG_FILE = "config.yaml"

# Check if the user is logged in
if (
    not st.session_state.get("logged_in")
    and os.path.exists(CONFIG_FILE)
    and (CFIG.load_config()["auth_setup"] == "True")
):
    # Redirect to the login page if not
    redir.nav_page("Login")


def logout_button():
    """
    Renders the logout button.
    """
    if st.button("Logout"):
        # Clear session state and redirect to the login page
        st.session_state.clear()
        st.experimental_rerun()  # Redirect to the login page


if (
    not CFIG.load_config()["auth_setup_config"] == "No Login"
    and CFIG.load_config()["auth_setup"] != False
):
    logout_button()


def render_history(instruct_container, chat_history):
    instruct_container.empty()
    with instruct_container:
        for instruct in chat_history:
            if "sender" in instruct and "message" in instruct:
                if instruct["sender"] == "User":
                    st.markdown(
                        f'<div style="text-align: left; margin-bottom: 5px;"><strong>User:</strong> {instruct["message"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="text-align: left; margin-bottom: 5px;"><strong>Agent:</strong> {instruct["message"]}</div>',
                        unsafe_allow_html=True,
                    )


st.header("Instruct an Agent")

agent_name = st.selectbox(
    "Select Agent",
    options=[""] + [agent["name"] for agent in CFG.get_agents()],
    index=0,
)

smart_instruct_toggle = st.checkbox("Enable Smart Instruct")

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = {}

instruct_container = st.container()

if agent_name:
    learn_file_upload = st.file_uploader("Upload a file to learn from")
    learn_file_path = ""
    if learn_file_upload is not None:
        if not os.path.exists(os.path.join("data", "uploaded_files")):
            os.makedirs(os.path.join("data", "uploaded_files"))
        learn_file_path = os.path.join("data", "uploaded_files", learn_file_upload.name)
        with open(learn_file_path, "wb") as f:
            f.write(learn_file_upload.getbuffer())

    try:
        chat_history = Agent(agent_name).get_chat_history(agent_name)
    except:
        chat_history = []
    st.session_state.chat_history[agent_name] = chat_history

    render_history(instruct_container, st.session_state.chat_history[agent_name])

    instruct_prompt = st.text_input("Enter your message", key="instruct_prompt")
    send_button = st.button("Send Message")

    if send_button:
        if agent_name and instruct_prompt:
            with st.spinner("Thinking, please wait..."):
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
                        prompt="Instruct",
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
            st.error("Agent name and message are required.")
else:
    st.warning("Please select an agent to start instructting.")
