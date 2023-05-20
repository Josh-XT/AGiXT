import streamlit as st
from Config import Config
from components.AgentSettingsPage import AgentSettingsPage
from components.ChatPage import ChatPage
from components.InstructPage import InstructPage
from components.TasksPage import TasksPage
from components.ChainsPage import ChainsPage
from components.CustomPromptsPage import CustomPromptsPage


CFG = Config()
st.set_page_config(
    page_title="AGiXT",
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


if main_selection == "Agent Settings":
    AgentSettingsPage(st)

elif main_selection == "Chat":
    ChatPage(st)

elif main_selection == "Instructions":
    InstructPage(st)

elif main_selection == "Tasks":
    TasksPage(st)


elif main_selection == "Chains":
    ChainsPage(st)

elif main_selection == "Custom Prompts":
    CustomPromptsPage(st)
