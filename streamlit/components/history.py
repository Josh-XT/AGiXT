from ApiClient import ApiClient
import streamlit as st


def get_history(agent_name):
    st.markdown("### Agent History")
    st.markdown(
        "The history of the agent's interactions.  The latest responses are at the top."
    )
    with st.container():
        st.markdown(
            """
            <style>
            .chat {
                border-radius: 5px;
                padding: 10px;
                margin: 10px 0;
            }
            .chat.user {
                background-color: #0f0f0f;
            }
            .chat.agent {
                background-color: #3A3B3C;
                color: white;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        if agent_name:
            history = ApiClient.get_chat_history(agent_name=agent_name)
            history = reversed(history)
            if history:
                for item in history:
                    if "USER" in item.keys():
                        st.markdown(
                            f"<div class='chat user'><b>You:</b><br> {item['USER']}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        if item[agent_name].startswith(f"{agent_name}:"):
                            item[agent_name] = item[agent_name][len(agent_name) + 1 :]
                        item[agent_name].replace("\n", "<br>")
                        st.markdown(
                            f"<div class='chat agent'><b>{agent_name}:</b><br>{item[agent_name]}</div>",
                            unsafe_allow_html=True,
                        )
