import os
import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth

"""
Telegram Bot Extension for AGiXT

Telegram uses Bot API tokens instead of OAuth. Each bot has a unique token
that can be obtained from @BotFather on Telegram.

Required environment variables (for company-wide bots):
- TELEGRAM_BOT_TOKEN: Bot token from BotFather (optional, companies can set their own)

Each company can configure their own bot token via company settings:
- telegram_bot_token: The bot token for this company's Telegram bot

Telegram Bot API Documentation: https://core.telegram.org/bots/api
"""


def get_telegram_user_ids(company_id=None):
    """
    Get mapping of Telegram user IDs to AGiXT user IDs for a company.

    Note: Telegram user IDs are numeric. Users link their accounts by
    sending a command to the bot with their AGiXT auth token.

    Args:
        company_id: Optional company ID to filter by

    Returns:
        Dict mapping Telegram user ID (string) -> AGiXT user ID
    """
    from DB import get_session, UserOAuth, OAuthProvider

    user_ids = {}
    with get_session() as session:
        provider = session.query(OAuthProvider).filter_by(name="telegram").first()
        if not provider:
            return user_ids

        query = session.query(UserOAuth).filter_by(provider_id=provider.id)

        if company_id:
            query = query.filter(UserOAuth.company_id == company_id)

        for oauth in query.all():
            if oauth.provider_user_id:
                user_ids[oauth.provider_user_id] = str(oauth.user_id)

    return user_ids


class telegram(Extensions):
    """
    The Telegram extension provides integration with Telegram Bot API.
    This extension allows AI agents to:
    - Send messages to users and groups
    - Send photos, documents, and other media
    - Create and manage polls
    - Get updates and message history
    - Manage group chats

    The extension uses a bot token from Telegram's BotFather.
    AI agents should use this when they need to interact with Telegram
    for notifications, conversations, or group management.

    To create a bot:
    1. Message @BotFather on Telegram
    2. Send /newbot and follow the prompts
    3. Copy the bot token to your settings
    """

    CATEGORY = "Social & Communication"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.bot_token = kwargs.get("TELEGRAM_BOT_TOKEN", None)
        if not self.bot_token:
            self.bot_token = getenv("TELEGRAM_BOT_TOKEN")
        self.auth = None
        self.base_url = None

        if self.bot_token:
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
            self.commands = {
                "Telegram - Get Bot Info": self.get_bot_info,
                "Telegram - Send Message": self.send_message,
                "Telegram - Send Photo": self.send_photo,
                "Telegram - Send Document": self.send_document,
                "Telegram - Send Poll": self.send_poll,
                "Telegram - Get Updates": self.get_updates,
                "Telegram - Get Chat": self.get_chat,
                "Telegram - Get Chat Members Count": self.get_chat_members_count,
                "Telegram - Leave Chat": self.leave_chat,
                "Telegram - Set Chat Title": self.set_chat_title,
                "Telegram - Set Chat Description": self.set_chat_description,
                "Telegram - Pin Message": self.pin_message,
                "Telegram - Unpin Message": self.unpin_message,
                "Telegram - Delete Message": self.delete_message,
                "Telegram - Forward Message": self.forward_message,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Telegram client: {str(e)}")

        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )

    def _make_request(self, method: str, data: dict = None, files: dict = None):
        """
        Make a request to the Telegram Bot API.

        Args:
            method: API method name
            data: Request parameters
            files: Files to upload

        Returns:
            API response
        """
        url = f"{self.base_url}/{method}"

        try:
            if files:
                response = requests.post(url, data=data, files=files)
            else:
                response = requests.post(url, json=data)

            result = response.json()

            if not result.get("ok"):
                error_desc = result.get("description", "Unknown error")
                logging.error(f"Telegram API error: {error_desc}")
                return {"error": error_desc}

            return result.get("result")

        except Exception as e:
            logging.error(f"Telegram request failed: {str(e)}")
            return {"error": str(e)}

    async def get_bot_info(self):
        """
        Gets information about the bot.

        Returns:
            dict: Bot information including id, username, name
        """
        try:
            result = self._make_request("getMe")

            if "error" in result:
                return result

            return {
                "id": result.get("id"),
                "username": result.get("username"),
                "first_name": result.get("first_name"),
                "can_join_groups": result.get("can_join_groups", False),
                "can_read_all_group_messages": result.get(
                    "can_read_all_group_messages", False
                ),
                "supports_inline_queries": result.get("supports_inline_queries", False),
            }

        except Exception as e:
            logging.error(f"Error getting bot info: {str(e)}")
            return {"error": str(e)}

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
        reply_to_message_id: int = None,
    ):
        """
        Sends a text message to a chat.

        Args:
            chat_id (str): Chat ID or username (for public chats)
            text (str): Message text (max 4096 characters)
            parse_mode (str): HTML or Markdown parsing mode
            disable_notification (bool): Send silently
            reply_to_message_id (int): ID of message to reply to

        Returns:
            dict: Sent message information
        """
        try:
            # Telegram has a 4096 character limit
            if len(text) > 4096:
                # Split into chunks
                chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
                results = []
                for chunk in chunks:
                    result = await self.send_message(
                        chat_id, chunk, parse_mode, disable_notification
                    )
                    results.append(result)
                return results[-1]  # Return last message info

            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_notification": disable_notification,
            }

            if reply_to_message_id:
                data["reply_to_message_id"] = reply_to_message_id

            result = self._make_request("sendMessage", data)

            if "error" in result:
                return {"success": False, "error": result["error"]}

            return {
                "success": True,
                "message_id": result.get("message_id"),
                "chat_id": result.get("chat", {}).get("id"),
                "date": result.get("date"),
            }

        except Exception as e:
            logging.error(f"Error sending message: {str(e)}")
            return {"success": False, "error": str(e)}

    async def send_photo(
        self,
        chat_id: str,
        photo_path: str,
        caption: str = None,
        parse_mode: str = "HTML",
    ):
        """
        Sends a photo to a chat.

        Args:
            chat_id (str): Chat ID or username
            photo_path (str): Path to the photo file or URL
            caption (str): Photo caption (max 1024 characters)
            parse_mode (str): HTML or Markdown parsing

        Returns:
            dict: Sent message information
        """
        try:
            # Check if it's a URL or file path
            if photo_path.startswith("http://") or photo_path.startswith("https://"):
                data = {
                    "chat_id": chat_id,
                    "photo": photo_path,
                }
                if caption:
                    data["caption"] = caption[:1024]
                    data["parse_mode"] = parse_mode

                result = self._make_request("sendPhoto", data)
            else:
                # It's a file path
                full_path = os.path.join(self.WORKING_DIRECTORY, photo_path)
                if not os.path.exists(full_path):
                    if os.path.exists(photo_path):
                        full_path = photo_path
                    else:
                        return {
                            "success": False,
                            "error": f"Photo not found: {photo_path}",
                        }

                data = {"chat_id": chat_id}
                if caption:
                    data["caption"] = caption[:1024]
                    data["parse_mode"] = parse_mode

                with open(full_path, "rb") as photo_file:
                    result = self._make_request(
                        "sendPhoto", data, files={"photo": photo_file}
                    )

            if "error" in result:
                return {"success": False, "error": result["error"]}

            return {
                "success": True,
                "message_id": result.get("message_id"),
                "chat_id": result.get("chat", {}).get("id"),
            }

        except Exception as e:
            logging.error(f"Error sending photo: {str(e)}")
            return {"success": False, "error": str(e)}

    async def send_document(
        self,
        chat_id: str,
        document_path: str,
        caption: str = None,
        parse_mode: str = "HTML",
    ):
        """
        Sends a document/file to a chat.

        Args:
            chat_id (str): Chat ID or username
            document_path (str): Path to the document file or URL
            caption (str): Document caption
            parse_mode (str): HTML or Markdown parsing

        Returns:
            dict: Sent message information
        """
        try:
            if document_path.startswith("http://") or document_path.startswith(
                "https://"
            ):
                data = {
                    "chat_id": chat_id,
                    "document": document_path,
                }
                if caption:
                    data["caption"] = caption[:1024]
                    data["parse_mode"] = parse_mode

                result = self._make_request("sendDocument", data)
            else:
                full_path = os.path.join(self.WORKING_DIRECTORY, document_path)
                if not os.path.exists(full_path):
                    if os.path.exists(document_path):
                        full_path = document_path
                    else:
                        return {
                            "success": False,
                            "error": f"Document not found: {document_path}",
                        }

                data = {"chat_id": chat_id}
                if caption:
                    data["caption"] = caption[:1024]
                    data["parse_mode"] = parse_mode

                with open(full_path, "rb") as doc_file:
                    result = self._make_request(
                        "sendDocument", data, files={"document": doc_file}
                    )

            if "error" in result:
                return {"success": False, "error": result["error"]}

            return {
                "success": True,
                "message_id": result.get("message_id"),
                "chat_id": result.get("chat", {}).get("id"),
            }

        except Exception as e:
            logging.error(f"Error sending document: {str(e)}")
            return {"success": False, "error": str(e)}

    async def send_poll(
        self,
        chat_id: str,
        question: str,
        options: list,
        is_anonymous: bool = True,
        allows_multiple_answers: bool = False,
    ):
        """
        Sends a poll to a chat.

        Args:
            chat_id (str): Chat ID or username
            question (str): Poll question (max 300 characters)
            options (list): List of answer options (2-10 options, max 100 chars each)
            is_anonymous (bool): Whether poll is anonymous
            allows_multiple_answers (bool): Allow multiple choices

        Returns:
            dict: Sent poll information
        """
        try:
            if len(options) < 2:
                return {"success": False, "error": "Poll needs at least 2 options"}
            if len(options) > 10:
                options = options[:10]

            data = {
                "chat_id": chat_id,
                "question": question[:300],
                "options": [opt[:100] for opt in options],
                "is_anonymous": is_anonymous,
                "allows_multiple_answers": allows_multiple_answers,
            }

            result = self._make_request("sendPoll", data)

            if "error" in result:
                return {"success": False, "error": result["error"]}

            return {
                "success": True,
                "message_id": result.get("message_id"),
                "poll_id": result.get("poll", {}).get("id"),
            }

        except Exception as e:
            logging.error(f"Error sending poll: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_updates(self, offset: int = None, limit: int = 100):
        """
        Gets incoming updates (messages, etc.) for the bot.

        Note: This is for polling-based bots. Webhook bots receive updates automatically.

        Args:
            offset (int): Identifier of first update to return
            limit (int): Max number of updates (1-100)

        Returns:
            list: List of update objects
        """
        try:
            data = {"limit": min(limit, 100)}
            if offset:
                data["offset"] = offset

            result = self._make_request("getUpdates", data)

            if isinstance(result, dict) and "error" in result:
                return {"error": result["error"]}

            updates = []
            for update in result:
                update_obj = {
                    "update_id": update.get("update_id"),
                }

                if "message" in update:
                    msg = update["message"]
                    update_obj["type"] = "message"
                    update_obj["message"] = {
                        "message_id": msg.get("message_id"),
                        "chat_id": msg.get("chat", {}).get("id"),
                        "chat_type": msg.get("chat", {}).get("type"),
                        "from_id": msg.get("from", {}).get("id"),
                        "from_username": msg.get("from", {}).get("username"),
                        "text": msg.get("text", ""),
                        "date": msg.get("date"),
                    }

                updates.append(update_obj)

            return updates

        except Exception as e:
            logging.error(f"Error getting updates: {str(e)}")
            return {"error": str(e)}

    async def get_chat(self, chat_id: str):
        """
        Gets information about a chat.

        Args:
            chat_id (str): Chat ID or username

        Returns:
            dict: Chat information
        """
        try:
            result = self._make_request("getChat", {"chat_id": chat_id})

            if "error" in result:
                return {"error": result["error"]}

            return {
                "id": result.get("id"),
                "type": result.get("type"),
                "title": result.get("title"),
                "username": result.get("username"),
                "first_name": result.get("first_name"),
                "last_name": result.get("last_name"),
                "description": result.get("description"),
                "invite_link": result.get("invite_link"),
            }

        except Exception as e:
            logging.error(f"Error getting chat: {str(e)}")
            return {"error": str(e)}

    async def get_chat_members_count(self, chat_id: str):
        """
        Gets the number of members in a chat.

        Args:
            chat_id (str): Chat ID or username

        Returns:
            dict: Member count
        """
        try:
            result = self._make_request("getChatMemberCount", {"chat_id": chat_id})

            if isinstance(result, dict) and "error" in result:
                return {"error": result["error"]}

            return {"count": result}

        except Exception as e:
            logging.error(f"Error getting member count: {str(e)}")
            return {"error": str(e)}

    async def leave_chat(self, chat_id: str):
        """
        Leaves a group, supergroup, or channel.

        Args:
            chat_id (str): Chat ID

        Returns:
            dict: Success status
        """
        try:
            result = self._make_request("leaveChat", {"chat_id": chat_id})

            if isinstance(result, dict) and "error" in result:
                return {"success": False, "error": result["error"]}

            return {"success": True}

        except Exception as e:
            logging.error(f"Error leaving chat: {str(e)}")
            return {"success": False, "error": str(e)}

    async def set_chat_title(self, chat_id: str, title: str):
        """
        Changes the title of a chat.

        Args:
            chat_id (str): Chat ID
            title (str): New chat title (1-128 characters)

        Returns:
            dict: Success status
        """
        try:
            result = self._make_request(
                "setChatTitle", {"chat_id": chat_id, "title": title[:128]}
            )

            if isinstance(result, dict) and "error" in result:
                return {"success": False, "error": result["error"]}

            return {"success": True}

        except Exception as e:
            logging.error(f"Error setting chat title: {str(e)}")
            return {"success": False, "error": str(e)}

    async def set_chat_description(self, chat_id: str, description: str):
        """
        Changes the description of a chat.

        Args:
            chat_id (str): Chat ID
            description (str): New description (0-255 characters)

        Returns:
            dict: Success status
        """
        try:
            result = self._make_request(
                "setChatDescription",
                {"chat_id": chat_id, "description": description[:255]},
            )

            if isinstance(result, dict) and "error" in result:
                return {"success": False, "error": result["error"]}

            return {"success": True}

        except Exception as e:
            logging.error(f"Error setting chat description: {str(e)}")
            return {"success": False, "error": str(e)}

    async def pin_message(
        self, chat_id: str, message_id: int, disable_notification: bool = False
    ):
        """
        Pins a message in a chat.

        Args:
            chat_id (str): Chat ID
            message_id (int): Message ID to pin
            disable_notification (bool): Pin silently

        Returns:
            dict: Success status
        """
        try:
            result = self._make_request(
                "pinChatMessage",
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "disable_notification": disable_notification,
                },
            )

            if isinstance(result, dict) and "error" in result:
                return {"success": False, "error": result["error"]}

            return {"success": True}

        except Exception as e:
            logging.error(f"Error pinning message: {str(e)}")
            return {"success": False, "error": str(e)}

    async def unpin_message(self, chat_id: str, message_id: int = None):
        """
        Unpins a message or all pinned messages in a chat.

        Args:
            chat_id (str): Chat ID
            message_id (int): Specific message to unpin, or None for most recent

        Returns:
            dict: Success status
        """
        try:
            data = {"chat_id": chat_id}
            if message_id:
                data["message_id"] = message_id

            result = self._make_request("unpinChatMessage", data)

            if isinstance(result, dict) and "error" in result:
                return {"success": False, "error": result["error"]}

            return {"success": True}

        except Exception as e:
            logging.error(f"Error unpinning message: {str(e)}")
            return {"success": False, "error": str(e)}

    async def delete_message(self, chat_id: str, message_id: int):
        """
        Deletes a message.

        Args:
            chat_id (str): Chat ID
            message_id (int): Message ID to delete

        Returns:
            dict: Success status
        """
        try:
            result = self._make_request(
                "deleteMessage", {"chat_id": chat_id, "message_id": message_id}
            )

            if isinstance(result, dict) and "error" in result:
                return {"success": False, "error": result["error"]}

            return {"success": True}

        except Exception as e:
            logging.error(f"Error deleting message: {str(e)}")
            return {"success": False, "error": str(e)}

    async def forward_message(
        self,
        chat_id: str,
        from_chat_id: str,
        message_id: int,
        disable_notification: bool = False,
    ):
        """
        Forwards a message from one chat to another.

        Args:
            chat_id (str): Target chat ID
            from_chat_id (str): Source chat ID
            message_id (int): Message ID to forward
            disable_notification (bool): Forward silently

        Returns:
            dict: Forwarded message information
        """
        try:
            result = self._make_request(
                "forwardMessage",
                {
                    "chat_id": chat_id,
                    "from_chat_id": from_chat_id,
                    "message_id": message_id,
                    "disable_notification": disable_notification,
                },
            )

            if isinstance(result, dict) and "error" in result:
                return {"success": False, "error": result["error"]}

            return {
                "success": True,
                "message_id": result.get("message_id"),
            }

        except Exception as e:
            logging.error(f"Error forwarding message: {str(e)}")
            return {"success": False, "error": str(e)}
