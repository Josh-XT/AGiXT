import streamlit as st
from Tasks import Tasks
from auth_libs.Users import check_auth_status
from pathlib import Path
from components.agent_selector import agent_selector

check_auth_status()

agent_name, agent = agent_selector()
st.title("Manage Tasks")

# initialize session state for stop events and agent status if not exist
if "agent_stop_events" not in st.session_state:
    st.session_state.agent_stop_events = {}

if "agent_status" not in st.session_state:
    st.session_state.agent_status = {}

if agent_name:
    smart_task_toggle = st.checkbox("Enable Smart Task")
    task_objective = st.text_area("Enter the task objective")
    task_agent = Tasks(agent_name)
    status = task_agent.get_status()
    if status == True:
        st.session_state.agent_status[agent_name] = "Running"
    else:
        st.session_state.agent_status[agent_name] = "Not Running"
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
                        agent.agent_instances[agent_name] = task_agent

                    task_agent.run_task(
                        objective=task_objective,
                        async_exec=True,
                        smart=smart_task_toggle,
                        load_task=load_task,
                    )

                    st.session_state.agent_status[agent_name] = "Running"
                    agent_status = "Running"
                    columns[0].success(f"Task started for agent '{agent_name}'.")
                else:
                    columns[0].error("Agent name and task objective are required.")
        else:  # agent_status == "Running"
            if st.button("Stop Task", key=f"stop_{agent_name}"):
                if agent_name in agent.agent_instances:
                    task_agent.stop_tasks()
                    st.session_state.agent_status[agent_name] = "Not Running"
                    agent_status = "Not Running"
                    columns[0].success(f"Task stopped for agent '{agent_name}'.")
                else:
                    columns[0].error("No task is running for the selected agent.")

    with col2:
        st.markdown(f"**Status:** {agent_status}")
