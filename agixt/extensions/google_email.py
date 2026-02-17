from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from base64 import urlsafe_b64encode, urlsafe_b64decode
from datetime import datetime
import os
import mimetypes
import email
import logging
import requests
from fastapi import HTTPException
from Extensions import Extensions
from MagicalAuth import MagicalAuth
from Globals import getenv, install_package_if_missing

install_package_if_missing("google-api-python-client", "googleapiclient")
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

"""
Google Email Extension - Gmail access for sending and managing emails.

This extension provides full Gmail functionality including reading, sending,
and organizing emails. It requires separate OAuth authorization from the
main Google SSO connection.

Required environment variables:

- GOOGLE_CLIENT_ID: Google OAuth client ID
- GOOGLE_CLIENT_SECRET: Google OAuth client secret

Required APIs:
- Gmail API: https://console.cloud.google.com/marketplace/product/google/gmail.googleapis.com

Required scopes:
- gmail.modify: Full access to read/write/send emails
- gmail.compose: Compose emails
- gmail.send: Send emails
"""

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]
AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
PKCE_REQUIRED = False


class GoogleEmailSSO:
    """SSO handler for Google Email with Gmail-specific scopes."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("GOOGLE_CLIENT_ID")
        self.client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.email_address = None
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://oauth2.googleapis.com/token",
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
            raise Exception(f"Google Email token refresh failed: {response.text}")

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            logging.error("No access_token in refresh response")

        return token_data

    def get_user_info(self):
        uri = "https://people.googleapis.com/v1/people/me?personFields=names,emailAddresses"

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
            first_name = data["names"][0]["givenName"]
            last_name = data["names"][0]["familyName"]
            email = data["emailAddresses"][0]["value"]
            self.email_address = email
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error parsing Google user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Google",
            )


def sso(code, redirect_uri=None) -> GoogleEmailSSO:
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
        "https://accounts.google.com/o/oauth2/token",
        params={
            "code": code,
            "client_id": getenv("GOOGLE_CLIENT_ID"),
            "client_secret": getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Google access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else None
    return GoogleEmailSSO(access_token=access_token, refresh_token=refresh_token)


class google_email(Extensions):
    """
    Google Email Extension.

    This extension provides comprehensive Gmail functionality including:
    - Reading and searching emails
    - Sending emails with attachments
    - Creating drafts
    - Managing folders/labels
    - Replying to emails
    - Processing attachments

    This extension requires separate authorization with Gmail-specific scopes,
    independent from the basic Google SSO connection.
    """

    CATEGORY = "Social & Communication"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("GOOGLE_EMAIL_ACCESS_TOKEN", None)
        google_client_id = getenv("GOOGLE_CLIENT_ID")
        google_client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.timezone = getenv("TZ")
        self.auth = None

        if google_client_id and google_client_secret:
            self.commands = {
                "Gmail - Get Emails": self.get_emails,
                "Gmail - Send Email": self.send_email,
                "Gmail - Move Email to Folder": self.move_email_to_folder,
                "Gmail - Create Draft Email": self.create_draft_email,
                "Gmail - Delete Email": self.delete_email,
                "Gmail - Search Emails": self.search_emails,
                "Gmail - Reply to Email": self.reply_to_email,
                "Gmail - Process Attachments": self.process_attachments,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                    self.timezone = self.auth.get_timezone()
                except Exception as e:
                    logging.error(f"Error initializing Google Email: {str(e)}")

        self.attachments_dir = kwargs.get(
            "conversation_directory", "./WORKSPACE/attachments"
        )
        os.makedirs(self.attachments_dir, exist_ok=True)

    def authenticate(self):
        """
        Verifies that the current access token corresponds to a valid user.
        Returns Google API credentials.
        """
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="google_email")

        credentials = Credentials(
            token=self.access_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=getenv("GOOGLE_CLIENT_ID"),
            client_secret=getenv("GOOGLE_CLIENT_SECRET"),
            scopes=SCOPES,
        )
        return credentials

    async def get_emails(self, query=None, max_emails=10):
        """
        Get emails from the user's Gmail account

        Args:
            query (str): The search query to filter emails
            max_emails (int): The maximum number of emails to retrieve

        Returns:
            List[Dict]: A list of email data
        """
        try:
            credentials = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=credentials,
                always_use_jwt_access=True,
            )
            result = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_emails)
                .execute()
            )
            messages = result.get("messages", [])

            emails = []
            for message in messages:
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message["id"])
                    .execute()
                )

                # Safely extract headers
                headers = {
                    h["name"]: h["value"] for h in msg["payload"].get("headers", [])
                }

                email_data = {
                    "id": msg["id"],
                    "sender": headers.get("From", "Unknown"),
                    "subject": headers.get("Subject", "No Subject"),
                    "body": msg.get("snippet", ""),
                    "attachments": [],
                    "received_time": datetime.fromtimestamp(
                        int(msg["internalDate"]) / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }

                # Check for attachments
                parts = msg["payload"].get("parts", [])
                for part in parts:
                    if part.get("filename"):
                        email_data["attachments"].append(part["filename"])

                emails.append(email_data)

            return emails
        except Exception as e:
            logging.error(f"Error retrieving emails: {str(e)}")
            return []

    async def send_email(self, to, subject, message_text):
        """
        Send an email from the user's Gmail account

        Args:
            to (str): The email address of the recipient
            subject (str): The subject of the email
            message_text (str): The body of the email

        Returns:
            str: The result of sending the email
        """
        try:
            credentials = self.authenticate()
            service = build("gmail", "v1", credentials=credentials)

            message = MIMEMultipart()
            message["to"] = to
            message["subject"] = subject

            msg = MIMEText(message_text)
            message.attach(msg)

            raw = urlsafe_b64encode(message.as_bytes()).decode()
            send_message = {"raw": raw}
            service.users().messages().send(userId="me", body=send_message).execute()

            return "Email sent successfully."
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
            return f"Failed to send email: {str(e)}"

    async def move_email_to_folder(self, message_id, folder_name):
        """
        Move an email to a specific folder in the user's Gmail account

        Args:
            message_id (str): The ID of the email message
            folder_name (str): The name of the folder to move the email to

        Returns:
            str: The result of moving the email
        """
        try:
            credentials = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=credentials,
                always_use_jwt_access=True,
            )

            folders = service.users().labels().list(userId="me").execute()
            folder_id = next(
                (
                    folder["id"]
                    for folder in folders["labels"]
                    if folder["name"] == folder_name
                ),
                None,
            )

            if not folder_id:
                folder_data = {"name": folder_name}
                folder = (
                    service.users()
                    .labels()
                    .create(userId="me", body=folder_data)
                    .execute()
                )
                folder_id = folder["id"]

            service.users().messages().modify(
                userId="me", id=message_id, body={"addLabelIds": [folder_id]}
            ).execute()

            return f"Email moved to {folder_name} folder."
        except Exception as e:
            logging.error(f"Error moving email: {str(e)}")
            return f"Failed to move email: {str(e)}"

    async def create_draft_email(self, recipient, subject, body, attachments=None):
        """
        Create a draft email in the user's Gmail account

        Args:
            recipient (str): The email address of the recipient
            subject (str): The subject of the email
            body (str): The body of the email
            attachments (List[str]): A list of file paths to attach to the email

        Returns:
            str: The result of creating the draft email
        """
        try:
            credentials = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=credentials,
                always_use_jwt_access=True,
            )

            message = MIMEMultipart()
            message["to"] = recipient
            message["subject"] = subject

            msg = MIMEText(body)
            message.attach(msg)

            if attachments:
                for attachment in attachments:
                    content_type, encoding = mimetypes.guess_type(attachment)

                    if content_type is None or encoding is not None:
                        content_type = "application/octet-stream"

                    main_type, sub_type = content_type.split("/", 1)
                    with open(attachment, "rb") as fp:
                        msg = MIMEApplication(fp.read(), _subtype=sub_type)

                    msg.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=os.path.basename(attachment),
                    )
                    message.attach(msg)

            raw = urlsafe_b64encode(message.as_bytes()).decode()
            draft = {"message": {"raw": raw}}
            service.users().drafts().create(userId="me", body=draft).execute()

            return "Draft email created successfully."
        except Exception as e:
            logging.error(f"Error creating draft email: {str(e)}")
            return f"Failed to create draft email: {str(e)}"

    async def delete_email(self, message_id):
        """
        Delete an email from the user's Gmail account

        Args:
            message_id (str): The ID of the email message

        Returns:
            str: The result of deleting the email
        """
        try:
            credentials = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=credentials,
                always_use_jwt_access=True,
            )
            service.users().messages().delete(userId="me", id=message_id).execute()
            return "Email deleted successfully."
        except Exception as e:
            logging.error(f"Error deleting email: {str(e)}")
            return f"Failed to delete email: {str(e)}"

    async def search_emails(self, query, max_emails=10):
        """
        Search emails in the user's Gmail account

        Args:
            query (str): The search query to filter emails
            max_emails (int): The maximum number of emails to retrieve

        Returns:
            List[Dict]: A list of email data
        """
        return await self.get_emails(query=query, max_emails=max_emails)

    async def reply_to_email(self, message_id, body, attachments=None):
        """
        Reply to an email in the user's Gmail account

        Args:
            message_id (str): The ID of the email message
            body (str): The body of the reply email
            attachments (List[str]): A list of file paths to attach to the reply email

        Returns:
            str: The result of sending the reply
        """
        try:
            credentials = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=credentials,
                always_use_jwt_access=True,
            )
            message = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="raw")
                .execute()
            )
            msg_str = urlsafe_b64decode(message["raw"].encode("ASCII"))
            mime_msg = email.message_from_bytes(msg_str)

            reply_msg = MIMEMultipart()
            reply_msg["To"] = mime_msg["From"]
            reply_msg["Subject"] = f"Re: {mime_msg['Subject']}"
            reply_msg["In-Reply-To"] = mime_msg["Message-ID"]
            reply_msg["References"] = mime_msg["Message-ID"]

            reply_text = MIMEText(body)
            reply_msg.attach(reply_text)

            if attachments:
                for attachment in attachments:
                    content_type, encoding = mimetypes.guess_type(attachment)

                    if content_type is None or encoding is not None:
                        content_type = "application/octet-stream"

                    main_type, sub_type = content_type.split("/", 1)
                    with open(attachment, "rb") as fp:
                        attach_msg = MIMEApplication(fp.read(), _subtype=sub_type)

                    attach_msg.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=os.path.basename(attachment),
                    )
                    reply_msg.attach(attach_msg)

            raw = urlsafe_b64encode(reply_msg.as_bytes()).decode()
            send_message = {"raw": raw}
            service.users().messages().send(userId="me", body=send_message).execute()

            return "Reply sent successfully."
        except Exception as e:
            logging.error(f"Error replying to email: {str(e)}")
            return f"Failed to send reply: {str(e)}"

    async def process_attachments(self, message_id):
        """
        Process attachments from an email in the user's Gmail account

        Args:
            message_id (str): The ID of the email message

        Returns:
            List[str]: A list of file paths to the saved attachments
        """
        try:
            credentials = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=credentials,
                always_use_jwt_access=True,
            )
            message = (
                service.users().messages().get(userId="me", id=message_id).execute()
            )
            saved_attachments = []

            parts = message["payload"].get("parts", [])
            for part in parts:
                if part.get("filename"):
                    attachment_id = part["body"].get("attachmentId")
                    if attachment_id:
                        attachment = (
                            service.users()
                            .messages()
                            .attachments()
                            .get(userId="me", messageId=message_id, id=attachment_id)
                            .execute()
                        )
                        data = urlsafe_b64decode(attachment["data"])

                        attachment_path = os.path.join(
                            self.attachments_dir, part["filename"]
                        )
                        with open(attachment_path, "wb") as file:
                            file.write(data)
                        saved_attachments.append(attachment_path)

            return saved_attachments
        except Exception as e:
            logging.error(f"Error processing attachments: {str(e)}")
            return []
