import os
import streamlit as st
from ApiClient import ApiClient
from auth_libs.Users import check_auth_status
from components.agent_selector import agent_selector

check_auth_status()

agent_name = agent_selector()
providers = ApiClient.get_providers()
embedders = ApiClient.get_embed_providers()


def render_provider_settings(agent_settings, provider_name: str):
    try:
        required_settings = ApiClient.get_provider_settings(provider_name)
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


st.header("Manage Agent Settings")

if "new_agent_name" not in st.session_state:
    st.session_state.new_agent_name = ""

# Check if a new agent has been added and reset the session state variable
if st.session_state.new_agent_name and st.session_state.new_agent_name != agent_name:
    st.session_state.new_agent_name = ""

# Add an input field for the new agent's name
new_agent = False
if not agent_name:
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
                st.session_state.new_agent_name = agent_name
                st.experimental_rerun()  # Rerun the app to update the agent list
            except Exception as e:
                st.error(f"Error adding agent: {str(e)}")
        else:
            st.error("New agent name is required.")
    new_agent = True

if agent_name and not new_agent:
    try:
        agent_config = ApiClient.get_agentconfig(agent_name=agent_name)
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

        st.subheader("Extension Settings")
        extension_setting_keys = ApiClient.get_extension_settings()

        extension_settings = render_extension_settings(
            extension_setting_keys, agent_settings
        )

        # Update the extension settings in the agent_settings directly
        agent_settings.update(extension_settings)

        st.subheader("Custom Settings")
        custom_settings = agent_settings.get("custom_settings", [])

        custom_settings_list = st.session_state.get("custom_settings_list", None)
        if custom_settings_list is None:
            if not custom_settings:
                custom_settings = [""]
            st.session_state.custom_settings_list = custom_settings.copy()

        custom_settings_container = st.container()
        with custom_settings_container:
            for i, custom_setting in enumerate(st.session_state.custom_settings_list):
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
        # Fetch the available commands using the `Commands` class
        available_commands = ApiClient.get_commands(agent_name=agent_name)

        # Save the existing command state to prevent duplication
        existing_command_states = {
            command_name: command_status
            for command_name, command_status in available_commands.items()
        }

        for command_name, command_status in available_commands.items():
            toggle_status = st.checkbox(
                command_name,
                value=command_status,
                key=command_name,
            )
            available_commands[command_name] = toggle_status

        # Update the available commands back to the agent config
        ApiClient.update_agent_commands(
            agent_name=agent_name, commands=available_commands
        )

    except Exception as e:
        st.error(f"Error loading agent configuration: {str(e)}")

if not new_agent:
    # Create a form for each button
    with st.form(key="update_agent_settings_form"):
        update_agent_settings_button = st.form_submit_button("Update Agent Settings")

    with st.form(key="wipe_memories_form"):
        wipe_memories_button = st.form_submit_button("Wipe Agent Memories")

    with st.form(key="delete_agent_form"):
        delete_agent_button = st.form_submit_button("Delete Agent")

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
                st.session_state.new_agent_name = ""  # Reset the selected agent
                st.experimental_rerun()  # Rerun the app to update the agent list
            except Exception as e:
                st.error(f"Error deleting agent: {str(e)}")
        else:
            st.error("Agent name is required.")
