from datetime import datetime
import yaml
import os


def export_conversation(conversation_name=None, agent_name=None, user="USER"):
    if not conversation_name:
        conversation_name = f"{str(datetime.now())} Conversation"
    history_file = os.path.join("conversations", f"{conversation_name}.yaml")
    if os.path.exists(history_file):
        with open(history_file, "r") as file:
            history = yaml.safe_load(file)
        return history
    return {"interactions": []}


def get_conversation(
    conversation_name=None, limit=100, page=1, agent_name=None, user="USER"
):
    history = {"interactions": []}
    try:
        history_file = os.path.join("conversations", f"{conversation_name}.yaml")
        if os.path.exists(history_file):
            with open(history_file, "r") as file:
                history = yaml.safe_load(file)
    except:
        history = new_conversation(conversation_name=conversation_name)
    return history


def get_conversations(agent_name=None, user="USER"):
    conversation_dir = os.path.join("conversations")
    if os.path.exists(conversation_dir):
        conversations = os.listdir(conversation_dir)
        return [conversation.split(".")[0] for conversation in conversations]
    return []


def new_conversation(
    conversation_name, agent_name=None, conversation_content=[], user="USER"
):
    history = {"interactions": conversation_content}
    history_file = os.path.join("conversations", f"{conversation_name}.yaml")
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    with open(history_file, "w") as file:
        yaml.safe_dump(history, file)
    return history


def log_interaction(
    role: str, message: str, conversation_name=None, agent_name=None, user="USER"
):
    history = get_conversation(conversation_name=conversation_name)
    history_file = os.path.join("conversations", f"{conversation_name}.yaml")
    if not os.path.exists(history_file):
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


def delete_history(conversation_name=None, agent_name=None, user="USER"):
    history_file = os.path.join("conversations", f"{conversation_name}.yaml")
    if os.path.exists(history_file):
        os.remove(history_file)


def delete_message(message, conversation_name=None, agent_name=None, user="USER"):
    if conversation_name:
        history = get_conversation(
            agent_name=agent_name, conversation_name=conversation_name
        )
        history["interactions"] = [
            interaction
            for interaction in history["interactions"]
            if interaction["message"] != message
        ]
        history_file = os.path.join("conversations", f"{conversation_name}.yaml")
        with open(history_file, "w") as file:
            yaml.safe_dump(history, file)


def update_message(
    message, new_message, conversation_name=None, agent_name=None, user="USER"
):
    if conversation_name:
        history = get_conversation(
            agent_name=agent_name, conversation_name=conversation_name
        )
        for interaction in history["interactions"]:
            if interaction["message"] == message:
                interaction["message"] = new_message
                break
        history_file = os.path.join("conversations", f"{conversation_name}.yaml")
        with open(history_file, "w") as file:
            yaml.safe_dump(history, file)
