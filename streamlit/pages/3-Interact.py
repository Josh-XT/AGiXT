import streamlit as st
from auth_libs.Users import check_auth_status
from components.agent_selector import agent_selector
from ApiClient import ApiClient
from components.learning import learning_page
from components.verify_backend import verify_backend
from components.docs import agixt_docs

verify_backend()
# check_auth_status()

st.set_page_config(
    page_title="Interact with Agents",
    page_icon=":speech_balloon:",
    layout="wide",
)
agixt_docs()

st.header("Interact with Agents")
# Create an instance of the API Client
api_client = ApiClient()

# Fetch available prompts
prompts = api_client.get_prompts()

# Add a dropdown to select a mode
mode = st.selectbox("Select Mode", ["Prompt", "Chat", "Instruct", "Learning", "Chains"])

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = {}

# If the user selects Prompt, then show the prompt functionality
if mode == "Prompt":
    st.markdown("### Choose an Agent and Prompt")
    agent_name = agent_selector()
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
            prompt_args_values[arg] = st.text_input(arg)

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

# If the user selects Chat, then show the chat functionality


def handle_message(chat_prompt):
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
        chat_entry = [
            {"role": "USER", "message": chat_prompt},
            {"role": agent_name, "message": response},
        ]
        st.session_state["chat_history"][agent_name].extend(chat_entry)
        render_chat_history(
            chat_container=chat_container,
            chat_history=st.session_state["chat_history"][agent_name],
        )


if mode == "Chat":
    st.markdown("### Choose an Agent to Chat With")
    agent_name = agent_selector()

    # Add a checkbox for smart chat option
    smart_chat_toggle = st.checkbox("Enable Smart Chat")

    # Create a container for the chat history
    chat_container = st.container()

    # If the user has selected an agent, then fetch the chat history
    if agent_name:
        try:
            st.session_state["chat_history"] = {}
        except:
            pass

        # Fetch the chat history
        st.session_state["chat_history"][agent_name] = ApiClient.get_chat_history(
            agent_name=agent_name
        )

    # Render the chat history
    with chat_container:
        st.write(
            f'<div style="width: 80%;">',
            unsafe_allow_html=True,
        )

        def render_chat_history(chat_container, chat_history):
            chat_container.empty()
            with chat_container:
                for chat in chat_history:
                    if "role" in chat and "message" in chat:
                        st.markdown(
                            f'<div style="text-align: left; margin-bottom: 5px;"><strong>{chat["role"]}:</strong> {chat["message"]}</div>',
                            unsafe_allow_html=True,
                        )

    # Add a text input for the chat prompt
    chat_prompt = st.text_input("Enter your message", key="chat_prompt")

    # Add a button to send the chat prompt
    send_button = st.button("Send Message")

    # If the user clicks the send button or the chat_prompt has changed, then send the chat prompt to the agent
    if send_button or chat_prompt != st.session_state.get("last_chat_prompt"):
        handle_message(chat_prompt)
        st.session_state["last_chat_prompt"] = chat_prompt

# If the user selects Instruct, then show the instruct functionality
if mode == "Instruct":
    st.markdown("### Choose an Agent to Instruct")
    agent_name = agent_selector()
    # Add a checkbox for smart instruct option
    smart_instruct_toggle = st.checkbox("Enable Smart Instruct")

    # Create a container for the chat history
    instruct_container = st.container()

    # If the user has selected an agent, then fetch the chat history
    if agent_name:
        try:
            st.session_state["chat_history"] = {}
        except:
            pass

        # Fetch the chat history
        st.session_state["chat_history"][agent_name] = ApiClient.get_chat_history(
            agent_name=agent_name
        )

    # Render the chat history
    with instruct_container:
        st.write(
            f'<div style="width: 80%;">',
            unsafe_allow_html=True,
        )

        def render_chat_history1(instruct_container, chat_history):
            instruct_container.empty()
            with instruct_container:
                for chat in chat_history:
                    if "role" in chat and "message" in chat:
                        st.markdown(
                            f'<div style="text-align: left; margin-bottom: 5px;"><strong>{chat["role"]}:</strong> {chat["message"]}</div>',
                            unsafe_allow_html=True,
                        )

    # Add a text input for the instruct prompt
    instruct_prompt = st.text_input("Enter your instruction", key="instruct_prompt")

    # Add a button to send the instruct prompt
    send_button = st.button("Send Instruction")

    # If the user clicks the send button, then send the instruct prompt to the agent
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
                        agent_name=agent_name,
                        prompt=instruct_prompt,
                    )

            instruct_entry = [
                {"role": "USER", "message": instruct_prompt},
                {"role": agent_name, "message": response},
            ]
            st.session_state["chat_history"][agent_name].extend(instruct_entry)
            render_chat_history1(
                instruct_container=instruct_container,
                chat_history=st.session_state["chat_history"][agent_name],
            )
        else:
            st.error("Agent name and message are required.")

if mode == "Learning":
    learning_page()

if mode == "Chains":
    st.markdown("### Choose a Chain to Run")
    chain_names = ApiClient.get_chains()

    chain_action = "Run Chain"
    chain_name = st.selectbox("Chains", chain_names)
    user_input = st.text_input("User Input")

    if st.button("Perform Action"):
        if chain_name:
            if chain_action == "Run Chain":
                ApiClient.run_chain(chain_name=chain_name, user_input=user_input)
                responses = ApiClient.get_chain_responses(chain_name=chain_name)
                st.success(f"Chain '{chain_name}' executed.")
                st.write(responses)
        else:
            st.error("Chain name is required.")
