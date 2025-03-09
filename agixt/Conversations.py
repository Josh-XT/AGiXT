from datetime import datetime
import logging
from DB import (
    Conversation,
    Agent,
    Message,
    User,
    get_session,
)
from Globals import getenv, DEFAULT_USER
from sqlalchemy.sql import func
from MagicalAuth import convert_time

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


def get_conversation_id_by_name(conversation_name, user_id):
    user_id = str(user_id)
    session = get_session()
    user = session.query(User).filter(User.id == user_id).first()
    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.name == conversation_name,
            Conversation.user_id == user_id,
        )
        .first()
    )
    if not conversation:
        c = Conversations(conversation_name=conversation_name, user=user.email)
        conversation_id = c.get_conversation_id()
    else:
        conversation_id = str(conversation.id)
    session.close()
    return conversation_id


def get_conversation_name_by_id(conversation_id, user_id):
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name("-", user_id)
        return "-"
    session = get_session()
    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .first()
    )
    if not conversation:
        session.close()
        return "-"
    conversation_name = conversation.name
    session.close()
    return conversation_name


class Conversations:
    def __init__(self, conversation_name=None, user=DEFAULT_USER):
        self.conversation_name = conversation_name
        self.user = user

    def export_conversation(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = "-"
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
        session.close()
        return history

    def get_conversations(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        # Use a LEFT OUTER JOIN to get conversations and their messages
        conversations = (
            session.query(Conversation)
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id)
            .filter(Message.id != None)  # Only get conversations with messages
            .order_by(Conversation.updated_at.desc())
            .distinct()
            .all()
        )

        conversation_list = [conversation.name for conversation in conversations]
        session.close()
        return conversation_list

    def get_conversations_with_ids(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        # Use a LEFT OUTER JOIN to get conversations and their messages
        conversations = (
            session.query(Conversation)
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id)
            .filter(Message.id != None)  # Only get conversations with messages
            .order_by(Conversation.updated_at.desc())
            .distinct()
            .all()
        )

        result = {
            str(conversation.id): conversation.name for conversation in conversations
        }
        session.close()
        return result

    def get_agent_id(self, user_id):
        session = get_session()
        agent_name = self.get_last_agent_name()
        # Get the agent's ID from the database
        # Make sure this agent belongs the the right user
        agent = (
            session.query(Agent)
            .filter(Agent.name == agent_name, Agent.user_id == user_id)
            .first()
        )
        try:
            agent_id = str(agent.id)
        except:
            agent_id = None
        session.close()
        return agent_id

    def get_conversations_with_detail(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        # Add notification check to the query
        conversations = (
            session.query(
                Conversation,
                func.count(Message.id)
                .filter(Message.notify == True)
                .label("notification_count"),
            )
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id)
            .filter(Message.id != None)
            .group_by(Conversation)
            .order_by(Conversation.updated_at.desc())
            .all()
        )
        # If the agent's company_id does not match
        result = {
            str(conversation.id): {
                "name": conversation.name,
                "agent_id": self.get_agent_id(user_id),
                "created_at": convert_time(conversation.created_at, user_id=user_id),
                "updated_at": convert_time(conversation.updated_at, user_id=user_id),
                "has_notifications": notification_count > 0,
                "summary": (
                    conversation.summary if Conversation.summary else "None available"
                ),
                "attachment_count": conversation.attachment_count,
            }
            for conversation, notification_count in conversations
        }
        session.close()
        return result

    def get_notifications(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        # Get all messages with notify=True for this user's conversations
        notifications = (
            session.query(Message, Conversation)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id, Message.notify == True)
            .order_by(Message.timestamp.desc())
            .all()
        )

        result = []
        for message, conversation in notifications:
            result.append(
                {
                    "conversation_id": str(conversation.id),
                    "conversation_name": conversation.name,
                    "message_id": str(message.id),
                    "message": message.content,
                    "role": message.role,
                    "timestamp": convert_time(message.timestamp, user_id=user_id),
                }
            )

        session.close()
        return result

    def get_conversation(self, limit=100, page=1):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = "-"
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
        else:
            # Mark all notifications as read for this conversation
            (
                session.query(Message)
                .filter(
                    Message.conversation_id == conversation.id, Message.notify == True
                )
                .update({"notify": False})
            )
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
            session.close()
            return {"interactions": []}
        return_messages = []
        for message in messages:
            msg = {
                "id": message.id,
                "role": message.role,
                "message": message.content,
                "timestamp": convert_time(message.timestamp, user_id=user_id),
                "updated_at": convert_time(message.updated_at, user_id=user_id),
                "updated_by": message.updated_by,
                "feedback_received": message.feedback_received,
            }
            return_messages.append(msg)
        session.close()
        return {"interactions": return_messages}

    def fork_conversation(self, message_id):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        # Get the original conversation
        original_conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not original_conversation:
            logging.info(f"No conversation found to fork.")
            session.close()
            return None

        # Get the target message first to get its timestamp
        target_message = (
            session.query(Message)
            .filter(
                Message.conversation_id == original_conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not target_message:
            logging.info(f"Target message not found.")
            session.close()
            return None

        # Get all messages up to and including the specified message using timestamp
        messages = (
            session.query(Message)
            .filter(
                Message.conversation_id == original_conversation.id,
                Message.timestamp <= target_message.timestamp,
            )
            .order_by(Message.timestamp.asc())
            .all()
        )

        if not messages:
            logging.info(f"No messages found in the conversation to fork.")
            session.close()
            return None

        try:
            # Create a new conversation
            new_conversation_name = f"{self.conversation_name}_fork_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            new_conversation = Conversation(name=new_conversation_name, user_id=user_id)
            session.add(new_conversation)
            session.flush()  # This will assign an id to new_conversation

            # Copy messages to the new conversation
            for message in messages:
                new_message = Message(
                    role=message.role,
                    content=message.content,
                    conversation_id=new_conversation.id,
                    timestamp=message.timestamp,
                    updated_at=message.updated_at,
                    updated_by=message.updated_by,
                    feedback_received=message.feedback_received,
                    notify=False,
                )
                session.add(new_message)

            # Set notify on the last message
            if messages:
                messages[-1].notify = True

            session.commit()
            forked_conversation_id = str(new_conversation.id)

            logging.info(
                f"Conversation forked successfully. New conversation ID: {forked_conversation_id}"
            )
            return new_conversation_name

        except Exception as e:
            logging.error(f"Error forking conversation: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def get_activities(self, limit=100, page=1):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = "-"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return {"activities": []}
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
            session.close()
            return {"activities": []}
        return_activities = []
        for message in messages:
            if message.content.startswith("[ACTIVITY]"):
                msg = {
                    "id": message.id,
                    "role": message.role,
                    "message": message.content,
                    "timestamp": message.timestamp,
                }
                return_activities.append(msg)
        # Order messages by timestamp oldest to newest
        return_activities = sorted(return_activities, key=lambda x: x["timestamp"])
        session.close()
        return {"activities": return_activities}

    def get_subactivities(self, activity_id):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = "-"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return ""
        messages = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.timestamp.asc())
            .all()
        )
        if not messages:
            session.close()
            return ""
        return_subactivities = []
        for message in messages:
            if message.content.startswith(f"[SUBACTIVITY][{activity_id}]"):
                msg = {
                    "id": message.id,
                    "role": message.role,
                    "message": message.content,
                    "timestamp": message.timestamp,
                }
                return_subactivities.append(msg)
        # Order messages by timestamp oldest to newest
        return_subactivities = sorted(
            return_subactivities, key=lambda x: x["timestamp"]
        )
        session.close()
        # Return it as a string with timestamps per subactivity in markdown format
        subactivities = "\n".join(
            [
                f"#### Activity at {subactivity['timestamp']}\n{subactivity['message']}"
                for subactivity in return_subactivities
            ]
        )
        return f"### Detailed Activities:\n{subactivities}"

    def get_activities_with_subactivities(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = "-"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return ""
        messages = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.timestamp.asc())
            .all()
        )
        if not messages:
            session.close()
            return ""
        return_activities = []
        current_activity = None
        for message in messages:
            if message.content.startswith("[ACTIVITY]"):
                if current_activity:
                    return_activities.append(current_activity)
                current_activity = {
                    "id": message.id,
                    "role": message.role,
                    "message": message.content,
                    "timestamp": message.timestamp,
                    "subactivities": [],
                }
            elif message.content.startswith("[SUBACTIVITY]"):
                if current_activity:
                    if "subactivities" not in current_activity:
                        current_activity["subactivities"] = []
                    current_activity["subactivities"].append(
                        {
                            "id": message.id,
                            "role": message.role,
                            "message": message.content,
                            "timestamp": message.timestamp,
                        }
                    )
        if current_activity:
            return_activities.append(current_activity)
        session.close()
        # Return in markdown
        activities = "\n".join(
            [
                f"### Activity at {activity['timestamp']}\n{activity['message']}\n"
                + "\n".join(
                    [
                        f"#### Subactivity at {subactivity['timestamp']}\n{subactivity['message']}"
                        for subactivity in activity["subactivities"]
                    ]
                )
                for activity in return_activities
            ]
        )
        return f"### Detailed Activities:\n{activities}"

    def new_conversation(self, conversation_content=[]):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id

        # Create a new conversation
        conversation = Conversation(name=self.conversation_name, user_id=user_id)
        session.add(conversation)
        session.commit()
        conversation_id = conversation.id

        if conversation_content:
            # Sort by timestamp to ensure chronological order
            try:
                from dateutil import parser

                # Try to sort by timestamp if available
                conversation_content = sorted(
                    conversation_content,
                    key=lambda x: (
                        parser.parse(x.get("timestamp", ""))
                        if x.get("timestamp")
                        else parser.parse("2099-01-01")
                    ),
                )
            except Exception as e:
                logging.warning(f"Could not sort by timestamp: {e}")

            # Find agent name from the first non-user message or use default
            agent_name = "XT"  # Default agent name
            for msg in conversation_content:
                if msg.get("role", "").upper() != "USER":
                    agent_name = msg.get("role")
                    break

            # Find the earliest timestamp in the conversation
            earliest_timestamp = None
            try:
                for msg in conversation_content:
                    if msg.get("timestamp"):
                        timestamp = parser.parse(msg.get("timestamp"))
                        if earliest_timestamp is None or timestamp < earliest_timestamp:
                            earliest_timestamp = timestamp

                # If we found timestamps, make the completed activity slightly earlier
                if earliest_timestamp:
                    import datetime

                    # Make it 1 second earlier than the earliest message
                    completed_activity_timestamp = (
                        earliest_timestamp - datetime.timedelta(seconds=1)
                    ).isoformat()
                else:
                    completed_activity_timestamp = None
            except:
                completed_activity_timestamp = None

            # Check if there are any subactivities and if there's already a Completed activities message
            has_subactivities = any(
                msg.get("message", "").startswith("[SUBACTIVITY]")
                for msg in conversation_content
            )

            # Check if a "Completed activities" message already exists in the import
            has_completed_activities = any(
                msg.get("message", "") == "[ACTIVITY] Completed activities."
                for msg in conversation_content
            )

            completed_activity_id = None

            # Create the "Completed activities" message only if needed and not already present
            if has_subactivities and not has_completed_activities:
                completed_activity_id = self.log_interaction(
                    role=agent_name,
                    message="[ACTIVITY] Completed activities.",
                    timestamp=completed_activity_timestamp,
                )
                logging.info(
                    f"Created completed activities with ID {completed_activity_id} and timestamp {completed_activity_timestamp}"
                )

            # Process regular messages
            for interaction in conversation_content:
                message = interaction.get("message", "")

                # Skip subactivities for now
                if message.startswith("[SUBACTIVITY]"):
                    continue

                # If this is a "Completed activities" message from the import, save its ID
                if (
                    message == "[ACTIVITY] Completed activities."
                    and not completed_activity_id
                ):
                    message_id = self.log_interaction(
                        role=interaction["role"],
                        message=message,
                        timestamp=interaction.get("timestamp"),
                    )
                    completed_activity_id = message_id
                    logging.info(
                        f"Using existing completed activities with ID {completed_activity_id}"
                    )
                else:
                    # Normal message processing
                    self.log_interaction(
                        role=interaction["role"],
                        message=message,
                        timestamp=interaction.get("timestamp"),
                    )

            # Now process subactivities, attaching to completed_activity_id
            if completed_activity_id:
                for interaction in conversation_content:
                    message = interaction.get("message", "")

                    if message.startswith("[SUBACTIVITY]"):
                        # Extract the content part after the subactivity ID
                        try:
                            # Find where the message type starts (after the second ])
                            parts = message.split("]", 2)
                            if len(parts) >= 3:
                                # Format: [SUBACTIVITY][id][TYPE] content
                                message_type_and_content = parts[2]
                                new_message = f"[SUBACTIVITY][{completed_activity_id}][{message_type_and_content}"
                            else:
                                # Fallback if format is different
                                new_message = f"[SUBACTIVITY][{completed_activity_id}] {message.split(']', 2)[-1]}"

                            self.log_interaction(
                                role=interaction["role"],
                                message=new_message,
                                timestamp=interaction.get("timestamp"),
                            )
                        except Exception as e:
                            logging.error(f"Error processing subactivity: {e}")
                            # If parsing fails, try a simpler approach
                            self.log_interaction(
                                role=interaction["role"],
                                message=f"[SUBACTIVITY][{completed_activity_id}] {message.replace('[SUBACTIVITY]', '').lstrip()}",
                                timestamp=interaction.get("timestamp"),
                            )
            response = conversation.__dict__
            response = {
                key: value for key, value in response.items() if not key.startswith("_")
            }
            if "id" not in response:
                response["id"] = conversation_id
            session.close()
            return response

    def get_thinking_id(self, agent_name):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = "-"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return None

        # Get the most recent non-thinking activity message
        current_parent_activity = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content.like("[ACTIVITY]%"),
                Message.content != "[ACTIVITY] Thinking.",
            )
            .order_by(Message.timestamp.desc())
            .first()
        )

        # Get the most recent thinking activity
        current_thinking = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == "[ACTIVITY] Thinking.",
            )
            .order_by(Message.timestamp.desc())
            .first()
        )

        # If there's a parent activity and it's more recent than the last thinking activity
        if current_parent_activity:
            if (
                not current_thinking
                or current_parent_activity.timestamp > current_thinking.timestamp
            ):
                # Create new thinking activity as we have a new parent
                thinking_id = self.log_interaction(
                    role=agent_name,
                    message="[ACTIVITY] Thinking.",
                )
                session.close()
                return str(thinking_id)

        # If we have a current thinking activity and it's the most recent,
        # or if there's no parent activity at all, reuse the existing thinking ID
        if current_thinking:
            if (
                not current_parent_activity
                or current_thinking.timestamp > current_parent_activity.timestamp
            ):
                session.close()
                return str(current_thinking.id)

        # If we have no thinking activity at all, create one
        thinking_id = self.log_interaction(
            role=agent_name,
            message="[ACTIVITY] Thinking.",
        )
        session.close()
        return str(thinking_id)

    def log_interaction(self, role, message, timestamp=None):
        message = str(message)
        if str(message).startswith("[SUBACTIVITY] "):
            try:
                last_activity_id = self.get_last_activity_id()
            except:
                last_activity_id = self.get_thinking_id(role)
            if last_activity_id:
                message = message.replace(
                    "[SUBACTIVITY] ", f"[SUBACTIVITY][{last_activity_id}] "
                )
            else:
                message = message.replace("[SUBACTIVITY] ", "[ACTIVITY] ")
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
        notify = False
        if role.lower() == "user":
            role = "USER"
        else:
            if not message.startswith("[ACTIVITY]") and not message.startswith(
                "[SUBACTIVITY]"
            ):
                notify = True
        if not conversation:
            conversation = self.new_conversation()
            session.close()
            session = get_session()
        else:
            conversation = conversation.__dict__
            conversation = {
                key: value
                for key, value in conversation.items()
                if not key.startswith("_")
            }
        if message.endswith("\n"):
            message = message[:-1]
        if message.endswith("\n"):
            message = message[:-1]
        conversation_id = self.get_conversation_id()
        try:
            new_message = Message(
                role=role,
                content=message,
                conversation_id=conversation_id,
                notify=notify,
            )
            # Use the provided timestamp if one is given
            if timestamp:
                try:
                    # Try to parse the timestamp - it might be in various formats
                    from dateutil import parser

                    parsed_time = parser.parse(timestamp)
                    new_message.timestamp = parsed_time
                    new_message.updated_at = parsed_time
                except:
                    # If parsing fails, just log it and continue with auto timestamps
                    logging.warning(f"Could not parse timestamp: {timestamp}")

        except Exception as e:
            conversation = self.new_conversation()
            session.close()
            session = get_session()
            new_message = Message(
                role=role,
                content=message,
                conversation_id=conversation_id,
                notify=notify,
            )

        session.add(new_message)
        session.commit()

        if role.lower() == "user":
            logging.info(f"{self.user}: {message}")
        else:
            if "[WARN]" in message:
                logging.warning(f"{role}: {message}")
            elif "[ERROR]" in message:
                logging.error(f"{role}: {message}")
            else:
                logging.info(f"{role}: {message}")
        message_id = str(new_message.id)
        session.close()
        return message_id

    def delete_conversation(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = "-"
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
            session.close()
            return

        session.query(Message).filter(
            Message.conversation_id == conversation.id
        ).delete()
        session.query(Conversation).filter(
            Conversation.id == conversation.id, Conversation.user_id == user_id
        ).delete()
        session.commit()
        session.close()

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
            session.close()
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
            session.close()
            return
        session.delete(message)
        session.commit()
        session.close()

    def get_message_by_id(self, message_id):
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
            session.close()
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
            logging.info(
                f"No message found with ID '{message_id}' in conversation '{self.conversation_name}'."
            )
            session.close()
            return
        session.close()
        return message.content

    def get_last_agent_name(self):
        # Get the last role in the conversation that isn't "user"
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = "-"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return "AGiXT"
        message = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .filter(Message.role != "USER")
            .filter(Message.role != "user")
            .order_by(Message.timestamp.desc())
            .first()
        )
        if not message:
            session.close()
            return "AGiXT"
        session.close()
        return message.role

    def delete_message_by_id(self, message_id):
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
            session.close()
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
            logging.info(
                f"No message found with ID '{message_id}' in conversation '{self.conversation_name}'."
            )
            session.close()
            return
        session.delete(message)
        session.commit()
        session.close()

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
            session.close()
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
            session.close()
            return
        message.feedback_received = not message.feedback_received
        session.commit()
        session.close()

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
            session.close()
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
            session.close()
            logging.info(
                f"No message found with ID '{message_id}' in conversation '{self.conversation_name}'."
            )
            return
        feedback_received = message.feedback_received
        session.close()
        return feedback_received

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
            session.close()
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
            session.close()
            return
        message.content = new_message
        session.commit()
        session.close()

    def update_message_by_id(self, message_id, new_message):
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
            session.close()
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
            logging.info(
                f"No message found with ID '{message_id}' in conversation '{self.conversation_name}'."
            )
            session.close()
            return

        # Update the message content directly
        message.content = str(new_message)  # Ensure the content is a string

        try:
            session.commit()
        except Exception as e:
            logging.error(f"Error updating message: {e}")
            session.rollback()
        finally:
            session.close()

    def get_conversation_id(self):
        if not self.conversation_name:
            conversation_name = "-"
        else:
            conversation_name = self.conversation_name
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            conversation = Conversation(name=conversation_name, user_id=user_id)
            session.add(conversation)
            session.commit()
        conversation_id = str(conversation.id)
        session.close()
        return conversation_id

    def rename_conversation(self, new_name: str):
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
            conversation = Conversation(name=self.conversation_name, user_id=user_id)
            session.add(conversation)
            session.commit()
        conversation.name = new_name
        session.commit()
        session.close()
        return new_name

    def get_last_activity_id(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == self.user).first()
        user_id = user_data.id
        if not self.conversation_name:
            self.conversation_name = "-"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return None
        last_activity = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .filter(Message.content.like("[ACTIVITY]%"))
            .order_by(Message.timestamp.desc())
            .first()
        )
        if not last_activity:
            session.close()
            return None
        last_id = last_activity.id
        session.close()
        return last_id

    def set_conversation_summary(self, summary: str):
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
            session.close()
            return ""
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation.id)
            .first()
        )
        conversation.summary = summary
        session.commit()
        session.close()
        return summary

    def get_conversation_summary(self):
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
            session.close()
            return ""
        summary = conversation.summary
        session.close()
        return summary

    def get_attachment_count(self):
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
            session.close()
            return 0
        attachment_count = conversation.attachment_count
        session.close()
        return attachment_count

    def update_attachment_count(self, count: int):
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
            session.close()
            return 0
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation.id)
            .first()
        )
        conversation.attachment_count = count
        session.commit()
        session.close()
        return count

    def increment_attachment_count(self):
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
            session.close()
            return 0
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation.id)
            .first()
        )
        conversation.attachment_count += 1
        session.commit()
        session.close()
        return conversation.attachment_count
