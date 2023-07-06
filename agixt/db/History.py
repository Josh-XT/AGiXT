import os
import yaml
from datetime import datetime
from DBConnection import (
    Conversation,
    Message,
    Agent,
    session,
)


def export_conversation(agent_name, conversation_name=None):
    agent = session.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        print(f"Agent '{agent_name}' not found in the database.")
        return
    conversation_name = (
        f"{agent_name} History" if not conversation_name else conversation_name
    )
    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.agent_id == agent.id,
            Conversation.name == conversation_name,
        )
        .first()
    )
    if not conversation:
        print(f"No conversation found for agent '{agent_name}'.")
        return

    messages = (
        session.query(Message).filter(Message.conversation_id == conversation.id).all()
    )

    history = {"interactions": []}

    for message in messages:
        interaction = {
            "role": message.role,
            "message": message.content,
            "timestamp": message.timestamp,
        }
        history["interactions"].append(interaction)

    agent_dir = os.path.join("agents", agent_name)
    os.makedirs(agent_dir, exist_ok=True)

    history_file = os.path.join(agent_dir, "history.yaml")
    with open(history_file, "w") as file:
        yaml.dump(history, file)

    print(f"Exported conversation for agent '{agent_name}' to {history_file}.")


def get_conversations(agent_name):
    agent = session.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        print(f"Agent '{agent_name}' not found in the database.")
        return
    conversations = (
        session.query(Conversation)
        .filter(
            Conversation.agent_id == agent.id,
        )
        .all()
    )
    return [conversation.name for conversation in conversations]


def get_conversation(agent_name, conversation_name=None, limit=100, page=1):
    agent = session.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        print(f"Agent '{agent_name}' not found in the database.")
        return
    if not conversation_name:
        conversation_name = f"{agent_name} History"
    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.agent_id == agent.id,
            Conversation.name == conversation_name,
        )
        .first()
    )
    if not conversation:
        print(f"No conversation found for agent '{agent_name}'.")
        return

    messages = (
        session.query(Message).filter(Message.conversation_id == conversation.id).all()
    )
    return_messages = []
    for message in messages:
        msg = {
            "role": message.role,
            "message": message.content,
            "timestamp": message.timestamp,
        }
        return_messages.append(msg)
    return return_messages


def new_conversation(agent_name, conversation_name):
    agent = session.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        print(f"Agent '{agent_name}' not found in the database.")
        return

    # Check if the conversation already exists for the agent
    existing_conversation = (
        session.query(Conversation)
        .filter(
            Conversation.agent_id == agent.id,
            Conversation.name == conversation_name,
        )
        .first()
    )
    if existing_conversation:
        print(
            f"Conversation '{conversation_name}' already exists for agent '{agent_name}'."
        )
        return

    # Create a new conversation
    conversation = Conversation(agent_id=agent.id, name=conversation_name)
    session.add(conversation)
    session.commit()

    print(
        f"Created a new conversation: '{conversation_name}' for agent '{agent_name}'."
    )


def log_interaction(agent_name, conversation_name, role, message):
    agent = session.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        print(f"Agent '{agent_name}' not found in the database.")
        return

    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.agent_id == agent.id,
            Conversation.name == conversation_name,
        )
        .first()
    )

    if not conversation:
        # Create a new conversation if it doesn't exist
        conversation = Conversation(agent_id=agent.id, name=conversation_name)
        session.add(conversation)
        session.commit()

    timestamp = datetime.now().strftime("%B %d, %Y %I:%M %p")

    new_message = Message(
        role=role,
        content=message,
        timestamp=timestamp,
        conversation_id=conversation.id,
    )
    session.add(new_message)
    session.commit()

    print(f"Logged interaction: [{timestamp}] {role}: {message}")


def delete_history(agent_name, conversation_name=None):
    agent = session.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        print(f"Agent '{agent_name}' not found in the database.")
        return
    if not conversation_name:
        conversation_name = f"{agent_name} History"
    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.agent_id == agent.id,
            Conversation.name == conversation_name,
        )
        .first()
    )
    if not conversation:
        print(f"No conversation found for agent '{agent_name}'.")
        return

    session.query(Message).filter(Message.conversation_id == conversation.id).delete()
    session.query(Conversation).filter(Conversation.id == conversation.id).delete()
    session.commit()

    print(f"Deleted conversation '{conversation_name}' for agent '{agent_name}'.")


def delete_message(agent_name, conversation_name, message_id):
    agent = session.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        print(f"Agent '{agent_name}' not found in the database.")
        return

    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.agent_id == agent.id,
            Conversation.name == conversation_name,
        )
        .first()
    )

    if not conversation:
        print(f"No conversation found for agent '{agent_name}'.")
        return

    message = (
        session.query(Message)
        .filter(
            Message.conversation_id == conversation.id,
            Message.id == message_id,
        )
        .first()
    )

    if not message:
        print(
            f"No message found with ID '{message_id}' in conversation '{conversation_name}'."
        )
        return

    session.delete(message)
    session.commit()

    print(
        f"Deleted message with ID '{message_id}' from conversation '{conversation_name}'."
    )


# Example usage:
# delete_history("Agent1")
# delete_message("Agent1", "Agent1 History", 1)
