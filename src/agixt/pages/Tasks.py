import streamlit as st
import os
import threading
from AGiXT import AGiXT
from Config import Config
from Config.Agent import Agent

st.header("Manage Tasks")

# Check if the user is logged in
if not st.session_state.get("logged_in"):
    # Redirect to the login page using JavaScript
    redirect_code = """
        <script>
            window.location.href = window.location.origin + "/Login"
        </script>
    """
    st.markdown(redirect_code, unsafe_allow_html=True)


def logout_button():
    """
    Renders the logout button.
    """
    if st.button("Logout"):
        # Clear session state and redirect to the login page
        st.session_state.clear()
        st.experimental_rerun()  # Redirect to the login page


logout_button()

# initialize session state for stop events and agent status if not exist
if "agent_stop_events" not in st.session_state:
    st.session_state.agent_stop_events = {}

if "agent_status" not in st.session_state:
    st.session_state.agent_status = {}

agent_name = st.selectbox(
    "Select Agent",
    options=[""] + [agent["name"] for agent in Config().get_agents()],
    index=0,
)

if agent_name:
    task_objective = st.text_area("Enter the task objective")
    learn_file_upload = st.file_uploader("Upload a file to learn from")
    learn_file_path = ""
    if learn_file_upload is not None:
        if not os.path.exists(os.path.join("data", "uploaded_files")):
            os.makedirs(os.path.join("data", "uploaded_files"))
        learn_file_path = os.path.join("data", "uploaded_files", learn_file_upload.name)
        with open(learn_file_path, "wb") as f:
            f.write(learn_file_upload.getbuffer())
    CFG = Agent(agent_name)

    col1, col2 = st.columns([3, 1])
    with col1:
        columns = st.columns([3, 2])
        agent_status = st.session_state.agent_status.get(agent_name, "Not Running")

        if agent_status == "Not Running":
            if st.button("Start Task"):
                if agent_name and task_objective:
                    if agent_name not in CFG.agent_instances:
                        CFG.agent_instances[agent_name] = AGiXT(agent_name)
                    stop_event = threading.Event()
                    st.session_state.agent_stop_events[agent_name] = stop_event
                    agent_thread = threading.Thread(
                        target=CFG.agent_instances[agent_name].run_task,
                        args=(stop_event, task_objective, True, learn_file_path),
                    )
                    agent_thread.start()
                    st.session_state.agent_status[agent_name] = "Running"
                    columns[0].success(f"Task started for agent '{agent_name}'.")
                else:
                    columns[0].error("Agent name and task objective are required.")
        else:  # agent_status == "Running"
            if st.button("Stop Task"):
                if agent_name in st.session_state.agent_stop_events:
                    st.session_state.agent_stop_events[agent_name].set()
                    del st.session_state.agent_stop_events[agent_name]
                    st.session_state.agent_status[agent_name] = "Not Running"
                    columns[0].success(f"Task stopped for agent '{agent_name}'.")
                else:
                    columns[0].error("No task is running for the selected agent.")

    with col2:
        st.markdown(f"**Status:** {agent_status}")
