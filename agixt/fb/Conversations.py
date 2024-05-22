from datetime import datetime
import yaml
import os
import logging
from Defaults import getenv, DEFAULT_USER

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class Conversations:
    def __init__(self, conversation_name=None, user=DEFAULT_USER):
        self.conversation_name = conversation_name
        self.user = user

    def export_conversation(self):
        if not self.conversation_name:
            self.conversation_name = f"{str(datetime.now())} Conversation"
        history_file = os.path.join("conversations", f"{self.conversation_name}.yaml")
        if os.path.exists(history_file):
            with open(history_file, "r") as file:
                history = yaml.safe_load(file)
            return history
        return {"interactions": []}

    def get_conversation(self, limit=100, page=1):
        history = {"interactions": []}
        try:
            history_file = os.path.join(
                "conversations", f"{self.conversation_name}.yaml"
            )
            if os.path.exists(history_file):
                with open(history_file, "r") as file:
                    history = yaml.safe_load(file)
        except:
            history = self.new_conversation()
        return history

    def get_conversations(self):
        conversation_dir = os.path.join("conversations")
        if os.path.exists(conversation_dir):
            conversations = os.listdir(conversation_dir)
            return [conversation.split(".")[0] for conversation in conversations]
        return []

    def new_conversation(self, conversation_content=[]):
        history = {"interactions": conversation_content}
        history_file = os.path.join("conversations", f"{self.conversation_name}.yaml")
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        with open(history_file, "w") as file:
            yaml.safe_dump(history, file)
        return history

    def log_interaction(self, role: str, message: str):
        history = self.get_conversation()
        history_file = os.path.join("conversations", f"{self.conversation_name}.yaml")
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
        if role.lower() == "user":
            logging.info(f"{self.user}: {message}")
        else:
            logging.info(f"{role}: {message}")

    def delete_conversation(self):
        history_file = os.path.join("conversations", f"{self.conversation_name}.yaml")
        if os.path.exists(history_file):
            os.remove(history_file)

    def delete_message(self, message):
        history = self.get_conversation()
        history["interactions"] = [
            interaction
            for interaction in history["interactions"]
            if interaction["message"] != message
        ]
        history_file = os.path.join("conversations", f"{self.conversation_name}.yaml")
        with open(history_file, "w") as file:
            yaml.safe_dump(history, file)

    def update_message(self, message, new_message):
        history = self.get_conversation()
        for interaction in history["interactions"]:
            if interaction["message"] == message:
                interaction["message"] = new_message
                break
        history_file = os.path.join("conversations", f"{self.conversation_name}.yaml")
        with open(history_file, "w") as file:
            yaml.safe_dump(history, file)
