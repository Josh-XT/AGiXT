from ApiClient import ApiClient
import streamlit as st
import os
import logging


@st.cache_data
def cached_get_extensions():
    return ApiClient.get_extensions()


@st.cache_data
def cached_get_prompts():
    return ApiClient.get_prompts()


def build_args(args: dict = {}, prompt: dict = {}, step_number: int = 0):
    return {
        arg: st.text_input(arg, value=prompt.get(arg, ""), key=f"{arg}_{step_number}")
        for arg in args
        if arg != "context"
        and arg != "command_list"
        and arg != "COMMANDS"
        and arg != "user_input"
    }


def prompt_selection(prompt: dict = {}, step_number: int = 0):
    available_prompts = cached_get_prompts()
    prompt_name = st.selectbox(
        "Select Custom Prompt",
        [""] + available_prompts,
        index=available_prompts.index(prompt.get("prompt_name", "")) + 1
        if "prompt_name" in prompt
        else 0,
        key=f"step_{step_number}_prompt_name",
    )

    if prompt_name:
        prompt_args = ApiClient.get_prompt_args(prompt_name)
        args = build_args(args=prompt_args, prompt=prompt, step_number=step_number)
        new_prompt = {
            "prompt_name": prompt_name,
            **args,
        }
        return new_prompt


def command_selection(prompt: dict = {}, step_number: int = 0):
    agent_commands = cached_get_extensions()
    available_commands = [cmd[0] for cmd in agent_commands]
    command_name = st.selectbox(
        "Select Command",
        [""] + available_commands,
        key=f"command_name_{step_number}",
        index=available_commands.index(prompt.get("command_name", "")) + 1
        if "command_name" in prompt
        else 0,
    )

    if command_name:
        command_args = ApiClient.get_command_args(command_name=command_name)
        args = build_args(args=command_args, prompt=prompt, step_number=step_number)
        new_prompt = {
            "command_name": command_name,
            **args,
        }
        return new_prompt


def chain_selection(prompt: dict = {}, step_number: int = 0):
    available_chains = ApiClient.get_chains()
    chain_name = st.selectbox(
        "Select Chain",
        [""] + available_chains,
        index=available_chains.index(prompt.get("chain_name", "")) + 1
        if "chain_name" in prompt
        else 0,
        key=f"step_{step_number}_chain_name",
    )
    user_input = st.text_input(
        "User Input",
        value=prompt.get("user_input", ""),
        key=f"user_input_{step_number}",
    )

    if chain_name:
        new_prompt = {"chain_name": chain_name, "user_input": user_input}
        return new_prompt


def agent_selection():
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
        key="select_learning_agent",
    )

    # If the selected agent has changed, save the new selection
    if selected_agent != previously_selected_agent:
        with open(os.path.join("session.txt"), "w") as f:
            f.write(selected_agent)
        try:
            st.experimental_rerun()
        except Exception as e:
            logging.info(e)
    return selected_agent
