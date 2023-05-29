import streamlit as st
import auth_libs.Redirect as redir
from Config import Config
from Chain import Chain
from Extensions import Extensions
from Agent import Agent
from Prompts import Prompts
from auth_libs.Users import check_auth_status
from components.agent_selector import agent_selector

check_auth_status()

agent_name, agent = agent_selector()
CFG = Config()

st.header("Manage Chains")
st.markdown("### Predefined Injection Variables")
st.markdown(
    """
    Any of these variables can be used in command arguments or prompt arguments to inject data into the prompt. These can also be used inside of any Custom Prompt.
- `{agent_name}` will cause the agent name to be injected.
- `{context}` will cause the current context from memory to be injected.
- `{date}` will cause the current date and timestamp to be injected.
- `{COMMANDS}` will cause the available commands list to be injected and for automatic commands execution from the agent based on its suggestions.
- `{command_list}` will cause the available commands list to be injected, but will not execute any commands the AI chooses. Useful on validation steps.
- `{STEPx}` will cause the step `x` response from a chain to be injected. For example, `{STEP1}` will inject the first step's response in a chain.
"""
)

chain_action = st.selectbox("Action", ["Create Chain", "Delete Chain", "Run Chain"])
if chain_action == "Create Chain":
    chain_name = st.text_input("Chain Name")
else:
    chain_name = st.selectbox("Chains", Chain().get_chains())

if st.button("Perform Action"):
    if chain_name:
        if chain_action == "Create Chain":
            Chain().add_chain(chain_name=chain_name)
            st.success(f"Chain '{chain_name}' created.")
            st.experimental_rerun()
        elif chain_action == "Delete Chain":
            Chain().delete_chain(chain_name=chain_name)
            st.success(f"Chain '{chain_name}' deleted.")
            st.experimental_rerun()
        elif chain_action == "Run Chain":
            Chain().run_chain(chain_name=chain_name)
            st.success(f"Chain '{chain_name}' executed.")
    else:
        st.error("Chain name is required.")

st.header("Manage Chain Steps & View Responses")

chain_names = Chain().get_chains()
selected_chain_name = st.selectbox("Select Chain", [""] + chain_names)

if selected_chain_name:
    try:
        chain = Chain().get_steps(chain_name=selected_chain_name)
    except:
        st.write(selected_chain_name + " Responses: ")
        try:
            chain_response = Chain().get_step_response(
                chain_name=selected_chain_name,
            )
            if chain_response:
                st.write(chain_response)
            else:
                raise ValueError("End of responses!", "None Found!")
        except ValueError as err:
            st.write(err.args)
            loop = False
        st.stop()

    st.subheader(f"Selected Chain: {selected_chain_name}")

    def modify_step(step):
        step_number = step["step"]
        agent_name = step["agent_name"]
        prompt_type = step["prompt_type"]
        prompt = step.get("prompt", "")
        agent_config = Agent(agent_name).agent_config
        modify_step_number = st.number_input(
            "Step Number",
            min_value=1,
            step=1,
            value=step_number,
            key=f"step_num_{step_number}",
        )
        modify_agent_name = st.selectbox(
            "Select Agent",
            options=[""] + [agent["name"] for agent in CFG.get_agents()],
            index=([agent["name"] for agent in CFG.get_agents()].index(agent_name) + 1)
            if agent_name in [agent["name"] for agent in CFG.get_agents()]
            else 0,
            key=f"agent_name_{step_number}",
        )
        modify_prompt_type = st.selectbox(
            "Select Prompt Type",
            options=["", "Command", "Prompt"],
            index=["", "Command", "Prompt"].index(prompt_type),
            key=f"prompt_type_{step_number}",
        )

        if modify_prompt_type == "Command":
            available_commands = [
                cmd["friendly_name"]
                for cmd in Extensions(agent_config).get_enabled_commands()
            ]
            command_name = st.selectbox(
                "Select Command",
                [""] + available_commands,
                key=f"command_name_{step_number}",
                index=available_commands.index(prompt.get("command_name", "")) + 1
                if "command_name" in prompt
                else 0,
            )

            if command_name:
                command_args = Extensions(agent_config).get_command_args(command_name)
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
            available_prompts = Prompts().get_prompts()
            modify_prompt_name = st.selectbox(
                "Select Custom Prompt",
                [""] + available_prompts,
                key=f"prompt_name_{step_number}",
                index=available_prompts.index(prompt.get("prompt_name", "")) + 1
                if "prompt_name" in prompt
                else 0,
            )

            if modify_prompt_name:
                prompt_args = Prompts().get_prompt_args(modify_prompt_name)
                formatted_prompt_args = ", ".join(
                    [
                        f"{arg}: {st.text_input(arg, value=prompt.get(arg, ''), key=f'{arg}_{step_number}')} "
                        for arg in prompt_args
                        if arg != "context"
                        and arg != "command_list"
                        and arg != "COMMANDS"
                    ]
                )
                modify_prompt = f"{modify_prompt_name}({formatted_prompt_args})"
        else:
            modify_prompt = ""

        if st.button("Modify Step", key=f"modify_{step_number}"):
            Chain().update_step(
                selected_chain_name,
                step_number,
                modify_agent_name,
                modify_prompt_type,
                modify_prompt,
            )
            st.success(f"Step {step_number} updated in chain '{selected_chain_name}'.")
            st.experimental_rerun()
            return {
                "step": modify_step_number,
                "agent_name": modify_agent_name,
                "prompt_type": modify_prompt_type,
                "prompt": modify_prompt,
            }
        return step

    st.write("Existing Steps:")
    if chain:
        for step in chain:
            if step is not None:
                try:
                    step = modify_step(step)
                except TypeError:
                    st.error(
                        "Error loading chain step. Please check the chain configuration."
                    )

    step_number = max([s["step"] for s in chain]) + 1 if chain else 1
    agent_name = st.selectbox(
        "Select Agent",
        options=[""] + [agent["name"] for agent in CFG.get_agents()],
        index=0,
        key="add_step_agent_name",
    )
    prompt_type = st.selectbox(
        "Select Prompt Type",
        [""] + ["Command", "Prompt"],
        key="add_step_prompt_type",
    )

    if prompt_type == "Command":
        agent_config = Agent(agent_name).agent_config
        available_commands = [
            cmd["friendly_name"]
            for cmd in Extensions(agent_config).get_enabled_commands()
        ]
        command_name = st.selectbox(
            "Select Command",
            [""] + available_commands,
            key="add_step_command_name",
        )

        if command_name:
            command_args = Extensions(agent_config).get_command_args(command_name)
            formatted_command_args = ", ".join(
                [
                    f"{arg}: {st.text_input(arg, key=f'add_step_{arg}')} "
                    for arg in command_args
                    if arg != "context" and arg != "command_list" and arg != "COMMANDS"
                ]
            )
            prompt = f"{command_name}({formatted_command_args})"
    elif prompt_type == "Prompt":
        available_prompts = Prompts().get_prompts()
        prompt_name = st.selectbox(
            "Select Custom Prompt",
            [""] + available_prompts,
            key="add_step_prompt_name",
        )

        if prompt_name:
            prompt_args = Prompts().get_prompt_args(prompt_name)
            formatted_prompt_args = ", ".join(
                [
                    f"{arg}: {st.text_input(arg, key=f'add_step_{arg}')} "
                    for arg in prompt_args
                    if arg != "context" and arg != "command_list" and arg != "COMMANDS"
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

    if st.button("Perform Step Action", key="add_step_button"):
        if (
            selected_chain_name
            and step_number
            and agent_name
            and prompt_type
            and prompt
        ):
            if step_action == "Add Step":
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

                Chain().add_chain_step(
                    selected_chain_name,
                    step_number,
                    agent_name,
                    prompt_type,
                    prompt_data,
                )
                st.success(
                    f"Step {step_number} added to chain '{selected_chain_name}'."
                )
                st.experimental_rerun()
            elif step_action == "Update Step":
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

                Chain().update_step(
                    selected_chain_name,
                    step_number,
                    agent_name,
                    prompt_type,
                    prompt_data,
                )
                st.success(
                    f"Step {step_number} updated in chain '{selected_chain_name}'."
                )
                st.experimental_rerun()
            elif step_action == "Delete Step":
                Chain().delete_step(selected_chain_name, step_number)
                st.success(
                    f"Step {step_number} deleted from chain '{selected_chain_name}'."
                )
                st.experimental_rerun()
        else:
            st.error("All fields are required.")
else:
    st.warning("Please select a chain to manage steps.")
