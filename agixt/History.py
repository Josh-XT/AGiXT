import os
import yaml
from datetime import datetime
from DBConnection import (
    Conversation,
    Message,
    Agent,
    session,
)


def import_conversations():
    agents_dir = "agents"  # Directory containing agent folders
    for agent_name in os.listdir(agents_dir):
        agent_dir = os.path.join(agents_dir, agent_name)
        history_file = os.path.join(agent_dir, "history.yaml")

        if not os.path.exists(history_file):
            continue  # Skip agent if history file doesn't exist

        # Get agent ID from the database based on agent name
        agent = session.query(Agent).filter(Agent.name == agent_name).first()
        if not agent:
            print(f"Agent '{agent_name}' not found in the database.")
            continue

        # Load conversation history from the YAML file
        with open(history_file, "r") as file:
            history = yaml.safe_load(file)

        # Check if the conversation already exists for the agent
        existing_conversation = (
            session.query(Conversation)
            .filter(
                Conversation.agent_id == agent.id,
                Conversation.name == f"{agent_name} History",
            )
            .first()
        )
        if existing_conversation:
            continue

        # Create a new conversation
        conversation = Conversation(agent_id=agent.id, name=f"{agent_name} History")
        session.add(conversation)
        session.commit()

        for conversation_data in history["interactions"]:
            # Create a new message for the conversation
            try:
                role = conversation_data["role"]
                content = conversation_data["message"]
                timestamp = conversation_data["timestamp"]
            except KeyError:
                continue
            message = Message(
                role=role,
                content=content,
                timestamp=timestamp,
                conversation_id=conversation.id,
            )
            session.add(message)
            session.commit()

        print(f"Imported `{agent_name} History` conversation for agent '{agent_name}'.")


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


def get_conversation(agent_name, conversation_name=None):
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

    for message in messages:
        print(f"[{message.timestamp}] {message.role}: {message.content}")


def log_interaction(role, message):
    agent_name = "your_agent_name"  # Replace with the actual agent name
    agent = session.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        print(f"Agent '{agent_name}' not found in the database.")
        return

    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.agent_id == agent.id,
            Conversation.name == f"{agent_name} History",
        )
        .first()
    )
    if not conversation:
        print(f"No conversation found for agent '{agent_name}'.")
        return

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
