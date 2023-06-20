from ApiClient import ApiClient
import streamlit as st
import html
import re


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
        message_container = "<div class='message-container'>"
        try:
            history = ApiClient.get_chat_history(agent_name=agent_name)
            history = reversed(history)

            for item in history:
                item["message"] = html.escape(item["message"])
                item["message"] = item["message"].replace(r"\n", "<br>")

                # Check if the message is a code block
                code_block_match = re.search(r"```(.*)```", item["message"], re.DOTALL)

                if code_block_match:
                    # Extract the code block from the match object
                    code_message = code_block_match.group(1)
                    # Replace the code block in the original message with the code block wrapped in <pre><code> tags
                    item["message"] = re.sub(
                        r"```.*```",
                        f"<pre><code>{code_message}</code></pre>",
                        item["message"],
                        flags=re.DOTALL,
                    )

                message = f"{item['timestamp']}<br><b>{item['role']}:</b><br>{item['message']}"

                if agent_name in item["role"]:
                    message_container += (
                        f"<div class='message agent-message'>{message}</div>"
                    )
                else:
                    message_container += (
                        f"<div class='message user-message'>{message}</div>"
                    )

        except Exception as e:
            print(e)
        message_container += "</div>"
        st.write(message_container, unsafe_allow_html=True)
