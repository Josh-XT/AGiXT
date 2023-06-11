import streamlit as st
from ApiClient import ApiClient
from components.verify_backend import verify_backend
from components.docs import agixt_docs
from components.chain_selectors import (
    chain_selection,
    command_selection,
    prompt_selection,
    add_new_step,
    modify_step,
)

verify_backend()

st.set_page_config(
    page_title="Chain Management",
    page_icon=":chains:",
    layout="wide",
)

agixt_docs()
st.session_state = {}
st.header("Chain Management")


chain_names = ApiClient.get_chains()
agents = ApiClient.get_agents()
chain_action = st.selectbox("Action", ["Create Chain", "Modify Chain", "Delete Chain"])

if chain_action == "Create Chain":
    chain_name = st.text_input("Chain Name")
elif chain_action == "Modify Chain":
    chain_names = ApiClient.get_chains()
    selected_chain_name = st.selectbox("Select Chain", [""] + chain_names)
    if selected_chain_name:
        chain = ApiClient.get_chain(chain_name=selected_chain_name)
        st.markdown(f"## Modifying Chain: {selected_chain_name}")
        if chain:
            for step in chain["steps"]:
                if step is not None:
                    new_step = modify_step(
                        chain_name=selected_chain_name,
                        step_number=step["step"],
                        agent_name=step["agent_name"],
                        prompt_type=step["prompt_type"],
                        prompt=step["prompt"],
                    )

        if len(chain["steps"]) > 0:
            step_number = max([s["step"] for s in chain["steps"]]) + 1 if chain else 1
        else:
            step_number = 1

        st.markdown(f"## Add New Step {step_number}")
        add_step = add_new_step(
            chain_name=selected_chain_name,
            step_number=step_number,
            agents=agents,
        )
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
