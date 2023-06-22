import streamlit as st
from components.selectors import agent_selection
from ApiClient import ApiClient
from components.learning import learning_page
from components.history import get_history
from components.verify_backend import verify_backend
from components.docs import agixt_docs

st.set_page_config(
    page_title="Interact with Agents",
    page_icon=":speech_balloon:",
    layout="wide",
)


verify_backend()


agixt_docs()

st.header("Interact with Agents")
# Create an instance of the API Client
api_client = ApiClient()

# Fetch available prompts
prompts = api_client.get_prompts()

# Add a dropdown to select a mode
mode = st.selectbox("Select Mode", ["Prompt", "Chat", "Instruct", "Learning", "Chains"])

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = ""

agent_name = agent_selection() if mode != "Chains" else None


with st.container():
    if agent_name:
        st.session_state["chat_history"] = get_history(agent_name=agent_name)


# If the user selects Prompt, then show the prompt functionality
if mode == "Prompt":
    st.markdown("### Choose an Agent and Prompt")
    # Add a dropdown to select a prompt
    prompt_name = st.selectbox("Choose a prompt", prompts)
    # Fetch arguments for the selected prompt
    prompt_args = api_client.get_prompt_args(prompt_name=prompt_name)

    # Add input fields for prompt arguments
    st.markdown("### Prompt Variables")
    prompt_args_values = {}
    skip_args = ["command_list", "context", "COMMANDS", "date"]
    for arg in prompt_args:
        if arg not in skip_args:
            prompt_args_values[arg] = st.text_area(arg)

    # Add a checkbox for websearch option
    websearch = st.checkbox("Enable websearch")
    websearch_depth = (
        3 if websearch else 0
    )  # Default depth is 3 if websearch is enabled

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
            shots=1,
        )

        # Print the response
        st.write(f"{agent_name}: {agent_prompt_resp}")

if mode == "Chat":
    st.markdown("### Choose an Agent to Chat With")
    smart_chat_toggle = st.checkbox("Enable Smart Chat")
    chat_prompt = st.text_area("Enter your message", key="chat_prompt")
    send_button = st.button("Send Message")

    if send_button:
        if agent_name and chat_prompt:
            with st.spinner("Thinking, please wait..."):
                if smart_chat_toggle:
                    response = ApiClient.smartchat(
                        agent_name=agent_name,
                        prompt=chat_prompt,
                        shots=3,
                    )
                else:
                    response = ApiClient.chat(agent_name=agent_name, prompt=chat_prompt)
                if response:
                    st.experimental_rerun()


if mode == "Instruct":
    st.markdown("### Choose an Agent to Instruct")
    smart_instruct_toggle = st.checkbox("Enable Smart Instruct")
    instruct_prompt = st.text_area("Enter your instruction", key="instruct_prompt")
    send_button = st.button("Send Message")

    if send_button:
        if agent_name and instruct_prompt:
            with st.spinner("Thinking, please wait..."):
                if smart_instruct_toggle:
                    response = ApiClient.smartinstruct(
                        agent_name=agent_name,
                        prompt=instruct_prompt,
                        shots=3,
                    )
                else:
                    response = ApiClient.instruct(
                        agent_name=agent_name, prompt=instruct_prompt
                    )
            if response:
                st.experimental_rerun()

if mode == "Learning":
    if agent_name:
        learning_page(agent_name)

if mode == "Chains":
    st.markdown("### Chain to Run")
    chain_names = ApiClient.get_chains()
    chain_action = "Run Chain"
    chain_name = st.selectbox("Chains", chain_names)
    from_step = st.number_input("Start from Step", min_value=1, value=1)
    all_responses = st.checkbox(
        "Show All Responses (If not checked, you will only be shown the last step's response in the chain when done.)"
    )
    user_input = st.text_area("User Input")
    # Need a checkbox for agent override
    agent_override = st.checkbox("Override Agent")
    if agent_override:
        agent_name = agent_selection()
    else:
        agent_name = ""
    if st.button("Run Chain"):
        if chain_name:
            if chain_action == "Run Chain":
                responses = ApiClient.run_chain(
                    chain_name=chain_name,
                    user_input=user_input,
                    agent_name=agent_name,
                    all_responses=all_responses,
                    from_step=from_step,
                )
                st.success(f"Chain '{chain_name}' executed.")
                st.write(responses)
        else:
            st.error("Chain name is required.")
