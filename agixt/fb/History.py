from datetime import datetime
import yaml
import os


def export_conversation(agent_name, conversation_name=None):
    if not conversation_name:
        conversation_name = f"{agent_name} History"
    history_file = os.path.join(
        "conversations", agent_name, f"{conversation_name}.yaml"
    )
    if os.path.exists(history_file):
        with open(history_file, "r") as file:
            history = yaml.safe_load(file)
        return history
    return {"interactions": []}


def get_conversation(agent_name, conversation_name=None, limit=100, page=1):
    if not conversation_name:
        conversation_name = f"{agent_name} History"
    history_file = os.path.join(
        "conversations", agent_name, f"{conversation_name}.yaml"
    )
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    if os.path.exists(history_file):
        with open(history_file, "r") as file:
            history = yaml.safe_load(file)
        if not history:
            history = {"interactions": []}
        return history
    return new_conversation(agent_name=agent_name, conversation_name=conversation_name)


def get_conversations(agent_name):
    agent_dir = os.path.join("conversations", agent_name)
    if os.path.exists(agent_dir):
        conversations = os.listdir(agent_dir)
        return [conversation.split(".")[0] for conversation in conversations]
    new_conversation(agent_name=agent_name, conversation_name=f"{agent_name} History")
    return [f"{agent_name} History"]


def new_conversation(agent_name, conversation_name):
    history = {"interactions": []}
    history_file = os.path.join(
        "conversations", agent_name, f"{conversation_name}.yaml"
    )
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    with open(history_file, "w") as file:
        yaml.safe_dump(history, file)
    return history


def log_interaction(role: str, message: str, agent_name: str, conversation_name=None):
    history = get_conversation(
        agent_name=agent_name, conversation_name=conversation_name
    )
    history_file = os.path.join(
        "conversations", agent_name, f"{conversation_name}.yaml"
    )
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    if not history:
        history = {"interactions": []}
    if "interactions" not in history:
        history["interactions"] = []
    history["interactions"].append(
        {
            "role": role,
            "message": message,
            "timestamp": datetime.now().strftime("%B %d, %Y %I:%M %p"),
        }
    )
    with open(history_file, "w") as file:
        yaml.safe_dump(history, file)


def delete_history(agent_name, conversation_name=None):
    if not conversation_name:
        conversation_name = f"{agent_name} History"
    history_file = os.path.join(
        "conversations", agent_name, f"{conversation_name}.yaml"
    )

    if os.path.exists(history_file):
        os.remove(history_file)


def delete_message(agent_name, message, conversation_name=None):
    history = get_conversation(
        agent_name=agent_name, conversation_name=conversation_name
    )
    history["interactions"] = [
        interaction
        for interaction in history["interactions"]
        if interaction["message"] != message
    ]
    if not conversation_name:
        conversation_name = "history"
    history_file = os.path.join(
        "conversations", agent_name, f"{conversation_name}.yaml"
    )
    with open(history_file, "w") as file:
        yaml.safe_dump(history, file)
