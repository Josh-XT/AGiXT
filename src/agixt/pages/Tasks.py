import streamlit as st
import os
import threading
from AGiXT import AGiXT
from Config import Config
from Config.Agent import Agent

# Check if the user is logged in
if not st.session_state.get("logged_in"):
    # Redirect to the login page using JavaScript
    redirect_code = '''
        <script>
            window.location.href = window.location.origin + "/Login"
        </script>
    '''
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

st.header("Manage Tasks")
agent_stop_events = {}
agent_name = st.selectbox(
    "Select Agent",
    options=[""] + [agent["name"] for agent in Config().get_agents()],
    index=0,
)
task_objective = st.text_area("Enter the task objective")

if agent_name:
    learn_file_upload = st.file_uploader("Upload a file to learn from")
    learn_file_path = ""
    if learn_file_upload is not None:
        if not os.path.exists(os.path.join("data", "uploaded_files")):
            os.makedirs(os.path.join("data", "uploaded_files"))
        learn_file_path = os.path.join("data", "uploaded_files", learn_file_upload.name)
        with open(learn_file_path, "wb") as f:
            f.write(learn_file_upload.getbuffer())
    CFG = Agent(agent_name)
    agent_status = "Not Running"
    if agent_name in agent_stop_events:
        agent_status = "Running"

    col1, col2 = st.columns([3, 1])
    with col1:
        columns = st.columns([3, 2])
        if st.button("Start Task"):
            if agent_name and task_objective:
                if agent_name not in CFG.agent_instances:
                    CFG.agent_instances[agent_name] = AGiXT(agent_name)
                stop_event = threading.Event()
                agent_stop_events[agent_name] = stop_event
                agent_thread = threading.Thread(
                    target=CFG.agent_instances[agent_name].run_task,
                    args=(stop_event, task_objective, True, learn_file_path),
                )
                agent_thread.start()
                agent_status = "Running"
                columns[0].success(f"Task started for agent '{agent_name}'.")
            else:
                columns[0].error("Agent name and task objective are required.")

        if st.button("Stop Task"):
            if agent_name in agent_stop_events:
                agent_stop_events[agent_name].set()
                del agent_stop_events[agent_name]
                agent_status = "Not Running"
                columns[0].success(f"Task stopped for agent '{agent_name}'.")
            else:
                columns[0].error("No task is running for the selected agent.")

    with col2:
        st.markdown(f"**Status:** {agent_status}")
