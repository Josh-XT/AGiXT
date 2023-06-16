from ApiClient import ApiClient
import streamlit as st
import json
from components.selectors import command_selection, prompt_selection, chain_selection


def add_new_step(chain_name, step_number, agents):
    st.markdown(f"## Add Chain Step {step_number}")
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
        prompt = command_selection(step_number=step_number)
    elif prompt_type == "Prompt":
        prompt = prompt_selection(step_number=step_number)
    elif prompt_type == "Chain":
        prompt = chain_selection(step_number=step_number)
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
        prompt = command_selection(prompt=step_prompt, step_number=step_number)
    elif prompt_type == "Prompt":
        prompt = prompt_selection(prompt=step_prompt, step_number=step_number)
    elif prompt_type == "Chain":
        prompt = chain_selection(prompt=step_prompt, step_number=step_number)
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


def modify_chain(chain_name, agents):
    if chain_name:
        chain = ApiClient.get_chain(chain_name=chain_name)
        export_button = st.download_button(
            "Export Chain",
            data=json.dumps(chain, indent=4),
            file_name=f"{chain_name}.json",
            mime="application/json",
        )
        st.markdown(f"## Modifying Chain: {chain_name}")
        if chain:
            for step in chain["steps"]:
                if step is not None:
                    new_step = modify_step(
                        chain_name=chain_name,
                        step=step,
                        agents=agents,
                    )

        if len(chain["steps"]) > 0:
            step_number = max([s["step"] for s in chain["steps"]]) + 1 if chain else 1
        else:
            step_number = 1

        add_step = add_new_step(
            chain_name=chain_name,
            step_number=step_number,
            agents=agents,
        )
    else:
        st.warning("Please select a chain to manage steps.")
