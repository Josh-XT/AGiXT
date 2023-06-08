import streamlit as st
from ApiClient import ApiClient
import logging
from auth_libs.Users import check_auth_status
from components.verify_backend import verify_backend
from components.docs import agixt_docs

verify_backend()


st.set_page_config(
    page_title="Chain Management",
    page_icon=":chains:",
    layout="wide",
)

# check_auth_status()
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
else:
    chain_name = st.selectbox("Chains", chain_names)

if st.button("Perform Action"):
    if chain_name:
        if chain_action == "Create Chain":
            ApiClient.add_chain(chain_name=chain_name)
            st.success(f"Chain '{chain_name}' created.")
            # st.experimental_rerun()
        elif chain_action == "Delete Chain":
            ApiClient.delete_chain(chain_name=chain_name)
            st.success(f"Chain '{chain_name}' deleted.")
            # st.experimental_rerun()
        elif chain_action == "Modify Chain":
            try:
                chain = ApiClient.get_chain(chain_name=chain_name)
                if "chain" in chain:
                    chain = chain["chain"]
            except:
                st.write(chain_name + " Responses: ")
                try:
                    if "_responses" in chain_name:
                        chain_commands_executed = ApiClient.get_chain_responses(
                            chain_name=chain_name.replace("_responses", "")
                        )
                    else:
                        chain_commands_executed = False
                    chain_response = ApiClient.get_chain_responses(
                        chain_name=chain_name,
                    )
                    if chain_response and chain_commands_executed:
                        for exec in chain_commands_executed["steps"]:
                            logging.info("----------exec: " + str(exec["step"]))
                            logging.info(
                                "----------Chain_Response " + str(chain_response["1"])
                            )
                            st.write(exec)
                            st.write(chain_response[str(exec["step"])])
                    elif chain_response:
                        st.write(chain_response)
                    else:
                        raise ValueError("End of responses!", "None Found!")
                except ValueError as err:
                    st.write(err.args)
                    loop = False
                st.stop()

            st.subheader(f"Selected Chain: {chain_name}")

            def modify_step(step):
                step_number = step["step"]
                with st.form(f"chain_step_{step_number}"):
                    agent_name = step["agent_name"]
                    prompt_type = step["prompt_type"]
                    prompt = step.get("prompt", "")
                    st.session_state[
                        f"selected_agent_{step_number}"
                    ] = st.session_state.get(
                        f"selected_agent_{step_number}", agent_name
                    )

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
                        index=(
                            [agent["name"] for agent in agents].index(
                                st.session_state[f"selected_agent_{step_number}"]
                            )
                            + 1
                        )
                        if st.session_state[f"selected_agent_{step_number}"]
                        in [agent["name"] for agent in agents]
                        else 0,
                        key=f"agent_name_{step_number}",
                    )

                    if (
                        modify_agent_name
                        != st.session_state[f"selected_agent_{step_number}"]
                    ):
                        st.session_state[
                            f"selected_agent_{step_number}"
                        ] = modify_agent_name

                    modify_prompt_type = st.selectbox(
                        "Select Prompt Type",
                        options=["", "Command", "Prompt"],
                        index=["", "Command", "Prompt"].index(prompt_type),
                        key=f"prompt_type_{step_number}",
                    )

                    if modify_prompt_type == "Command":
                        available_commands = [cmd[0] for cmd in agent_commands]
                        command_name = st.selectbox(
                            "Select Command",
                            [""] + available_commands,
                            key=f"command_name_{step_number}",
                            index=available_commands.index(
                                prompt.get("command_name", "")
                            )
                            + 1
                            if "command_name" in prompt
                            else 0,
                        )

                        if command_name:
                            command_args = ApiClient.get_command_args(command_name)
                            formatted_command_args = ", ".join(
                                [
                                    f"{arg}: {st.text_input(arg, value=prompt.get(arg, ''), key=f'{arg}_{step_number}')} "
                                    for arg in command_args
                                    if arg != "context"
                                    and arg != "command_list"
                                    and arg != "COMMANDS"
                                ]
                            )
                            modify_prompt = f"{command_name}({formatted_command_args})"
                    elif modify_prompt_type == "Prompt":
                        available_prompts = ApiClient.get_prompts()
                        modify_prompt_name = st.selectbox(
                            "Select Custom Prompt",
                            [""] + available_prompts,
                            key=f"prompt_name_{step_number}",
                            index=available_prompts.index(prompt.get("prompt_name", ""))
                            + 1
                            if "prompt_name" in prompt
                            else 0,
                        )

                        if modify_prompt_name:
                            prompt_args = ApiClient.get_prompt_args(modify_prompt_name)
                            if prompt_args:
                                if isinstance(prompt_args, str):
                                    prompt_args = [prompt_args]
                                try:
                                    modify_prompt["prompt_name"] = modify_prompt_name
                                    for arg in prompt_args:
                                        if (
                                            arg != "context"
                                            and arg != "command_list"
                                            and arg != "COMMANDS"
                                        ):
                                            modify_prompt[arg] = st.text_input(
                                                arg,
                                                value=prompt.get(arg, "")
                                                if arg in prompt
                                                else "",
                                                key=f"{arg}_{step_number}",
                                            )
                                except:
                                    pass
                    else:
                        modify_prompt = ""
                    submit = st.form_submit_button("Modify Step")
                    if submit:
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

                        ApiClient.update_step(
                            chain_name=chain_name,
                            step_number=step_number,
                            agent_name=modify_agent_name,
                            prompt_type=modify_prompt_type,
                            prompt=modify_prompt,
                        )
                        st.success(
                            f"Step {step_number} updated in chain '{chain_name}'."
                        )
                        # st.experimental_rerun()
                    return step

            st.write("Existing Steps:")
            if chain:
                for step in chain["steps"]:
                    if step is not None:
                        try:
                            step = modify_step(step)
                        except TypeError:
                            st.error(
                                "Error loading chain step. Please check the chain configuration."
                            )
            if len(chain["steps"]) > 0:
                step_number = (
                    max([s["step"] for s in chain["steps"]]) + 1 if chain else 1
                )
            else:
                step_number = 1

            with st.form("add_step_form"):
                new_step_number = st.number_input(
                    "Step Number",
                    min_value=1,
                    step=1,
                    value=step_number,
                    key=f"step_num_{step_number}",
                )
                agent_name = st.selectbox(
                    "Select Agent",
                    options=[""] + [agent["name"] for agent in agents],
                    index=0,
                    key="add_step_agent_name",
                )
                prompt_type = st.selectbox(
                    "Select Prompt Type",
                    [""] + ["Command", "Prompt"],
                    key="add_step_prompt_type",
                )
                if prompt_type == "Command":
                    available_commands = [cmd[0] for cmd in agent_commands]
                    command_name = st.selectbox(
                        "Select Command",
                        [""] + available_commands,
                        key="add_step_command_name",
                    )

                    if command_name:
                        command_args = ApiClient.get_command_args(
                            command_name=command_name
                        )
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
                            **formatted_command_args,
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
                        prompt = f"{prompt_name}({formatted_prompt_args})"
                else:
                    prompt = ""

                step_action = st.selectbox(
                    "Action",
                    ["Add Step", "Update Step", "Delete Step"],
                    key="add_step_action",
                )

                submit = st.form_submit_button("Perform Step Action")
                if submit:
                    if (
                        chain_name
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
                                    prompt_data[arg] = st.session_state[
                                        f"add_step_{arg}"
                                    ]
                        elif prompt_type == "Prompt":
                            prompt_data["prompt_name"] = prompt_name
                            for arg in prompt_args:
                                if (
                                    arg != "context"
                                    and arg != "command_list"
                                    and arg != "COMMANDS"
                                ):
                                    prompt_data[arg] = st.session_state[
                                        f"add_step_{arg}"
                                    ]
                        elif step_action == "Update Step":
                            if prompt_type == "Command":
                                prompt_data = {"command_name": command_name}
                                for arg in command_args:
                                    if (
                                        arg != "context"
                                        and arg != "command_list"
                                        and arg != "COMMANDS"
                                    ):
                                        prompt_data[arg] = st.session_state[
                                            f"add_step_{arg}"
                                        ]
                            elif prompt_type == "Prompt":
                                prompt_data = {"prompt_name": prompt_name}
                                for arg in prompt_args:
                                    if (
                                        arg != "context"
                                        and arg != "command_list"
                                        and arg != "COMMANDS"
                                    ):
                                        prompt_data[arg] = st.session_state[
                                            f"add_step_{arg}"
                                        ]

                            ApiClient.update_step(
                                chain_name=chain_name,
                                step_number=step_number,
                                agent_name=agent_name,
                                prompt_type=prompt_type,
                                prompt=prompt_data,
                            )
                            st.success(
                                f"Step {step_number} updated in chain '{chain_name}'."
                            )
                            # st.experimental_rerun()
                        elif step_action == "Delete Step":
                            ApiClient.delete_step(chain_name, step_number)
                            st.success(
                                f"Step {step_number} deleted from chain '{chain_name}'."
                            )
                            # st.experimental_rerun()
                    else:
                        st.error("All fields are required.")

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
