import streamlit as st
from auth_libs.Users import check_auth_status
from components.agent_selector import agent_selector
from ApiClient import ApiClient

st.set_page_config(
    page_title="Prompt Agent",
    page_icon=":speech_balloon:",
    layout="wide",
)

check_auth_status()
agent_name = agent_selector()

# Create an instance of the API Client
api_client = ApiClient()

# Fetch available prompts
prompts = api_client.get_prompts()

# Add a dropdown to select a prompt
prompt_name = st.selectbox("Choose a prompt", prompts)

# Fetch arguments for the selected prompt
prompt_args = api_client.get_prompt_args(prompt_name)

# Add input fields for prompt arguments
st.header("Prompt arguments")
prompt_args_values = {}
skip_args = ["command_list", "context", "COMMANDS", "date"]
for arg in prompt_args:
    if arg not in skip_args:
        prompt_args_values[arg] = st.text_input(arg)

# Add a checkbox for websearch option
websearch = st.checkbox("Enable websearch")
websearch_depth = 3 if websearch else 0  # Default depth is 3 if websearch is enabled

# Add an input field for websearch depth if websearch is enabled
if websearch:
    websearch_depth = st.number_input("Websearch depth", min_value=1, value=3)

# Add an input field for context_results if 'task' is in prompt_args
context_results = 0
if "task" in prompt_args and "context" in prompt_args:
    context_results = st.number_input("Context results", min_value=1, value=5)

# Button to execute the prompt
if st.button("Execute"):
    # Call the prompt_agent function
    agent_prompt_resp = api_client.prompt_agent(
        agent_name=agent_name,
        prompt_name=prompt_name,
        prompt_args=prompt_args_values,
        websearch=websearch,
        websearch_depth=websearch_depth,
        context_results=context_results,
    )

    # Print the response
    st.write(f"{agent_name}: {agent_prompt_resp}")
