import json
import streamlit as st
from ApiClient import ApiClient
from components.verify_backend import verify_backend
from components.docs import agixt_docs
from components.chain import modify_chain

verify_backend()

st.set_page_config(
    page_title="Chain Management",
    page_icon=":chains:",
    layout="wide",
)

agixt_docs()
st.session_state = {}
chain_names = ApiClient.get_chains()
agents = ApiClient.get_agents()
st.header("Chain Management")
chain_action = st.selectbox("Action", ["Create Chain", "Modify Chain", "Delete Chain"])

if chain_action == "Create Chain":
    chain_name = st.text_input("Chain Name")
else:
    chain_name = st.selectbox("Chains", options=chain_names)

if chain_action == "Create Chain":
    action_button = st.button("Create New Chain")
    # Import Chain
    chain_file = st.file_uploader("Import Chain", type=["json"])
    if chain_file:
        chain_name = chain_file.name.split(".")[0]
        chain_content = chain_file.read().decode("utf-8")
        steps = json.loads(chain_content)
        ApiClient.import_chain(chain_name=chain_name, steps=steps)
        st.success(f"Chain '{chain_name}' added.")
        chain_file = None
    if action_button:
        if chain_name:
            ApiClient.add_chain(chain_name=chain_name)
            st.success(f"Chain '{chain_name}' created.")
            st.experimental_rerun()
        else:
            st.error("Chain name is required.")

elif chain_action == "Delete Chain":
    action_button = st.button("Delete Chain")
    if action_button:
        if chain_name:
            ApiClient.delete_chain(chain_name=chain_name)
            st.success(f"Chain '{chain_name}' deleted.")
            st.experimental_rerun()
        else:
            st.error("Chain name is required.")

elif chain_action == "Modify Chain":
    if chain_name:
        chain = modify_chain(chain_name=chain_name, agents=agents)
    else:
        st.warning("Please select a chain to manage steps.")

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
