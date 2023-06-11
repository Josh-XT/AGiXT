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
        index=available_prompts.index(prompt.get("prompt_name", "")) + 1
        if "prompt_name" in prompt
        else 0,
        key=f"step_{step_number}_prompt_name",
    )

    if prompt_name:
        prompt_args = ApiClient.get_prompt_args(prompt_name)
        formatted_prompt_args = {
            arg: st.text_input(
                arg, value=prompt.get(arg, ""), key=f"{arg}_{step_number}"
            )
            for arg in prompt_args
            if arg != "context" and arg != "command_list" and arg != "COMMANDS"
        }
        new_prompt = {
            "prompt_name": prompt_name,
            "prompt_args": formatted_prompt_args,
        }
        return new_prompt


def command_selection(step_number, prompt):
    print(prompt)
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
        formatted_command_args = {
            arg: st.text_input(
                arg, value=prompt.get(arg, ""), key=f"{arg}_{step_number}"
            )
            for arg in command_args
            if arg != "context" and arg != "command_list" and arg != "COMMANDS"
        }
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
        prompt = command_selection(step_number=step_number, prompt={})
    elif prompt_type == "Prompt":
        prompt = prompt_selection(step_number=step_number, prompt={})
    elif prompt_type == "Chain":
        prompt = chain_selection(step_number=step_number, prompt={})
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


def modify_step(chain_name, step, agents):
    step_number = step["step"]
    agent_name = step["agent_name"]
    prompt_type = step["prompt_type"]
    step_prompt = step["prompt"]
    modify_step_number = st.number_input(
        "Step Number",
        min_value=1,
        step=1,
        value=step_number,
        key=f"step_num_{step_number}",
    )
    modify_agent_name = st.selectbox(
        "Select Agent",
        options=[""] + [agent["name"] for agent in agents],
        index=([agent["name"] for agent in agents].index(agent_name) + 1)
        if agent_name in [agent["name"] for agent in agents]
        else 0,
        key=f"agent_name_{step_number}",
    )
    modify_prompt_type = st.selectbox(
        "Select Step Type",
        options=["", "Command", "Prompt", "Chain"],
        index=["", "Command", "Prompt", "Chain"].index(prompt_type),
        key=f"prompt_type_{step_number}",
    )
    if prompt_type == "Command":
        prompt = command_selection(step_number=step_number, prompt=step_prompt)
    elif prompt_type == "Prompt":
        prompt = prompt_selection(step_number=step_number, prompt=step_prompt)
    elif prompt_type == "Chain":
        prompt = chain_selection(step_number=step_number, prompt=step_prompt)
    else:
        prompt = {}
    if st.button("Modify Step", key=f"modify_step_{step_number}"):
        if chain_name and step_number and agent_name and prompt_type and prompt:
            ApiClient.update_step(
                chain_name=chain_name,
                step_number=modify_step_number,
                agent_name=modify_agent_name,
                prompt_type=modify_prompt_type,
                prompt=prompt,
            )
            st.success(f"Step modified in chain '{chain_name}'.")
            st.experimental_rerun()
        else:
            st.error("All fields are required.")
