import streamlit as st
import threading
import json
from Config import Config
from AgentLLM import AgentLLM
from Config.Agent import Agent
from Chain import Chain
from CustomPrompt import CustomPrompt

CFG = Config()

st.set_page_config(
    page_title="Agent-LLM",
    page_icon=":robot:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("Agent-LLM")
st.sidebar.markdown("An AI Automation Platform for creating and managing AI agents.")
st.sidebar.markdown("---")

agent_stop_events = {}

main_selection = st.sidebar.selectbox(
    "Select a feature",
    [
        "Agent Settings",
        "Chat",
        "Instructions",
        "Tasks",
        "Chains",
        "Custom Prompts",
    ],
)

if main_selection == "Agent Settings":
    st.header("Manage Agent Settings")

    agent_name = st.selectbox("Select Agent", [""] + CFG.get_agents())
    agent_settings = st.text_area("Custom Settings (JSON format)", height=300)

    if st.button("Update Agent Settings"):
        if agent_name and agent_settings:
            try:
                settings = json.loads(agent_settings)
                Agent(agent_name).update_agent_config(settings, "settings")
                st.success(f"Agent '{agent_name}' updated.")
            except Exception as e:
                st.error(f"Error updating agent: {str(e)}")
        else:
            st.error("Agent name and settings are required.")

elif main_selection == "Chat":
    st.header("Chat with Agent")

    agent_name = st.selectbox("Select Agent", [""] + CFG.get_agents())
    chat_prompt = st.text_area("Enter your chat prompt")
    smart_chat_toggle = st.checkbox("Enable Smart Chat")

    if st.button("Start Chat"):
        if agent_name and chat_prompt:
            agent = AgentLLM(agent_name)
            if smart_chat_toggle:
                response = agent.smart_chat(chat_prompt, shots=3)
            else:
                response = agent.run(chat_prompt, prompt="Chat", context_results=6)
            st.markdown(f"**Response:** {response}")
        else:
            st.error("Agent name and chat prompt are required.")

elif main_selection == "Instructions":
    st.header("Instruct Agent")

    agent_name = st.selectbox("Select Agent", [""] + CFG.get_agents())
    instruct_prompt = st.text_area("Enter your instruction")
    smart_instruct_toggle = st.checkbox("Enable Smart Instruct")

    if st.button("Give Instruction"):
        if agent_name and instruct_prompt:
            agent = AgentLLM(agent_name)
            if smart_instruct_toggle:
                response = agent.smart_instruct(task=instruct_prompt, shots=3)
            else:
                response = agent.run(task=instruct_prompt, prompt="instruct")
            st.markdown(f"**Response:** {response}")
        else:
            st.error("Agent name and instruction are required.")

elif main_selection == "Tasks":
    st.header("Manage Tasks")

    agent_name = st.selectbox("Select Agent", [""] + CFG.get_agents())
    task_objective = st.text_area("Enter the task objective")
    agent_status = "Not Running"

    if agent_name in agent_stop_events:
        agent_status = "Running"

    st.markdown(f"**Status:** {agent_status}")

    if st.button("Start Task"):
        if agent_name and task_objective:
            if agent_name not in CFG.agent_instances:
                CFG.agent_instances[agent_name] = AgentLLM(agent_name)
            stop_event = threading.Event()
            agent_stop_events[agent_name] = stop_event
            agent_thread = threading.Thread(
                target=CFG.agent_instances[agent_name].run_task,
                args=(stop_event, task_objective),
            )
            agent_thread.start()
            st.success(f"Task started for agent '{agent_name}'.")
        else:
            st.error("Agent name and task objective are required.")

    if st.button("Stop Task"):
        if agent_name in agent_stop_events:
            agent_stop_events[agent_name].set()
            del agent_stop_events[agent_name]
            st.success(f"Task stopped for agent '{agent_name}'.")
        else:
            st.error("No task is running for the selected agent.")

elif main_selection == "Chains":
    st.header("Manage Chains")

    chain_name = st.text_input("Chain Name")
    chain_action = st.selectbox("Action", ["Create Chain", "Delete Chain"])

    if st.button("Perform Action"):
        if chain_name:
            if chain_action == "Create Chain":
                Chain().add_chain(chain_name)
                st.success(f"Chain '{chain_name}' created.")
            elif chain_action == "Delete Chain":
                Chain().delete_chain(chain_name)
                st.success(f"Chain '{chain_name}' deleted.")
        else:
            st.error("Chain name is required.")

elif main_selection == "Custom Prompts":
    st.header("Manage Custom Prompts")

    prompt_name = st.text_input("Prompt Name")
    prompt_content = st.text_area("Prompt Content")
    prompt_action = st.selectbox(
        "Action", ["Add Prompt", "Update Prompt", "Delete Prompt"]
    )

    if st.button("Perform Action"):
        if prompt_name and prompt_content:
            custom_prompt = CustomPrompt()
            if prompt_action == "Add Prompt":
                custom_prompt.add_prompt(prompt_name, prompt_content)
                st.success(f"Prompt '{prompt_name}' added.")
            elif prompt_action == "Update Prompt":
                custom_prompt.update_prompt(prompt_name, prompt_content)
                st.success(f"Prompt '{prompt_name}' updated.")
            elif prompt_action == "Delete Prompt":
                custom_prompt.delete_prompt(prompt_name)
                st.success(f"Prompt '{prompt_name}' deleted.")
        else:
            st.error("Prompt name and content are required.")
