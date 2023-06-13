from ApiClient import ApiClient
import streamlit as st
import html


def get_history(agent_name):
    st.markdown("### Agent History")
    st.markdown(
        "The history of the agent's interactions. The latest responses are at the top."
    )

    # Add a button to delete agent history
    if st.button("Delete Agent History"):
        ApiClient.delete_agent_history(agent_name=agent_name)
        st.success("Agent history deleted successfully.")

    # Define CSS rules for message container
    message_container_css = """
        <style>
        .message-container {
            height: 400px;
            overflow: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px;
            margin: 10px 0;
        }
        .message {
            margin-bottom: 10px;
        }
        .user-message {
            background-color: #0f0f0f;
            padding: 5px;
            border-radius: 5px;
        }
        .agent-message {
            background-color: #3a3b3c;
            color: white;
            padding: 5px;
            border-radius: 5px;
        }
        </style>
    """

    st.write(message_container_css, unsafe_allow_html=True)

    with st.container():
        # Get chat history from API
        history = ApiClient.get_chat_history(agent_name=agent_name)
        history = reversed(history)

        # Create a container for messages
        message_container = "<div class='message-container'>"

        for item in history:
            if "USER" in item.keys():
                message_container += f"<div class='message user-message'><b>You:</b><br>{item['USER']}</div>"
            else:
                if item[agent_name].startswith(f"{agent_name}:"):
                    item[agent_name] = item[agent_name][len(agent_name) + 1 :]
                item[agent_name] = item[agent_name].replace("\n", "<br>")
                item[agent_name] = html.escape(item[agent_name])
                message_container += f"<div class='message agent-message'><b>{agent_name}:</b><br>{item[agent_name]}</div>"
        message_container += "</div>"
        st.write(message_container, unsafe_allow_html=True)
