import streamlit as st
from ApiClient import ApiClient
from components.history import get_history
import os
import logging


def agent_selector():
    # Load the previously selected agent name
    try:
        with open(os.path.join("session.txt"), "r") as f:
            previously_selected_agent = f.read().strip()
    except FileNotFoundError:
        previously_selected_agent = None

    # Get the list of agent names
    agent_names = [agent["name"] for agent in ApiClient.get_agents()]

    # If the previously selected agent is in the list, use it as the default
    if previously_selected_agent in agent_names:
        default_index = (
            agent_names.index(previously_selected_agent) + 1
        )  # add 1 for the empty string at index 0
    else:
        default_index = 0

    # Create the selectbox
    selected_agent = st.selectbox(
        "Agent Name",
        options=[""] + agent_names,
        index=default_index,
    )

    # If the selected agent has changed, save the new selection
    if selected_agent != previously_selected_agent:
        with open(os.path.join("session.txt"), "w") as f:
            f.write(selected_agent)
        try:
            st.experimental_rerun()
        except Exception as e:
            logging.info(e)

    # Get the history for the selected agent
    agent_history = get_history(agent_name=selected_agent)

    return selected_agent, agent_history
