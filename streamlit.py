import streamlit as st
import threading
import json
from Config import Config
from AgentLLM import AgentLLM
from Config.Agent import Agent
from Chain import Chain
from CustomPrompt import CustomPrompt
from provider import get_provider_options
from Embedding import get_embedding_providers
from Commands import Commands

CFG = Config()

st.set_page_config(
    page_title="Agent-LLM",
    page_icon=":robot:",
    layout="wide",
    initial_sidebar_state="expanded",
)

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


def render_provider_settings(agent_settings, provider_name: str):
    try:
        required_settings = get_provider_options(provider_name)
    except (TypeError, ValueError):
        st.error(
            f"Error loading provider settings: expected a list, but got {required_settings}"
        )
        return {}
    rendered_settings = {}

    if not isinstance(required_settings, list):
        st.error(
            f"Error loading provider settings: expected a list, but got {required_settings}"
        )
        return rendered_settings

    for key in required_settings:
        if key in agent_settings:
            default_value = agent_settings[key]
        else:
            default_value = None

        user_val = st.text_input(key, value=default_value)
        rendered_settings[key] = user_val

    return rendered_settings


if main_selection == "Agent Settings":
    st.header("Manage Agent Settings")

    agent_name = st.selectbox(
        "Select Agent", [""] + [agent["name"] for agent in CFG.get_agents()]
    )

    if agent_name:
        try:
            agent_config = Agent(agent_name).get_agent_config()
            agent_settings = agent_config.get("settings", {})
            provider_name = agent_settings.get("provider", "")
            provider_name = st.selectbox(
                "Select Provider",
                CFG.get_providers(),
                index=CFG.get_providers().index(provider_name)
                if provider_name in CFG.get_providers()
                else 0,
            )
            embedder_name = agent_settings.get("embedder", "")
            embedding_provider_name = st.selectbox(
                "Select Embedding Provider",
                get_embedding_providers(),
                index=get_embedding_providers().index(embedder_name)
                if embedder_name in get_embedding_providers()
                else 0,
            )
            if embedding_provider_name:
                agent_settings["embedder"] = embedding_provider_name
            if provider_name:
                provider_settings = render_provider_settings(
                    agent_settings, provider_name
                )
                agent_settings.update(provider_settings)

            st.subheader("Custom Settings")
            custom_settings = agent_settings.get("custom_settings", [])

            custom_settings_list = st.session_state.get("custom_settings_list", None)
            if custom_settings_list is None:
                if not custom_settings:
                    custom_settings = [""]
                st.session_state.custom_settings_list = custom_settings.copy()

            custom_settings_container = st.container()
            with custom_settings_container:
                for i, custom_setting in enumerate(
                    st.session_state.custom_settings_list
                ):
                    key, value = (
                        custom_setting.split(":", 1)
                        if ":" in custom_setting
                        else (custom_setting, "")
                    )
                    col1, col2 = st.columns(
                        [0.5, 0.5]
                    )  # Add columns for side by side input
                    with col1:
                        new_key = st.text_input(
                            f"Custom Setting {i + 1} Key",
                            value=key,
                            key=f"custom_key_{i}",
                        )
                    with col2:
                        new_value = st.text_input(
                            f"Custom Setting {i + 1} Value",
                            value=value,
                            key=f"custom_value_{i}",
                        )
                    st.session_state.custom_settings_list[i] = f"{new_key}:{new_value}"

                    # Automatically add an empty key/value pair if the last one is filled
                    if (
                        i == len(st.session_state.custom_settings_list) - 1
                        and new_key
                        and new_value
                    ):
                        st.session_state.custom_settings_list.append("")

            # Update the custom settings in the agent_settings directly
            agent_settings.update(
                {
                    custom_setting.split(":", 1)[0]: custom_setting.split(":", 1)[1]
                    for custom_setting in st.session_state.custom_settings_list
                    if custom_setting and ":" in custom_setting
                }
            )

            st.subheader("Agent Commands")
            commands = Commands(agent_name)
            available_commands = commands.get_available_commands()

            for command in available_commands:
                command_name = command["name"]
                command_status = command["enabled"]
                toggle_status = st.checkbox(
                    command_name, value=command_status, key=command_name
                )
                command["enabled"] = toggle_status

            Agent(agent_name).update_agent_config(
                {"commands": available_commands}, "commands"
            )

        except Exception as e:
            st.error(f"Error loading agent configuration: {str(e)}")

    if st.button("Update Agent Settings"):
        if agent_name:
            try:
                Agent(agent_name).update_agent_config(agent_settings, "settings")
                st.success(f"Agent '{agent_name}' updated.")
            except Exception as e:
                st.error(f"Error updating agent: {str(e)}")
        else:
            st.error("Agent name is required.")


elif main_selection == "Chat":
    st.header("Chat with Agent")

    agent_name = st.selectbox(
        "Select Agent",
        options=[""] + [agent["name"] for agent in CFG.get_agents()],
        index=0,
    )

    smart_chat_toggle = st.checkbox("Enable Smart Chat")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    chat_container = st.container()

    if agent_name:
        agent = AgentLLM(agent_name)

        with chat_container:
            for chat in st.session_state["chat_history"]:
                if chat["sender"] == "User":
                    st.markdown(
                        f'<div style="text-align: left; margin-bottom: 5px;"><strong>User:</strong> {chat["message"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="text-align: right; margin-bottom: 5px;"><strong>Agent:</strong> {chat["message"]}</div>',
                        unsafe_allow_html=True,
                    )

        chat_prompt = st.text_input("Enter your message", key="chat_prompt")
        send_button = st.button("Send Message")

        if send_button:
            if agent_name and chat_prompt:
                st.session_state["chat_history"].append(
                    {"sender": "User", "message": chat_prompt}
                )
                if smart_chat_toggle:
                    response = agent.smart_chat(chat_prompt, shots=3)
                else:
                    response = agent.run(chat_prompt, prompt="Chat", context_results=6)
                st.session_state["chat_history"].append(
                    {"sender": "Agent", "message": response}
                )
                chat_container.empty()
                with chat_container:
                    for chat in st.session_state["chat_history"]:
                        if chat["sender"] == "User":
                            st.markdown(
                                f'<div style="text-align: left; margin-bottom: 5px;"><strong>User:</strong> {chat["message"]}</div>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f'<div style="text-align: right; margin-bottom: 5px;"><strong>Agent:</strong> {chat["message"]}</div>',
                                unsafe_allow_html=True,
                            )
            else:
                st.error("Agent name and message are required.")
    else:
        st.warning("Please select an agent to start chatting.")

elif main_selection == "Instructions":
    st.header("Instruct Agent")

    agent_name = st.selectbox(
        "Select Agent", [""] + [agent["name"] for agent in CFG.get_agents()]
    )
    instruct_prompt = st.text_area("Enter your instruction")
    smart_instruct_toggle = st.checkbox("Enable Smart Instruct")

    if st.button("Instruct Agent"):
        if agent_name and instruct_prompt:
            if agent_name not in st.session_state:
                st.session_state[agent_name] = AgentLLM(agent_name)
            agent = st.session_state[agent_name]
            if smart_instruct_toggle:
                response = agent.smart_instruct(task=instruct_prompt, shots=3)
            else:
                response = agent.run(task=instruct_prompt, prompt="instruct")
            st.markdown(f"**Response:** {response}")
        else:
            st.error("Agent name and instruction are required.")

elif main_selection == "Tasks":
    st.header("Manage Tasks")

    agent_name = st.selectbox(
        "Select Agent", [""] + [agent["name"] for agent in CFG.get_agents()]
    )
    task_objective = st.text_area("Enter the task objective")

    if agent_name:
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
