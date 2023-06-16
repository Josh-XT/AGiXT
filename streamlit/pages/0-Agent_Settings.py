import os
import json
import streamlit as st
from ApiClient import ApiClient
from components.selectors import agent_selection
from components.verify_backend import verify_backend
from components.docs import agixt_docs

verify_backend()

st.set_page_config(
    page_title="Agent Settings",
    page_icon=":hammer_and_wrench:",
    layout="wide",
)
agixt_docs()


@st.cache_data
def get_providers():
    return ApiClient.get_providers()


@st.cache_data
def get_embed_providers():
    return ApiClient.get_embed_providers()


@st.cache_data
def provider_settings(provider_name: str):
    return ApiClient.get_provider_settings(provider_name)


@st.cache_data
def get_extension_settings():
    return ApiClient.get_extension_settings()


providers = get_providers()
embedders = get_embed_providers()
extension_setting_keys = get_extension_settings()


def render_provider_settings(agent_settings, provider_name: str):
    try:
        required_settings = provider_settings(provider_name)
    except (TypeError, ValueError):
        st.error(
            f"Error loading provider settings: expected a list or a dictionary, but got {required_settings}"
        )
        return {}
    rendered_settings = {}

    if not isinstance(required_settings, (list, dict)):
        st.error(
            f"Error loading provider settings: expected a list or a dictionary, but got {required_settings}"
        )
        return rendered_settings

    if isinstance(required_settings, dict):
        required_settings = list(required_settings.keys())

    for key in required_settings:
        if key in agent_settings:
            default_value = agent_settings[key]
        else:
            default_value = ""

        user_val = st.text_input(key, value=default_value)
        rendered_settings[key] = user_val

    if "LOG_REQUESTS" in agent_settings:
        value = agent_settings["LOG_REQUESTS"]
    else:
        value = False
    rendered_settings["LOG_REQUESTS"] = st.checkbox(
        "Log requests to files", key="LOG_REQUESTS", value=value
    )

    return rendered_settings


st.header("Agent Settings")
agent_name = agent_selection()

if "new_agent_name" not in st.session_state:
    st.session_state["new_agent_name"] = ""

# Add an input field for the new agent's name
new_agent = False

# Check if a new agent has been added and reset the session state variable
if (
    st.session_state["new_agent_name"]
    and st.session_state["new_agent_name"] != agent_name
):
    st.session_state["new_agent_name"] = ""

if not agent_name:
    agent_file = st.file_uploader("Import Agent", type=["json"])
    if agent_file:
        agent_name = agent_file.name.split(".")[0]
        agent_settings = agent_file.read().decode("utf-8")
        agent_config = json.loads(agent_settings)
        ApiClient.import_agent(
            agent_name=agent_name,
            settings=agent_config["settings"],
            commands=agent_config["commands"],
        )
        st.success(f"Agent '{agent_name}' imported.")
    new_agent_name = st.text_input("New Agent Name")

    # Add an "Add Agent" button
    add_agent_button = st.button("Add Agent")

    # If the "Add Agent" button is clicked, create a new agent config file
    if add_agent_button:
        if new_agent_name:
            try:
                ApiClient.add_agent(new_agent_name, {})
                st.success(f"Agent '{new_agent_name}' added.")
                agent_name = new_agent_name
                with open(os.path.join("session.txt"), "w") as f:
                    f.write(agent_name)
                st.session_state["new_agent_name"] = agent_name
                st.experimental_rerun()  # Rerun the app to update the agent list
            except Exception as e:
                st.error(f"Error adding agent: {str(e)}")
        else:
            st.error("New agent name is required.")
    new_agent = True

if agent_name and not new_agent:
    try:
        agent_config = ApiClient.get_agentconfig(agent_name=agent_name)
        export_button = st.download_button(
            "Export Agent Config",
            data=json.dumps(agent_config, indent=4),
            file_name=f"{agent_name}.json",
            mime="application/json",
        )
        agent_settings = agent_config.get("settings", {})
        provider_name = agent_settings.get("provider", "")
        provider_name = st.selectbox(
            "Select Provider",
            providers,
            index=providers.index(provider_name) if provider_name in providers else 0,
        )

        agent_settings[
            "provider"
        ] = provider_name  # Update the agent_settings with the selected provider

        embedder_name = agent_settings.get("embedder", "")
        embedder_name = st.selectbox(
            "Select Embedder",
            embedders,
            index=embedders.index(embedder_name) if embedder_name in embedders else 0,
        )

        agent_settings[
            "embedder"
        ] = embedder_name  # Update the agent_settings with the selected embedder

        if provider_name:
            provider_settings = render_provider_settings(agent_settings, provider_name)
            agent_settings.update(provider_settings)

        def render_extension_settings(extension_settings, agent_settings):
            rendered_settings = {}

            for extension, settings in extension_settings.items():
                st.subheader(f"{extension}")
                for key, val in settings.items():
                    if key in agent_settings:
                        default_value = agent_settings[key]
                    else:
                        default_value = val if val else ""

                    user_val = st.text_input(
                        key, value=default_value, key=f"{extension}_{key}"
                    )

                    # Check if the user value exists before saving the setting
                    if user_val:
                        rendered_settings[key] = user_val

            return rendered_settings

        with st.form(key="update_agent_settings_form"):
            update_agent_settings_button = st.form_submit_button(
                "Update Agent Settings"
            )
            wipe_memories_button = st.form_submit_button("Wipe Agent Memories")
            delete_agent_button = st.form_submit_button("Delete Agent")
        st.subheader("Extension Settings")
        with st.form("extension_settings"):
            extension_settings = render_extension_settings(
                extension_setting_keys, agent_settings
            )

            # Update the extension settings in the agent_settings directly
            agent_settings.update(extension_settings)

            st.subheader("Agent Commands")
            # Fetch the available commands using the `Commands` class
            available_commands = agent_config["commands"]

            # Save the existing command state to prevent duplication
            existing_command_states = {
                command_name: command_status
                for command_name, command_status in available_commands.items()
            }

            all_commands_selected = st.checkbox("Select All Commands")

            for command_name, command_status in available_commands.items():
                if all_commands_selected:
                    available_commands[command_name] = True
                else:
                    toggle_status = st.checkbox(
                        command_name,
                        value=command_status,
                        key=command_name,
                    )
                    available_commands[command_name] = toggle_status
            if st.form_submit_button("Update Agent Commands"):
                ApiClient.update_agent_commands(
                    agent_name=agent_name, commands=available_commands
                )
    except Exception as e:
        st.error(f"Error loading agent configuration: {str(e)}")

if not new_agent:
    # Trigger actions on form submit
    if update_agent_settings_button:
        if agent_name:
            try:
                ApiClient.update_agent_commands(
                    agent_name=agent_name, commands=available_commands
                )
                ApiClient.update_agent_settings(
                    agent_name=agent_name, settings=agent_settings
                )
                st.success(f"Agent '{agent_name}' updated.")
            except Exception as e:
                st.error(f"Error updating agent: {str(e)}")

    if wipe_memories_button:
        if agent_name:
            try:
                ApiClient.wipe_agent_memories(agent_name=agent_name)
                st.success(f"Memories of agent '{agent_name}' wiped.")
            except Exception as e:
                st.error(f"Error wiping agent's memories: {str(e)}")

    if delete_agent_button:
        if agent_name:
            try:
                ApiClient.delete_agent(agent_name=agent_name)
                st.success(f"Agent '{agent_name}' deleted.")
                st.session_state["new_agent_name"] = ""  # Reset the selected agent
                st.experimental_rerun()  # Rerun the app to update the agent list
            except Exception as e:
                st.error(f"Error deleting agent: {str(e)}")
        else:
            st.error("Agent name is required.")
