import streamlit as st
from ApiClient import ApiClient
from components.verify_backend import verify_backend
from components.docs import agixt_docs

verify_backend()


st.set_page_config(
    page_title="Chain Management",
    page_icon=":chains:",
    layout="wide",
)

agixt_docs()
st.session_state = {}
st.header("Chain Management")


@st.cache_data
def cached_get_extensions():
    return ApiClient.get_extensions()


chain_names = ApiClient.get_chains()
agents = ApiClient.get_agents()
agent_commands = cached_get_extensions()
chain_action = st.selectbox("Action", ["Create Chain", "Modify Chain", "Delete Chain"])

if chain_action == "Create Chain":
    chain_name = st.text_input("Chain Name")

elif chain_action == "Modify Chain":
    chain_names = ApiClient.get_chains()
    selected_chain_name = st.selectbox("Select Chain", [""] + chain_names)

    if selected_chain_name:
        chain = ApiClient.get_chain(chain_name=selected_chain_name)
        st.markdown(f"## Modifying Chain: {selected_chain_name}")

        def modify_step(step):
            step_number = step["step"]
            agent_name = step["agent_name"]
            prompt_type = step["prompt_type"]
            prompt = step["prompt"]
            # agent_config = ApiClient.get_agentconfig(agent_name=agent_name)
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

            if modify_prompt_type == "Command":
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
                    formatted_command_args = ", ".join(
                        [
                            f"{arg}: {st.text_input(arg, value=prompt.get(arg, ''), key=f'{arg}_{step_number}')} "
                            for arg in command_args
                            if arg != "context"
                            and arg != "command_list"
                            and arg != "COMMANDS"
                        ]
                    )
                    modify_prompt = {
                        "command_name": command_name,
                        "command_args": formatted_command_args,
                    }
            elif modify_prompt_type == "Prompt":
                available_prompts = ApiClient.get_prompts()
                modify_prompt_name = st.selectbox(
                    "Select Custom Prompt",
                    [""] + available_prompts,
                    key=f"prompt_name_{step_number}",
                    index=available_prompts.index(prompt.get("prompt_name", "")) + 1
                    if "prompt_name" in prompt
                    else 0,
                )

                if modify_prompt_name:
                    prompt_args = ApiClient.get_prompt_args(
                        prompt_name=modify_prompt_name
                    )
                    if prompt_args:
                        formatted_prompt_args = ", ".join(
                            [
                                f"{arg}: {st.text_input(arg, value=prompt.get(arg, ''), key=f'{arg}_{step_number}')} "
                                for arg in prompt_args
                                if arg != "context"
                                and arg != "command_list"
                                and arg != "COMMANDS"
                            ]
                        )
                        modify_prompt = {
                            "prompt_name": modify_prompt_name,
                            "prompt_args": formatted_prompt_args,
                        }
            elif modify_prompt_type == "Chain":
                available_chains = ApiClient.get_chains()
                modify_chain_name = st.selectbox(
                    "Select Chain",
                    [""] + available_chains,
                    key=f"chain_name_{step_number}",
                    index=available_chains.index(prompt.get("chain_name", "")) + 1
                    if "chain_name" in prompt
                    else 0,
                )
                chain_user_input = st.text_input(
                    "User Input", key=f"user_input_{step_number}"
                )
                if modify_chain_name:
                    modify_prompt = {"chain_name": modify_chain_name}
            else:
                modify_prompt = ""

            if st.button("Modify Step", key=f"modify_{step_number}"):
                modify_prompt = {}
                if modify_prompt_type == "Command":
                    modify_prompt["command_name"] = command_name
                    for arg in command_args:
                        if (
                            arg != "context"
                            and arg != "command_list"
                            and arg != "COMMANDS"
                        ):
                            modify_prompt[arg] = st.session_state[
                                f"{arg}_{step_number}"
                            ]
                elif modify_prompt_type == "Prompt":
                    modify_prompt["prompt_name"] = modify_prompt_name
                    for arg in prompt_args:
                        if (
                            arg != "context"
                            and arg != "command_list"
                            and arg != "COMMANDS"
                        ):
                            modify_prompt[arg] = st.session_state[
                                f"{arg}_{step_number}"
                            ]
                elif modify_prompt_type == "Chain":
                    modify_prompt["chain_name"] = st.session_state[
                        f"chain_name_{step_number}"
                    ]
                    modify_prompt["user_input"] = st.session_state[
                        f"user_input_{step_number}"
                    ]
                else:
                    modify_prompt = ""

                ApiClient.update_step(
                    chain_name=selected_chain_name,
                    step_number=step_number,
                    agent_name=modify_agent_name,
                    prompt_type=modify_prompt_type,
                    prompt=modify_prompt,
                )
                st.success(
                    f"Step {step_number} updated in chain '{selected_chain_name}'."
                )
                st.experimental_rerun()
            return step

        st.write("Existing Steps:")
        if chain:
            for step in chain["steps"]:
                if step is not None:
                    step = modify_step(step=step)

        if len(chain["steps"]) > 0:
            step_number = max([s["step"] for s in chain["steps"]]) + 1 if chain else 1
        else:
            step_number = 1
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
            agent_config = ApiClient.get_agentconfig(agent_name=agent_name)
            available_commands = [cmd[0] for cmd in agent_commands]
            command_name = st.selectbox(
                "Select Command",
                [""] + available_commands,
                key="add_step_command_name",
            )

            if command_name:
                command_args = ApiClient.get_command_args(command_name)
                formatted_command_args = ", ".join(
                    [
                        f"{arg}: {st.text_input(arg, key=f'add_step_{arg}')} "
                        for arg in command_args
                        if arg != "context"
                        and arg != "command_list"
                        and arg != "COMMANDS"
                    ]
                )
                prompt = {
                    "command_name": command_name,
                    "command_args": formatted_command_args,
                }
        elif prompt_type == "Prompt":
            available_prompts = ApiClient.get_prompts()
            prompt_name = st.selectbox(
                "Select Custom Prompt",
                [""] + available_prompts,
                key="add_step_prompt_name",
            )

            if prompt_name:
                prompt_args = ApiClient.get_prompt_args(prompt_name)
                formatted_prompt_args = ", ".join(
                    [
                        f"{arg}: {st.text_input(arg, key=f'add_step_{arg}')} "
                        for arg in prompt_args
                        if arg != "context"
                        and arg != "command_list"
                        and arg != "COMMANDS"
                    ]
                )
                prompt = {
                    "prompt_name": prompt_name,
                    "prompt_args": formatted_prompt_args,
                }
        elif prompt_type == "Chain":
            available_chains = ApiClient.get_chains()
            run_chain_name = st.selectbox(
                "Select Chain",
                [""] + available_chains,
                key="add_step_chain_name",
            )
            user_input = st.text_input("User Input", key="add_step_user_input")

            if run_chain_name:
                prompt = {"chain_name": run_chain_name, "user_input": user_input}
        else:
            prompt = {}

        step_action = st.selectbox(
            "Action",
            ["Add Step", "Update Step", "Delete Step"],
            key="add_step_action",
        )

        if st.button("Perform Step Action", key="add_step_button"):
            if (
                selected_chain_name
                and step_number
                and agent_name
                and prompt_type
                and prompt
            ):
                prompt_data = {}
                if prompt_type == "Command":
                    prompt_data["command_name"] = command_name
                    for arg in command_args:
                        if (
                            arg != "context"
                            and arg != "command_list"
                            and arg != "COMMANDS"
                        ):
                            prompt_data[arg] = st.session_state[f"add_step_{arg}"]
                elif prompt_type == "Prompt":
                    prompt_data["prompt_name"] = prompt_name
                    for arg in prompt_args:
                        if (
                            arg != "context"
                            and arg != "command_list"
                            and arg != "COMMANDS"
                        ):
                            prompt_data[arg] = st.session_state[f"add_step_{arg}"]
                elif prompt_type == "Chain":
                    prompt_data["chain_name"] = run_chain_name
                    prompt_data["user_input"] = user_input

                if step_action == "Update Step":
                    if prompt_type == "Command":
                        prompt_data = {"command_name": command_name}
                        for arg in command_args:
                            if (
                                arg != "context"
                                and arg != "command_list"
                                and arg != "COMMANDS"
                            ):
                                prompt_data[arg] = st.session_state[f"add_step_{arg}"]
                    elif prompt_type == "Prompt":
                        prompt_data = {"prompt_name": prompt_name}
                        for arg in prompt_args:
                            if (
                                arg != "context"
                                and arg != "command_list"
                                and arg != "COMMANDS"
                            ):
                                prompt_data[arg] = st.session_state[f"add_step_{arg}"]
                    elif prompt_type == "Chain":
                        prompt_data = {
                            "chain_name": run_chain_name,
                            "user_input": user_input,
                        }

                    ApiClient.update_step(
                        chain_name=selected_chain_name,
                        step_number=step_number,
                        agent_name=agent_name,
                        prompt_type=prompt_type,
                        prompt=prompt_data,
                    )
                    st.success(
                        f"Step {step_number} updated in chain '{selected_chain_name}'."
                    )
                    st.experimental_rerun()
                elif step_action == "Delete Step":
                    ApiClient.delete_step(selected_chain_name, step_number)
                    st.success(
                        f"Step {step_number} deleted from chain '{selected_chain_name}'."
                    )
                    st.experimental_rerun()
                elif step_action == "Add Step":
                    ApiClient.add_step(
                        chain_name=selected_chain_name,
                        step_number=step_number,
                        agent_name=agent_name,
                        prompt_type=prompt_type,
                        prompt=prompt_data,
                    )
                    st.success(f"Step added to chain '{selected_chain_name}'.")
                    st.experimental_rerun()
            else:
                st.error("All fields are required.")
    else:
        st.warning("Please select a chain to manage steps.")
else:
    chain_name = st.selectbox("Chains", ApiClient.get_chains())
if chain_action == "Create Chain" or chain_action == "Delete Chain":
    action_button = st.button("Perform Action")
    if action_button:
        if chain_name:
            if chain_action == "Create Chain":
                ApiClient.add_chain(chain_name=chain_name)
                st.success(f"Chain '{chain_name}' created.")
                st.experimental_rerun()
            elif chain_action == "Delete Chain":
                ApiClient.delete_chain(chain_name=chain_name)
                st.success(f"Chain '{chain_name}' deleted.")
                st.experimental_rerun()
        else:
            st.error("Chain name is required.")

st.markdown("### Predefined Injection Variables")
st.markdown(
    """
    Any of these variables can be used in command arguments or prompt arguments to inject data into the prompt. These can also be used inside of any Custom Prompt.
- `{agent_name}` will cause the agent name to be injected.
- `{context}` will cause the current context from memory to be injected. This will only work if you have `{user_input}` in your prompt arguments for the memory search. (Only applies to prompts but is still a reserved variable name.)
- `{date}` will cause the current date and timestamp to be injected.
- `{COMMANDS}` will cause the available commands list to be injected and for automatic commands execution from the agent based on its suggestions.
- `{command_list}` will cause the available commands list to be injected, but will not execute any commands the AI chooses. Useful on validation steps.
- `{STEPx}` will cause the step `x` response from a chain to be injected. For example, `{STEP1}` will inject the first step's response in a chain.
"""
)
