from datetime import datetime
import logging
from DB import (
    Conversation,
    Message,
    User,
    get_session,
)
from Globals import getenv, DEFAULT_USER

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class Conversations:
    def __init__(self, conversation_name=None, user=DEFAULT_USER):
        self.conversation_name = conversation_name
        self.user = user

    def export_conversation(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = f"{str(datetime.now())} Conversation"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        history = {"interactions": []}
        if not conversation:
            return history
        messages = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .all()
        )
        for message in messages:
            interaction = {
                "role": message.role,
                "message": message.content,
                "timestamp": message.timestamp,
            }
            history["interactions"].append(interaction)
        return history

    def get_conversations(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        conversations = (
            session.query(Conversation)
            .filter(
                Conversation.user_id == user_id,
            )
            .all()
        )
        return [conversation.name for conversation in conversations]

    def get_conversation(self, limit=100, page=1):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = f"{str(datetime.now())} Conversation"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            # Create the conversation
            conversation = Conversation(name=self.conversation_name, user_id=user_id)
            session.add(conversation)
            session.commit()
        offset = (page - 1) * limit
        messages = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.timestamp.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        if not messages:
            return {"interactions": []}
        return_messages = []
        for message in messages:
            msg = {
                "id": message.id,
                "role": message.role,
                "message": message.content,
                "timestamp": message.timestamp,
                "updated_at": message.updated_at,
                "updated_by": message.updated_by,
                "feedback_received": message.feedback_received,
            }
            return_messages.append(msg)
        return {"interactions": return_messages}

    def new_conversation(self, conversation_content=[]):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        # Check if the conversation already exists for the agent
        existing_conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not existing_conversation:
            # Create a new conversation
            conversation = Conversation(name=self.conversation_name, user_id=user_id)
            session.add(conversation)
            session.commit()
            if conversation_content != []:
                for interaction in conversation_content:
                    new_message = Message(
                        role=interaction["role"],
                        content=interaction["message"],
                        conversation_id=conversation.id,
                    )
                    session.add(new_message)
        else:
            conversation = existing_conversation
        return conversation

    def log_interaction(self, role, message):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not conversation:
            conversation = self.new_conversation()
            session.close()
            session = get_session()
        try:
            new_message = Message(
                role=role,
                content=message,
                conversation_id=conversation.id,
            )
        except Exception as e:
            conversation = self.new_conversation()
            session.close()
            session = get_session()
            new_message = Message(
                role=role,
                content=message,
                conversation_id=conversation.id,
            )
        session.add(new_message)
        session.commit()
        if role.lower() == "user":
            logging.info(f"{self.user}: {message}")
        else:
            logging.info(f"{role}: {message}")

    def delete_conversation(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = f"{str(datetime.now())} Conversation"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            logging.info(f"No conversation found.")
            return

        session.query(Message).filter(
            Message.conversation_id == conversation.id
        ).delete()
        session.query(Conversation).filter(
            Conversation.id == conversation.id, Conversation.user_id == user_id
        ).delete()
        session.commit()

    def delete_message(self, message):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not conversation:
            logging.info(f"No conversation found.")
            return
        message_id = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == message,
            )
            .first()
        ).id

        message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not message:
            logging.info(
                f"No message found with ID '{message_id}' in conversation '{self.conversation_name}'."
            )
            return

        session.delete(message)
        session.commit()

    def toggle_feedback_received(self, message):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not conversation:
            logging.info(f"No conversation found.")
            return
        message_id = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == message,
            )
            .first()
        ).id

        message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not message:
            logging.info(
                f"No message found with ID '{message_id}' in conversation '{self.conversation_name}'."
            )
            return

        message.feedback_received = not message.feedback_received
        session.commit()

    def has_received_feedback(self, message):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not conversation:
            logging.info(f"No conversation found.")
            return
        message_id = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == message,
            )
            .first()
        ).id

        message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not message:
            logging.info(
                f"No message found with ID '{message_id}' in conversation '{self.conversation_name}'."
            )
            return

        return message.feedback_received

    def update_message(self, message, new_message):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not conversation:
            logging.info(f"No conversation found.")
            return
        message_id = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == message,
            )
            .first()
        ).id

        message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not message:
            logging.info(
                f"No message found with ID '{message_id}' in conversation '{self.conversation_name}'."
            )
            return

        message.content = new_message
        session.commit()

    def get_conversation_id(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            return None
        return str(conversation.id)
