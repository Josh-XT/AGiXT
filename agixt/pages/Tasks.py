import streamlit as st
import os
from Tasks import Tasks
from Config import Config
from Agent import Agent
from auth_libs.Users import check_auth_status
from pathlib import Path

check_auth_status()


st.title("Manage Tasks")

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
    agent = Agent(agent_name)
    task_objective = st.text_area("Enter the task objective")
    learn_file_upload = st.file_uploader("Upload a file to learn from")
    learn_file_path = ""
    if learn_file_upload is not None:
        if not os.path.exists(os.path.join("data", "uploaded_files")):
            os.makedirs(os.path.join("data", "uploaded_files"))
        learn_file_path = os.path.join("data", "uploaded_files", learn_file_upload.name)
        with open(learn_file_path, "wb") as f:
            f.write(learn_file_upload.getbuffer())

    task_list_dir = Path(f"agents/{agent_name}")
    task_list_dir.mkdir(parents=True, exist_ok=True)
    existing_tasks = [
        f.stem for f in task_list_dir.glob("*.json") if f.stem != "config"
    ]

    load_task = st.selectbox(
        "Load Task",
        options=[""] + existing_tasks,
        index=0,
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        columns = st.columns([3, 2])
        agent_status = st.session_state.agent_status.get(agent_name, "Not Running")

        if agent_status == "Not Running":
            if st.button("Start Task", key=f"start_{agent_name}"):
                if agent_name and (task_objective or load_task):
                    if agent_name not in agent.agent_instances:
                        agent.agent_instances[agent_name] = Tasks(agent_name)

                    agent.agent_instances[agent_name].run_task(
                        task_objective,
                        True,
                        learn_file_path,
                        load_task,
                    )
                    st.session_state.agent_status[agent_name] = "Running"
                    agent_status = "Running"
                    columns[0].success(f"Task started for agent '{agent_name}'.")
                else:
                    columns[0].error("Agent name and task objective are required.")
        else:  # agent_status == "Running"
            if st.button("Stop Task", key=f"stop_{agent_name}"):
                if agent_name in agent.agent_instances:
                    agent.agent_instances[agent_name].stop_tasks()
                    st.session_state.agent_status[agent_name] = "Not Running"
                    agent_status = "Not Running"
                    columns[0].success(f"Task stopped for agent '{agent_name}'.")
                else:
                    columns[0].error("No task is running for the selected agent.")

    with col2:
        st.markdown(f"**Status:** {agent_status}")
