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

st.set_page_config(
    page_title="Agent-LLM",
    page_icon=":robot:",
    layout="wide",
    initial_sidebar_state="expanded",
)

CFG = Config()

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

            # Remove any empty key/value pairs at the end of the list
            while (
                st.session_state.custom_settings_list
                and not st.session_state.custom_settings_list[-1]
            ):
                st.session_state.custom_settings_list.pop()

            agent_settings["custom_settings"] = [
                cs for cs in st.session_state.custom_settings_list if cs
            ]

            # Update the agent config with the new settings
            Agent(agent_name).update_agent_config(agent_settings)

            if st.button("Delete Agent"):
                if st.session_state.email == admin_email:
                    Agent(agent_name).delete_agent()
                    st.success(f"Agent '{agent_name}' deleted.")
                    agent_name = ""
                    st.experimental_rerun()  # Rerun the app to update the agent list
                else:
                    st.error("Only the admin can delete agents.")

        except Exception as e:
            st.error(f"Error loading agent settings: {str(e)}")

elif main_selection == "Chat":
    # Chat UI code
    st.header("Chat")

    agent_name = st.selectbox(
        "Select Agent",
        [""] + [agent["name"] for agent in CFG.get_agents()],
        key="chat_agent_name_select",
    )

    if agent_name:
        agent = Agent(agent_name)
        agent_settings = agent.get_agent_config().get("settings", {})

        message = st.text_input("User:")
        if st.button("Send"):
            agent.handle_message(message)
            response = agent.get_response()
            st.text_area("Agent:", value=response, height=200, max_chars=None)

            # Save the conversation
            conversation = agent.get_conversation()
            agent.save_conversation(conversation)

elif main_selection == "Instructions":
    # Instructions UI code
    st.header("Instructions")

    st.write(
        """
        Instructions for using the Agent-LLM:

        1. Login with your credentials.
        2. Manage agent settings:
           - Select an existing agent or create a new agent.
           - Select a provider and configure the provider settings.
           - Add custom settings if needed.
        3. Use the Chat feature to communicate with the agent.
        4. View and manage tasks assigned to the agent.
        5. Create and manage conversation chains.
        6. Create and manage custom prompts.
        7. Change your password if needed.
        8. Logout when finished.
        """
    )

elif main_selection == "Tasks":
    # Tasks UI code
    st.header("Tasks")

    agent_name = st.selectbox(
        "Select Agent",
        [""] + [agent["name"] for agent in CFG.get_agents()],
        key="tasks_agent_name_select",
    )

    if agent_name:
        agent = Agent(agent_name)
        tasks = agent.get_tasks()
        if tasks:
            st.write("Tasks assigned to the agent:")
            for task in tasks:
                st.write(task)
        else:
            st.write("No tasks assigned to the agent.")

elif main_selection == "Chains":
    # Chains UI code
    st.header("Chains")

    agent_name = st.selectbox(
        "Select Agent",
        [""] + [agent["name"] for agent in CFG.get_agents()],
        key="chains_agent_name_select",
    )

    if agent_name:
        agent = Agent(agent_name)
        chains = agent.get_chains()
        if chains:
            st.write("Conversation chains:")
            for chain in chains:
                st.write(chain)
        else:
            st.write("No conversation chains.")

elif main_selection == "Custom Prompts":
    # Custom Prompts UI code
    st.header("Custom Prompts")

    agent_name = st.selectbox(
        "Select Agent",
        [""] + [agent["name"] for agent in CFG.get_agents()],
        key="prompts_agent_name_select",
    )

    if agent_name:
        agent = Agent(agent_name)
        prompts = agent.get_custom_prompts()
        if prompts:
            st.write("Custom prompts:")
            for prompt in prompts:
                st.write(prompt)
        else:
            st.write("No custom prompts.")

# Logout if there is a session state but the email is not set (indicating a logout)
if st.session_state and "email" not in st.session_state:
    logout()
