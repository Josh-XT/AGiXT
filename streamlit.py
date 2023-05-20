import streamlit as st
import threading
import os
import yaml
import bcrypt
import json
from Config import Config
from AgentLLM import AgentLLM
from Config.Agent import Agent
from Chain import Chain
from CustomPrompt import CustomPrompt
from provider import get_provider_options
from Commands import Commands
from Embedding import get_embedding_providers

CFG = Config()

st.set_page_config(
    page_title="Agent-LLM",
    page_icon=":robot:",
    layout="wide",
    initial_sidebar_state="expanded",
)


SETUP_INI = "setup.cfgi"
if not os.path.exists(SETUP_INI):
    st.write("Setup Configuration")
    setup_cfg = st.radio("Auth/Login Settings", ("No Login", "Single-User Login", "Multi-User Private Registration", "Multi-User Public Registration"), 0)
    if st.button("Build Config"):
        with open(SETUP_INI, "w") as file:
            config = {
                "auth": setup_cfg,
                "allow_reg": False,
                "allow_uac": False
            }
            json.dump({"config": [config]}, file)
            st.success("{setup_cfg} Setup Configured!")
        st.experimental_rerun()
    st.stop()

# Load the Config data from the CONFIG file
def load_cfg_data():
    with open(SETUP_INI, "r") as file:
        data = json.load(file)
    return data

# Save the Config data from the CONFIG file
def save_cfg_data(data):
    with open(SETUP_INI, "w") as file:
        json.dump(data, file)

        
setup_cfg = load_cfg_data()
for config in setup_cfg["config"]:
    if not "allow_reg" in config:
        config["allow_reg"] = False
    if not "allow_uac" in config:
        config["allow_uac"] = False
    if not "allow_ucp" in config:
        config["allow_ucp"] = False
    if not "allow_uaa" in config:
        config["allow_uaa"] = False

    if config["auth"] == "No Login":
        auth = "NL"
        #st.success("NO LOGIN REQUIRED LOADING INTERFACE")
    elif config["auth"] == "Single-User Login":
        auth = "SUL"
    elif config["auth"] == "Multi-User Private Registration":
        auth = "MPVR"
    elif config["auth"] == "Multi-User Public Registration":
        auth = "MPBR"
        save_cfg_data(setup_cfg)
    allow_reg = config["allow_reg"]
    allow_uac = config["allow_uac"]
    allow_ucp = config["allow_ucp"]
    allow_uaa = config["allow_uaa"]

# Check if the JSON file exists and prompt for admin email and password if it doesn't
JSON_FILE_PATH = "users.json"
if not os.path.exists(JSON_FILE_PATH) and auth == "NL":
    with open(JSON_FILE_PATH, "w") as file:
        admin_user = {
            "email": "Private User",
            "password_hash": bcrypt.hashpw("1", bcrypt.gensalt()),
            "admin": "True"
        }
        json.dump({"users": [admin_user]}, file)
    st.experimental_rerun()

elif not os.path.exists(JSON_FILE_PATH):
    st.write("Admin Setup")
    admin_email = st.text_input("Admin Email")
    admin_password = st.text_input("Admin Password", type="password")
    if st.button("Setup Admin"):
        if admin_email and admin_password:
            with open(JSON_FILE_PATH, "w") as file:
                admin_user = {
                    "email": admin_email,
                    "password_hash": bcrypt.hashpw(admin_password, bcrypt.gensalt()),
                    "admin": "True"
                }
                json.dump({"users": [admin_user]}, file)
                st.success("Admin account created successfully!")
        else:
            st.error("Admin email and password are required.")
        st.experimental_rerun()

    st.stop()

# Load the user data from the JSON file
def load_user_data():
    with open(JSON_FILE_PATH, "r") as file:
        data = json.load(file)
    return data

# Save the user data to the JSON file
def save_user_data(data):
    with open(JSON_FILE_PATH, "w") as file:
        json.dump(data, file)

        
user_data = load_user_data()
for user in user_data["users"]:
    if user["admin"] == "True":
        admin_email = user["email"]

# Login form
def login_form():
    st.write("Please log in")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if auth == "NL":
        st.session_state["logged_in"] = True
        st.session_state["email"] = admin_email #Redirect to UI
        st.experimental_rerun()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            user_data = load_user_data()
            for user in user_data["users"]:
                if user["email"] == email:
                    if bcrypt.hashpw(password, user["password_hash"])==user["password_hash"]:
                        st.success("Login successful!")
                        st.session_state["logged_in"] = True
                        st.session_state["email"] = email
                        st.experimental_rerun()  # Redirect to UI
                        break
            else:
                st.error("Incorrect email or password.")
    with col2:
        
        recheck_cfg = load_cfg_data()
        for rconfig in recheck_cfg["config"]:
            allow_reg = rconfig["allow_reg"]
        if allow_reg == True:
            if st.button("Register"):
                st.session_state["registering"] = True
                st.experimental_rerun()
    if st.session_state["registered"] == True:
        st.success("User created successfully!")

    st.stop()
    
# Create user form (pub registration)
def registration_form():
    st.write("Registration Form")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Register"):
            if not email:
                st.error("Email is required.")
            elif password != confirm_password:
                st.error("Password and confirm password do not match.")
            else:
                user_data = load_user_data()
                for user in user_data["users"]:
                    if user["email"] == email:
                        return True

                new_user = {
                    "email": email,
                    "password_hash": bcrypt.hashpw(password, bcrypt.gensalt()),
                    "admin": "False"
                }
                user_data["users"].append(new_user)
                save_user_data(user_data)
                st.session_state["registering"] = False
                return False
    with col2:
        if st.button("Return"):
            return False

    if st.session_state["regFail"] == True:
        st.error("User with the same email already exists.")

    st.stop()

# Logout function
def logout():
    st.session_state.pop("logged_in", None)
    st.session_state.pop("email", None)
    st.experimental_rerun()

# Main code
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    if 'registering' not in st.session_state:
        st.session_state["registering"] = False
    if 'regFail' not in st.session_state:
        st.session_state["regFail"] = False
    if 'registered' not in st.session_state:
        st.session_state["registered"] = False

    if not st.session_state["registering"]:
        login_form()
    else:
        retval = registration_form()
        st.session_state["regFail"] = retval
        st.session_state["registered"] = not retval
        st.experimental_rerun()
    st.stop()
else:
    st.header("Welcome!")
    st.write("You are logged in as: ", st.session_state["email"])
    if auth != "NL" and st.session_state["logged_in"] == True:
        if st.button("Logout"):
            logout()

# Add the UI code here
agent_stop_events = {}


if auth == "NL":
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
else:
    main_selection = st.sidebar.selectbox(
    "Select a feature",
    [
        "Account Manager",
        "Agent Settings",
        "Chat",
        "Instructions",
        "Tasks",
        "Chains",
        "Custom Prompts",
    ],
)

# Agent Settings UI code
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


# Add the UI sections here based on the main_selection
if main_selection == "Account Manager":

    # Toggle public registrations
    def toggle_value(val,to_toggle="allow_reg"):
                
        setup_cfg = load_cfg_data()
        for config in setup_cfg["config"]:
            config[to_toggle] = val
        save_cfg_data(setup_cfg)

        if val == False:
            st.success("Setting Disabled!")
        else:
            st.success("Setting Enabled!")

        st.session_state["regCheck"] = val

    # Change password form
    def change_password_form():
        st.write("Change Password")
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        if st.button("Change Password"):
            user_data = load_user_data()
            for user in user_data["users"]:
                if user["email"] == st.session_state["email"]:
                    if bcrypt.checkpw(current_password, user["password_hash"])==user["password_hash"]:
                        if new_password == confirm_password:
                            user["password_hash"] = bcrypt.hashpw(new_password, bcrypt.gensalt())
                            save_user_data(user_data)
                            st.success("Password changed successfully!")
                        else:
                            st.error("New password and confirm password do not match.")
                    else:
                        st.error("Incorrect current password.")
                    break

    # Create user form (admin only)
    def create_user_form():
        if st.session_state["email"] != admin_email:
            st.error("Only the admin can create new users.")
            return
        st.write("Create User")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        if st.button("Create User"):
            if not email:
                st.error("Email is required.")
            elif password != confirm_password:
                st.error("Password and confirm password do not match.")
            else:
                user_data = load_user_data()
                for user in user_data["users"]:
                    if user["email"] == email:
                        st.error("User with the same email already exists.")
                        return

                new_user = {
                    "email": email,
                    "password_hash": bcrypt.hashpw(password, bcrypt.gensalt()),
                    "admin": "False"
                }
                user_data["users"].append(new_user)
                save_user_data(user_data)
                st.success("User created successfully!")

    if st.session_state["email"] == admin_email and auth == "MPBR":
        setup_cfg = load_cfg_data()
        for config in setup_cfg["config"]:
            allow_reg = config["allow_reg"]
        
        st.session_state["regCheck"] = allow_reg

        if allow_reg == True:
            ar_opposite = False
        else:
            ar_opposite = True

        if allow_uac == True:
            uac_opposite = False
        else:
            uac_opposite = True

        if allow_ucp == True:
            ucp_opposite = False
        else:
            ucp_opposite = True

        if allow_uaa == True:
            uaa_opposite = False
        else:
            uaa_opposite = True

        col1, col2, = st.columns(2)

        with col1:
            if auth == "MPBR":
                st.checkbox("Enable Public Registration", value=allow_reg, on_change=toggle_value, args=(ar_opposite,"allow_reg"))
            else:
                st.checkbox("Enable Public Registration", value=allow_reg, on_change=toggle_value, args=(ar_opposite,"allow_reg"), disabled=True)
            st.checkbox("Enable Users to Create Public Agents", value=allow_uac, on_change=toggle_value, args=(uac_opposite,"allow_uac"))

        with col2:
            st.checkbox("Enable Users To Create Private Agents", value=allow_ucp, on_change=toggle_value, args=(ucp_opposite,"allow_ucp"))
            st.checkbox("Enable Users To Use Admin's Agents", value=allow_uaa, on_change=toggle_value, args=(uaa_opposite,"allow_uaa"))

    change_password_form()
    if st.session_state["email"] == admin_email and auth != "SUL":
        create_user_form()

elif main_selection == "Agent Settings":
    st.header("Manage Agent Settings")

    if "new_agent_name" not in st.session_state:
        st.session_state.new_agent_name = ""

    agent_name = st.selectbox(
        "Select Agent",
        [""] + [agent["name"] for agent in CFG.get_agents()],
        index=0
        if not st.session_state.new_agent_name
        else [agent["name"] for agent in CFG.get_agents()].index(
            st.session_state.new_agent_name
        )
        + 1,
        key="agent_name_select",
    )

    # Check if a new agent has been added and reset the session state variable
    if (
        st.session_state.new_agent_name
        and st.session_state.new_agent_name != agent_name
    ):
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
                # You can customize provider_settings and commands as needed
                provider_settings = {
                    "provider": "gpt4free",
                    "AI_MODEL": "gpt-4",
                    "AI_TEMPERATURE": "0.7",
                    "MAX_TOKENS": "4000",
                    "embedder": "default",
                }
                commands = []  # You can define the default commands here
                try:
                    Agent(new_agent_name).add_agent(new_agent_name, provider_settings)
                    st.success(f"Agent '{new_agent_name}' added.")
                    agent_name = new_agent_name
                    st.session_state.new_agent_name = agent_name
                    st.experimental_rerun()  # Rerun the app to update the agent list
                except Exception as e:
                    st.error(f"Error adding agent: {str(e)}")
            else:
                st.error("New agent name is required.")
        new_agent = True

    if agent_name and not new_agent:
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

            agent_settings[
                "provider"
            ] = provider_name  # Update the agent_settings with the selected provider

            embedder_name = agent_settings.get("embedder", "")
            embedders = get_embedding_providers()
            embedder_name = st.selectbox(
                "Select Embedder",
                embedders,
                index=embedders.index(embedder_name)
                if embedder_name in embedders
                else 0,
            )

            agent_settings[
                "embedder"
            ] = embedder_name  # Update the agent_settings with the selected embedder

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
            # Fetch the available commands using the `Commands` class
            commands = Commands(agent_name)
            available_commands = commands.get_available_commands()

            # Save the existing command state to prevent duplication
            existing_command_states = {
                command["friendly_name"]: command["enabled"]
                for command in available_commands
            }
            for command in available_commands:
                command_friendly_name = command["friendly_name"]
                command_status = (
                    existing_command_states[command_friendly_name]
                    if command_friendly_name in existing_command_states
                    else command["enabled"]
                )
                toggle_status = st.checkbox(
                    command_friendly_name,
                    value=command_status,
                    key=command_friendly_name,
                )
                command["enabled"] = toggle_status
            reduced_commands = {
                cmd["friendly_name"]: cmd["enabled"] for cmd in available_commands
            }
            # Update the available commands back to the agent config
            Agent(agent_name).update_agent_config(reduced_commands, "commands")

        except Exception as e:
            st.error(f"Error loading agent configuration: {str(e)}")

    if not new_agent:
        if st.button("Update Agent Settings"):
            if agent_name:
                try:
                    # Update the available commands back to the agent config
                    # Save commands in the desired format
                    reduced_commands = {
                        cmd["friendly_name"]: cmd["enabled"]
                        for cmd in available_commands
                    }
                    Agent(agent_name).update_agent_config(reduced_commands, "commands")
                    # Update other settings
                    Agent(agent_name).update_agent_config(agent_settings, "settings")
                    st.success(f"Agent '{agent_name}' updated.")
                except Exception as e:
                    st.error(f"Error updating agent: {str(e)}")
        delete_agent_button = st.button("Delete Agent")

        # If the "Delete Agent" button is clicked, delete the agent config file
        if delete_agent_button:
            if agent_name:
                try:
                    Agent(agent_name).delete_agent(agent_name)
                    st.success(f"Agent '{agent_name}' deleted.")
                    agent_name = ""
                    st.experimental_rerun()  # Rerun the app to update the agent list
                except Exception as e:
                    st.error(f"Error deleting agent: {str(e)}")
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
        st.session_state["chat_history"] = {}

    chat_container = st.container()

    def render_chat_history(chat_container, chat_history):
        chat_container.empty()
        with chat_container:
            for chat in chat_history:
                if "sender" in chat and "message" in chat:
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

    if agent_name:
        learn_file_upload = st.file_uploader("Upload a file to learn from")
        learn_file_path = ""
        if learn_file_upload is not None:
            if not os.path.exists(os.path.join("data", "uploaded_files")):
                os.makedirs(os.path.join("data", "uploaded_files"))
            learn_file_path = os.path.join(
                "data", "uploaded_files", learn_file_upload.name
            )
            with open(learn_file_path, "wb") as f:
                f.write(learn_file_upload.getbuffer())

        chat_history = []
        agent_file_path = os.path.join("data", "agents", f"{agent_name}.yaml")

        if os.path.exists(agent_file_path):
            with open(agent_file_path, "r") as file:
                agent_data = yaml.safe_load(file)
                chat_history = agent_data.get("interactions", [])

        st.session_state.chat_history[agent_name] = chat_history

        render_chat_history(chat_container, st.session_state.chat_history[agent_name])

        chat_prompt = st.text_input("Enter your message", key="chat_prompt")
        send_button = st.button("Send Message")

        if send_button:
            if agent_name and chat_prompt:
                with st.spinner("Thinking, please wait..."):
                    agent = AgentLLM(agent_name)
                    if smart_chat_toggle:
                        response = agent.smart_chat(
                            chat_prompt,
                            shots=3,
                            async_exec=True,
                            learn_file=learn_file_path,
                        )
                    else:
                        response = agent.run(
                            chat_prompt,
                            prompt="Chat",
                            context_results=6,
                            learn_file=learn_file_path,
                        )
                chat_entry = [
                    {"sender": "User", "message": chat_prompt},
                    {"sender": "Agent", "message": response},
                ]
                st.session_state.chat_history[agent_name].extend(chat_entry)
                render_chat_history(
                    chat_container, st.session_state.chat_history[agent_name]
                )
            else:
                st.error("Agent name and message are required.")
    else:
        st.warning("Please select an agent to start chatting.")

elif main_selection == "Instructions":
    st.header("Instruct an Agent")

    agent_name = st.selectbox(
        "Select Agent",
        options=[""] + [agent["name"] for agent in CFG.get_agents()],
        index=0,
    )

    smart_instruct_toggle = st.checkbox("Enable Smart Instruct")

    if "instruct_history" not in st.session_state:
        st.session_state["instruct_history"] = {}

    instruct_container = st.container()

    def render_instruct_history(instruct_container, instruct_history):
        instruct_container.empty()
        with instruct_container:
            for instruct in instruct_history:
                if "sender" in instruct and "message" in instruct:
                    if instruct["sender"] == "User":
                        st.markdown(
                            f'<div style="text-align: left; margin-bottom: 5px;"><strong>User:</strong> {instruct["message"]}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f'<div style="text-align: right; margin-bottom: 5px;"><strong>Agent:</strong> {instruct["message"]}</div>',
                            unsafe_allow_html=True,
                        )

    if agent_name:
        learn_file_upload = st.file_uploader("Upload a file to learn from")
        learn_file_path = ""
        if learn_file_upload is not None:
            if not os.path.exists(os.path.join("data", "uploaded_files")):
                os.makedirs(os.path.join("data", "uploaded_files"))
            learn_file_path = os.path.join(
                "data", "uploaded_files", learn_file_upload.name
            )
            with open(learn_file_path, "wb") as f:
                f.write(learn_file_upload.getbuffer())
        instruct_history = []
        agent_file_path = os.path.join("data", "agents", f"{agent_name}.yaml")

        if os.path.exists(agent_file_path):
            with open(agent_file_path, "r") as file:
                agent_data = yaml.safe_load(file)
                instruct_history = agent_data.get("interactions", [])

        st.session_state.instruct_history[agent_name] = instruct_history

        render_instruct_history(
            instruct_container, st.session_state.instruct_history[agent_name]
        )

        instruct_prompt = st.text_input("Enter your message", key="instruct_prompt")
        send_button = st.button("Send Message")

        if send_button:
            if agent_name and instruct_prompt:
                with st.spinner("Thinking, please wait..."):
                    agent = AgentLLM(agent_name)
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
                st.session_state.instruct_history[agent_name].extend(instruct_entry)
                render_instruct_history(
                    instruct_container, st.session_state.instruct_history[agent_name]
                )
            else:
                st.error("Agent name and message are required.")
    else:
        st.warning("Please select an agent to give instructions.")

elif main_selection == "Tasks":
    st.header("Manage Tasks")

    agent_name = st.selectbox(
        "Select Agent",
        options=[""] + [agent["name"] for agent in CFG.get_agents()],
        index=0,
    )
    task_objective = st.text_area("Enter the task objective")

    if agent_name:
        learn_file_upload = st.file_uploader("Upload a file to learn from")
        learn_file_path = ""
        if learn_file_upload is not None:
            if not os.path.exists(os.path.join("data", "uploaded_files")):
                os.makedirs(os.path.join("data", "uploaded_files"))
            learn_file_path = os.path.join(
                "data", "uploaded_files", learn_file_upload.name
            )
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
                        CFG.agent_instances[agent_name] = AgentLLM(agent_name)
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

# Logout if there is a session state but the email is not set (indicating a logout)
if st.session_state and "email" not in st.session_state:
    logout()