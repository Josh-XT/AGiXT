import os
import logging
import requests
import base64
from datetime import datetime
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from fastapi import HTTPException

"""
Microsoft Email Extension - Outlook/Exchange email functionality.

This extension provides access to Microsoft Outlook email features including
reading, sending, and managing emails. It requires separate OAuth authorization
from the main Microsoft SSO connection.

Required environment variables:

- MICROSOFT_CLIENT_ID: Microsoft OAuth client ID
- MICROSOFT_CLIENT_SECRET: Microsoft OAuth client secret

Required scopes:
- offline_access: Required for refresh tokens
- User.Read: Read user profile information
- Mail.Read: Read user's emails
- Mail.ReadWrite: Read and write emails (move, delete)
- Mail.Send: Send emails on behalf of user
"""

SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
]
AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
PKCE_REQUIRED = False


class MicrosoftEmailSSO:
    """SSO handler for Microsoft Email with mail-specific scopes."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(SCOPES),
            },
        )

        if response.status_code != 200:
            logging.error(f"Token refresh failed with response: {response.text}")
            raise Exception(f"Microsoft Email token refresh failed: {response.text}")

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            logging.error("No access_token in refresh response")

        return token_data

    def get_user_info(self):
        uri = "https://graph.microsoft.com/v1.0/me"

        if not self.access_token:
            logging.error("No access token available")

        response = requests.get(
            uri,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        try:
            data = response.json()
            first_name = data.get("givenName", "") or ""
            last_name = data.get("surname", "") or ""
            email = data.get("mail") or data.get("userPrincipalName", "")

            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error parsing Microsoft user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Microsoft",
            )


def sso(code, redirect_uri=None) -> MicrosoftEmailSSO:
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )
    response = requests.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": getenv("MICROSOFT_CLIENT_ID"),
            "client_secret": getenv("MICROSOFT_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Microsoft Email access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "Not provided")
    return MicrosoftEmailSSO(access_token=access_token, refresh_token=refresh_token)


class microsoft_email(Extensions):
    """
    Microsoft Email (Outlook) Extension.

    This extension provides comprehensive integration with Microsoft Outlook email,
    allowing AI agents to read, send, manage, and search emails.

    Features:
    - Read emails from any folder
    - Send emails with attachments
    - Create draft emails
    - Delete and move emails
    - Search emails
    - Reply to emails
    - Process email attachments

    This extension requires separate authorization with email-specific scopes,
    independent from the basic Microsoft SSO connection.
    """

    CATEGORY = "Productivity"
    _GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0/me"
    WELL_KNOWN_FOLDER_ALIASES = {
        "inbox": "inbox",
        "sent": "sentitems",
        "sentitems": "sentitems",
        "sent items": "sentitems",
        "drafts": "drafts",
        "deleted": "deleteditems",
        "deleted items": "deleteditems",
        "trash": "deleteditems",
        "junk": "junkemail",
        "junk email": "junkemail",
        "spam": "junkemail",
        "archive": "archive",
        "outbox": "outbox",
    }
    WELL_KNOWN_FOLDER_CANONICALS = set(WELL_KNOWN_FOLDER_ALIASES.values())

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("MICROSOFT_EMAIL_ACCESS_TOKEN", None)
        microsoft_client_id = getenv("MICROSOFT_CLIENT_ID")
        microsoft_client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.timezone = getenv("TZ")
        self.auth = None

        if microsoft_client_id and microsoft_client_secret:
            self.commands = {
                "Get Emails from Outlook": self.get_emails,
                "Send Email from Outlook": self.send_email,
                "Create Draft Email in Outlook": self.create_draft_email,
                "Delete Email from Outlook": self.delete_email,
                "Search Emails in Outlook": self.search_emails,
                "Reply to Email in Outlook": self.reply_to_email,
                "Move Email to Folder": self.move_email_to_folder,
                "Process Email Attachments": self.process_attachments,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                    self.timezone = self.auth.get_timezone()
                except Exception as e:
                    logging.error(
                        f"Error initializing Microsoft Email client: {str(e)}"
                    )

        self.attachments_dir = kwargs.get(
            "conversation_directory", "./WORKSPACE/attachments"
        )
        os.makedirs(self.attachments_dir, exist_ok=True)

    def verify_user(self):
        """
        Verifies that the current access token corresponds to a valid user.
        """
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(
                provider="microsoft_email"
            )

        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        if response.status_code != 200:
            raise Exception(
                f"User not found or invalid token. Status: {response.status_code}, "
                f"Response: {response.text}. Ensure the Microsoft Email extension is connected."
            )

    def _normalize_folder_segments(self, folder_name):
        """Break a folder path into normalized segments."""
        if not folder_name:
            return []

        normalized = []
        path = folder_name.replace("\\", "/")
        for index, raw_segment in enumerate(path.split("/")):
            segment = raw_segment.strip()
            if not segment:
                continue

            key = segment.lower()
            if index == 0 and key in self.WELL_KNOWN_FOLDER_ALIASES:
                normalized.append(self.WELL_KNOWN_FOLDER_ALIASES[key])
            else:
                normalized.append(segment)

        return normalized

    def _resolve_mail_folder_id(self, folder_segments, headers):
        """Resolve a folder path to its unique ID."""
        if not folder_segments:
            return None

        traversal_headers = headers.copy()
        traversal_headers.setdefault("ConsistencyLevel", "eventual")
        traversal_headers.pop("Prefer", None)

        current_id = None
        for index, segment in enumerate(folder_segments):
            if index == 0:
                direct_url = f"{self._GRAPH_BASE_URL}/mailFolders/{segment}"
                response = requests.get(direct_url, headers=traversal_headers)
                if response.status_code == 200:
                    folder_info = response.json() or {}
                    current_id = folder_info.get("id") or segment
                    if len(folder_segments) == 1:
                        return current_id
                    continue

            parent_hint = "root" if current_id is None else folder_segments[index - 1]
            search_url = (
                f"{self._GRAPH_BASE_URL}/mailFolders/{current_id}/childFolders"
                if current_id
                else f"{self._GRAPH_BASE_URL}/mailFolders"
            )
            filter_name = segment.replace("'", "''")
            params = {"$filter": f"displayName eq '{filter_name}'", "$top": "1"}
            response = requests.get(
                search_url, headers=traversal_headers, params=params
            )

            if response.status_code != 200:
                logging.error(
                    f"Failed to search for folder '{segment}' under '{parent_hint}' "
                    f"(status {response.status_code}): {response.text}"
                )
                return None

            results = response.json().get("value", [])
            if not results:
                logging.warning(
                    f"No folder named '{segment}' found under '{parent_hint}'"
                )
                return None

            current_id = results[0].get("id")
            if not current_id:
                logging.warning(
                    f"Folder search result missing id for segment '{segment}'"
                )
                return None

        return current_id

    def _build_messages_endpoint(self, folder_name, headers):
        """Build the messages endpoint for the requested folder."""
        segments = self._normalize_folder_segments(folder_name)
        if not segments:
            return f"{self._GRAPH_BASE_URL}/messages"

        if len(segments) == 1 and segments[0] in self.WELL_KNOWN_FOLDER_CANONICALS:
            return f"{self._GRAPH_BASE_URL}/mailFolders/{segments[0]}/messages"

        folder_id = self._resolve_mail_folder_id(segments, headers)
        if folder_id:
            return f"{self._GRAPH_BASE_URL}/mailFolders/{folder_id}/messages"

        logging.warning(
            f"Falling back to primary mailbox because folder '{folder_name}' could not be resolved."
        )
        return f"{self._GRAPH_BASE_URL}/messages"

    def _format_email_message(self, message):
        """Format a Graph message payload into a standardized structure."""
        if not isinstance(message, dict):
            return None

        message_id = message.get("id")
        if not message_id:
            return None

        sender_info = message.get("from") or message.get("sender") or {}
        if isinstance(sender_info, dict):
            email_address = (
                (sender_info.get("emailAddress") or {}).get("address")
                if sender_info
                else None
            )
        else:
            email_address = None

        email_address = email_address or "unknown"

        body_data = message.get("body")
        if isinstance(body_data, dict):
            body_content = body_data.get("content", "")
        elif body_data is None:
            body_content = ""
        else:
            body_content = str(body_data)

        return {
            "id": message_id,
            "subject": message.get("subject") or "(No Subject)",
            "sender": email_address,
            "received_time": message.get("receivedDateTime", ""),
            "body": body_content,
            "body_preview": message.get("bodyPreview", ""),
            "has_attachments": message.get("hasAttachments", False),
            "web_link": message.get("webLink", ""),
            "importance": message.get("importance", "normal"),
        }

    async def get_emails(self, folder_name="Inbox", max_emails=10, page_size=10):
        """
        Retrieves emails from a specified folder in the user's Outlook mailbox.

        Args:
            folder_name (str): Name of the folder to fetch emails from (e.g., "Inbox", "Sent Items")
            max_emails (int): Maximum number of emails to retrieve
            page_size (int): Number of emails to fetch per page

        Returns:
            list: List of dictionaries containing email information
        """
        try:
            self.verify_user()

            max_emails = int(max_emails)
            page_size = int(page_size) if page_size else 10

            if max_emails <= 0:
                return []

            per_page = max(1, min((page_size or 10), 100, max_emails))

            base_headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Prefer": 'outlook.body-content-type="text"',
                "ConsistencyLevel": "eventual",
            }

            folder_headers = base_headers.copy()
            folder_headers.pop("Prefer", None)

            messages_url = self._build_messages_endpoint(folder_name, folder_headers)

            emails = []
            params = {
                "$top": str(per_page),
                "$orderby": "receivedDateTime DESC",
            }
            next_link = None

            while len(emails) < max_emails:
                if next_link:
                    response = requests.get(next_link, headers=base_headers)
                else:
                    response = requests.get(
                        messages_url, headers=base_headers, params=params
                    )

                if response.status_code != 200:
                    logging.error(
                        f"Failed to fetch emails (status {response.status_code}): {response.text}"
                    )
                    break

                try:
                    payload = response.json() or {}
                except ValueError as json_err:
                    logging.error(f"Failed to parse email response JSON: {json_err}")
                    break

                messages = payload.get("value", [])
                if not messages:
                    break

                for message in messages:
                    formatted = self._format_email_message(message)
                    if formatted:
                        emails.append(formatted)
                    if len(emails) >= max_emails:
                        break

                next_link = payload.get("@odata.nextLink")
                if not next_link:
                    break

            return emails

        except Exception as e:
            logging.error(f"Error retrieving emails: {str(e)}")
            return []

    async def send_email(
        self, recipient, subject, body, attachments=None, importance="normal"
    ):
        """
        Sends an email using Outlook.

        Args:
            recipient (str): Email address of the recipient
            subject (str): Email subject
            body (str): Email content (HTML supported)
            attachments (list): Optional list of file paths to attach
            importance (str): Email importance level ("low", "normal", or "high")

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            email_data = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": body},
                    "toRecipients": [{"emailAddress": {"address": recipient}}],
                    "importance": importance,
                },
                "saveToSentItems": "true",
            }

            if attachments:
                email_data["message"]["attachments"] = []
                for attachment_path in attachments:
                    if os.path.exists(attachment_path):
                        with open(attachment_path, "rb") as file:
                            content = file.read()
                            email_data["message"]["attachments"].append(
                                {
                                    "@odata.type": "#microsoft.graph.fileAttachment",
                                    "name": os.path.basename(attachment_path),
                                    "contentBytes": base64.b64encode(content).decode(),
                                }
                            )

            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/sendMail",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=email_data,
            )

            if response.status_code == 202:
                return "Email sent successfully."
            else:
                raise Exception(f"Failed to send email: {response.text}")

        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
            return f"Failed to send email: {str(e)}"

    async def create_draft_email(
        self, recipient, subject, body, attachments=None, importance="normal"
    ):
        """
        Creates a draft email in Outlook.

        Args:
            recipient (str): Email address of the recipient
            subject (str): Email subject
            body (str): Email content (HTML supported)
            attachments (list): Optional list of file paths to attach
            importance (str): Email importance level

        Returns:
            str: Success or failure message with draft ID
        """
        try:
            self.verify_user()

            draft_data = {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body},
                "toRecipients": [{"emailAddress": {"address": recipient}}],
                "importance": importance,
            }

            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=draft_data,
            )

            if response.status_code == 201:
                draft = response.json()
                draft_id = draft.get("id")

                # Add attachments if provided
                if attachments and draft_id:
                    for attachment_path in attachments:
                        if os.path.exists(attachment_path):
                            with open(attachment_path, "rb") as file:
                                content = file.read()
                                attachment_data = {
                                    "@odata.type": "#microsoft.graph.fileAttachment",
                                    "name": os.path.basename(attachment_path),
                                    "contentBytes": base64.b64encode(content).decode(),
                                }
                                requests.post(
                                    f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}/attachments",
                                    headers={
                                        "Authorization": f"Bearer {self.access_token}",
                                        "Content-Type": "application/json",
                                    },
                                    json=attachment_data,
                                )

                return f"Draft email created successfully. Draft ID: {draft_id}"
            else:
                raise Exception(f"Failed to create draft: {response.text}")

        except Exception as e:
            logging.error(f"Error creating draft email: {str(e)}")
            return f"Failed to create draft email: {str(e)}"

    async def delete_email(self, message_id):
        """
        Deletes an email from the mailbox.

        Args:
            message_id (str): The ID of the email to delete

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

            if response.status_code == 204:
                return "Email deleted successfully."
            else:
                raise Exception(f"Failed to delete email: {response.text}")

        except Exception as e:
            logging.error(f"Error deleting email: {str(e)}")
            return f"Failed to delete email: {str(e)}"

    async def search_emails(self, query, max_results=10):
        """
        Searches for emails matching the given query.

        Args:
            query (str): Search query (supports OData filter syntax)
            max_results (int): Maximum number of results to return

        Returns:
            list: List of matching email dictionaries
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "ConsistencyLevel": "eventual",
            }

            params = {
                "$search": f'"{query}"',
                "$top": str(max_results),
                "$orderby": "receivedDateTime DESC",
            }

            response = requests.get(
                f"{self._GRAPH_BASE_URL}/messages",
                headers=headers,
                params=params,
            )

            if response.status_code == 200:
                data = response.json()
                emails = []
                for message in data.get("value", []):
                    formatted = self._format_email_message(message)
                    if formatted:
                        emails.append(formatted)
                return emails
            else:
                logging.error(f"Search failed: {response.text}")
                return []

        except Exception as e:
            logging.error(f"Error searching emails: {str(e)}")
            return []

    async def reply_to_email(self, message_id, reply_body, reply_all=False):
        """
        Replies to an email.

        Args:
            message_id (str): The ID of the email to reply to
            reply_body (str): The reply message content
            reply_all (bool): Whether to reply to all recipients

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            endpoint = "replyAll" if reply_all else "reply"
            reply_data = {
                "message": {"body": {"contentType": "HTML", "content": reply_body}}
            }

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/{endpoint}",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=reply_data,
            )

            if response.status_code == 202:
                return "Reply sent successfully."
            else:
                raise Exception(f"Failed to send reply: {response.text}")

        except Exception as e:
            logging.error(f"Error replying to email: {str(e)}")
            return f"Failed to reply to email: {str(e)}"

    async def move_email_to_folder(self, message_id, destination_folder):
        """
        Moves an email to a different folder.

        Args:
            message_id (str): The ID of the email to move
            destination_folder (str): The destination folder name or ID

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Resolve folder ID
            segments = self._normalize_folder_segments(destination_folder)
            folder_id = None

            if segments:
                if (
                    len(segments) == 1
                    and segments[0] in self.WELL_KNOWN_FOLDER_CANONICALS
                ):
                    folder_id = segments[0]
                else:
                    folder_id = self._resolve_mail_folder_id(segments, headers)

            if not folder_id:
                return f"Could not find folder: {destination_folder}"

            move_data = {"destinationId": folder_id}

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move",
                headers=headers,
                json=move_data,
            )

            if response.status_code == 201:
                return f"Email moved to {destination_folder} successfully."
            else:
                raise Exception(f"Failed to move email: {response.text}")

        except Exception as e:
            logging.error(f"Error moving email: {str(e)}")
            return f"Failed to move email: {str(e)}"

    async def process_attachments(self, message_id, save_to_directory=None):
        """
        Downloads and processes attachments from an email.

        Args:
            message_id (str): The ID of the email with attachments
            save_to_directory (str): Optional directory to save attachments

        Returns:
            list: List of saved attachment paths or attachment info
        """
        try:
            self.verify_user()

            save_dir = save_to_directory or self.attachments_dir
            os.makedirs(save_dir, exist_ok=True)

            response = requests.get(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

            if response.status_code != 200:
                raise Exception(f"Failed to get attachments: {response.text}")

            attachments = response.json().get("value", [])
            saved_files = []

            for attachment in attachments:
                if attachment.get("@odata.type") == "#microsoft.graph.fileAttachment":
                    filename = attachment.get("name", "unnamed_attachment")
                    content = attachment.get("contentBytes", "")

                    if content:
                        file_path = os.path.join(save_dir, filename)
                        with open(file_path, "wb") as f:
                            f.write(base64.b64decode(content))
                        saved_files.append(
                            {
                                "filename": filename,
                                "path": file_path,
                                "size": attachment.get("size", 0),
                                "content_type": attachment.get("contentType", ""),
                            }
                        )

            return saved_files

        except Exception as e:
            logging.error(f"Error processing attachments: {str(e)}")
            return []
