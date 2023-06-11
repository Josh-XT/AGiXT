from ApiClient import ApiClient
import streamlit as st


@st.cache_data
def cached_get_extensions():
    return ApiClient.get_extensions()


def prompt_selection(step_number, prompt):
    available_prompts = ApiClient.get_prompts()
    prompt_name = st.selectbox(
        "Select Custom Prompt",
        [""] + available_prompts,
        key=f"step_{step_number}_prompt_name",
    )

    if prompt_name:
        prompt_args = ApiClient.get_prompt_args(prompt_name)
        formatted_prompt_args = ", ".join(
            [
                f"{arg}: {st.text_input(arg, value=prompt.get(arg, ''), key=f'{arg}_{step_number}')} "
                for arg in prompt_args
                if arg != "context" and arg != "command_list" and arg != "COMMANDS"
            ]
        )
        new_prompt = {
            "prompt_name": prompt_name,
            "prompt_args": formatted_prompt_args,
        }
        return new_prompt


def command_selection(step_number, prompt):
    agent_commands = cached_get_extensions()
    available_commands = [cmd[0] for cmd in agent_commands]
    command_name = st.selectbox(
        "Select Command",
        [""] + available_commands,
        key=f"step_{step_number}_command_name",
    )

    if command_name:
        command_args = ApiClient.get_command_args(command_name)
        formatted_command_args = ", ".join(
            [
                f"{arg}: {st.text_input(arg, value=prompt.get(arg, ''), key=f'{arg}_{step_number}')} "
                for arg in command_args
                if arg != "context" and arg != "command_list" and arg != "COMMANDS"
            ]
        )
        new_prompt = {
            "command_name": command_name,
            "command_args": formatted_command_args,
        }
        return new_prompt


def chain_selection(step_number, prompt):
    available_chains = ApiClient.get_chains()
    chain_name = st.selectbox(
        "Select Chain",
        [""] + available_chains,
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


def add_new_step(chain_name, step_number, agents):
    agent_name = st.selectbox(
        "Select Agent",
        options=[""] + [agent["name"] for agent in agents],
        index=0,
        key="add_step_agent_name",
    )
    prompt_type = st.selectbox(
        "Select Step Type",
        [""] + ["Command", "Prompt", "Chain"],
        key="add_step_prompt_type",
    )

    if prompt_type == "Command":
        prompt = command_selection()
    elif prompt_type == "Prompt":
        prompt = prompt_selection()
    elif prompt_type == "Chain":
        prompt = chain_selection()
    else:
        prompt = {}
    if st.button("Add New Step", key=f"add_step_{step_number}"):
        if chain_name and step_number and agent_name and prompt_type and prompt:
            ApiClient.add_step(
                chain_name=chain_name,
                step_number=step_number,
                agent_name=agent_name,
                prompt_type=prompt_type,
                prompt=prompt,
            )
            st.success(f"Step added to chain '{chain_name}'.")
            st.experimental_rerun()
        else:
            st.error("All fields are required.")


def modify_step(chain_name, step_number, agent_name, prompt_type, prompt):
    if st.button("Modify Step", key=f"modify_step_{step_number}"):
        if chain_name and step_number and agent_name and prompt_type and prompt:
            ApiClient.update_step(
                chain_name=chain_name,
                step_number=step_number,
                agent_name=agent_name,
                prompt_type=prompt_type,
                prompt=prompt,
            )
            st.success(f"Step modified in chain '{chain_name}'.")
            st.experimental_rerun()
        else:
            st.error("All fields are required.")
