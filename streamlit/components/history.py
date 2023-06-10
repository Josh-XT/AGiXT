from ApiClient import ApiClient
import streamlit as st


def get_initial_messages(agent_name):
    history = ApiClient.get_chat_history(agent_name=agent_name)
    history = reversed(history)
    messages = []
    message_id = 0

    for item in history:
        if "USER" in item.keys():
            message_id += 1
            messages.append({"id": message_id, "type": "user", "text": item["USER"]})
        else:
            message_id += 1
            messages.append(
                {"id": message_id, "type": "agent", "text": item[agent_name]}
            )

    return messages


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
            if "messages" not in st.session_state:
                st.session_state["messages"] = get_initial_messages(agent_name)

            def render_messages():
                for message in st.session_state["messages"]:
                    css_class = "user" if message["type"] == "user" else "agent"
                    display_name = "You" if message["type"] == "user" else agent_name
                    formatted_message = f"<div class='chat {css_class}'><b>{display_name}:</b><br>{message['text']}</div>"
                    st.markdown(formatted_message, unsafe_allow_html=True)
                    if st.button(f"Delete message {message['id']}"):
                        delete_message(message["id"])

            def delete_message(id):
                index = next(
                    (
                        i
                        for i, msg in enumerate(st.session_state["messages"])
                        if msg["id"] == id
                    ),
                    None,
                )
                if index is not None:
                    st.session_state["messages"].pop(index)

            def clear_all_messages():
                st.session_state["messages"].clear()

            render_messages()
            if st.button("Clear All"):
                clear_all_messages()
