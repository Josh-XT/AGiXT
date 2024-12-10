from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from base64 import urlsafe_b64encode, urlsafe_b64decode
from datetime import datetime, timedelta
import os
import sys
import subprocess
import mimetypes
import email
import logging
from Extensions import Extensions
from MagicalAuth import MagicalAuth
from Globals import getenv

try:
    from googleapiclient.discovery import build
except:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "google-api-python-client"]
    )
    from googleapiclient.discovery import build


class google(Extensions):
    """
    The Google extension provides comprehensive integration with Google services.
    This extension allows AI agents to:
    - Manage Gmail (read, send, move, search)
    - Handle Google Calendar events
    - Manage Google Keep notes
    - Process email attachments

    The extension requires the user to be authenticated with Google through OAuth.
    AI agents should use this when they need to interact with a user's Google account
    for tasks like scheduling meetings, sending emails, or managing notes.
    """

    def __init__(self, **kwargs):
        api_key = kwargs.get("api_key")
        self.google_auth = None
        google_client_id = getenv("GOOGLE_CLIENT_ID")
        google_client_secret = getenv("GOOGLE_CLIENT_SECRET")

        if google_client_id and google_client_secret:
            self.commands = {
                "Google - Get Emails": self.get_emails,
                "Google - Send Email": self.send_email,
                "Google - Move Email to Folder": self.move_email_to_folder,
                "Google - Create Draft Email": self.create_draft_email,
                "Google - Delete Email": self.delete_email,
                "Google - Search Emails": self.search_emails,
                "Google - Reply to Email": self.reply_to_email,
                "Google - Process Attachments": self.process_attachments,
                "Google - Get Calendar Items": self.get_calendar_items,
                "Google - Add Calendar Item": self.add_calendar_item,
                "Google - Remove Calendar Item": self.remove_calendar_item,
                "Google - Get Keep Notes": self.get_keep_notes,
                "Google - Create Keep Note": self.create_keep_note,
                "Google - Delete Keep Note": self.delete_keep_note,
            }

            if api_key:
                try:
                    auth = MagicalAuth(token=api_key)
                    self.google_auth = auth.get_oauth_functions("google")
                    if self.google_auth:
                        logging.info("Google client initialized successfully")
                    else:
                        logging.error("Failed to get OAuth data for Google")
                except Exception as e:
                    logging.error(f"Error initializing Google client: {str(e)}")

        self.attachments_dir = kwargs.get(
            "conversation_directory", "./WORKSPACE/attachments"
        )
        os.makedirs(self.attachments_dir, exist_ok=True)

    def authenticate(self):
        """
        Ensures we have valid Google authentication and returns credentials.
        Raises ValueError if auth is not initialized.
        """
        if not self.google_auth:
            raise ValueError(
                "Google authentication not initialized. Please check authentication."
            )
        return self.google_auth

    async def get_emails(self, query=None, max_emails=10):
        """
        Retrieves emails from Gmail inbox.

        Args:
            query (str): Optional search query to filter emails
            max_emails (int): Maximum number of emails to retrieve

        Returns:
            list: List of dictionaries containing email information including:
                - id: Email identifier
                - sender: Sender's email address
                - subject: Email subject
                - body: Email content snippet
                - attachments: List of attachment names
                - received_time: When the email was received
        """
        try:
            service = build(
                "gmail",
                "v1",
                credentials=self.authenticate(),
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

                # Extract headers properly
                headers = {
                    header["name"].lower(): header["value"]
                    for header in msg["payload"]["headers"]
                }

                email_data = {
                    "id": msg["id"],
                    "sender": headers.get("from", "Unknown"),
                    "subject": headers.get("subject", "No Subject"),
                    "body": msg["snippet"],
                    "attachments": [
                        part["filename"]
                        for part in msg["payload"].get("parts", [])
                        if part.get("filename")
                    ],
                    "received_time": datetime.fromtimestamp(
                        int(msg["internalDate"]) / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }
                emails.append(email_data)

            return emails
        except Exception as e:
            logging.error(f"Error retrieving emails: {str(e)}")
            return []

    async def send_email(
        self, to, subject, body, attachments=None, importance="normal"
    ):
        """
        Sends an email using Gmail.

        Args:
            to (str): Recipient email address
            subject (str): Email subject
            body (str): Email content
            attachments (list): Optional list of file paths to attach
            importance (str): Email importance level ("low", "normal", "high")

        Returns:
            str: Success or failure message
        """
        try:
            service = build(
                "gmail",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            message = MIMEMultipart()
            message["to"] = to
            message["subject"] = subject

            # Add importance header
            if importance == "high":
                message["X-Priority"] = "1"
            elif importance == "low":
                message["X-Priority"] = "5"

            msg = MIMEText(body, "html")
            message.attach(msg)

            if attachments:
                for attachment_path in attachments:
                    if os.path.exists(attachment_path):
                        content_type, _ = mimetypes.guess_type(attachment_path)
                        if content_type is None:
                            content_type = "application/octet-stream"

                        main_type, sub_type = content_type.split("/", 1)
                        with open(attachment_path, "rb") as fp:
                            attach_msg = MIMEApplication(fp.read(), _subtype=sub_type)

                        attach_msg.add_header(
                            "Content-Disposition",
                            "attachment",
                            filename=os.path.basename(attachment_path),
                        )
                        message.attach(attach_msg)

            raw = urlsafe_b64encode(message.as_bytes()).decode()
            try:
                service.users().messages().send(
                    userId="me", body={"raw": raw}
                ).execute()
                return "Email sent successfully."
            except Exception as e:
                raise Exception(f"Failed to send email: {str(e)}")

        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
            return f"Failed to send email: {str(e)}"

    async def move_email_to_folder(self, message_id, folder_name):
        """
        Moves an email to a specified Gmail label/folder.

        Args:
            message_id (str): ID of the email to move
            folder_name (str): Name of the destination label/folder

        Returns:
            str: Success or failure message
        """
        try:
            service = build(
                "gmail",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            # First try to find the label
            labels = service.users().labels().list(userId="me").execute()
            label_id = None
            for label in labels.get("labels", []):
                if label["name"].lower() == folder_name.lower():
                    label_id = label["id"]
                    break

            # Create label if it doesn't exist
            if not label_id:
                new_label = (
                    service.users()
                    .labels()
                    .create(userId="me", body={"name": folder_name})
                    .execute()
                )
                label_id = new_label["id"]

            # Modify the message to add the label
            service.users().messages().modify(
                userId="me", id=message_id, body={"addLabelIds": [label_id]}
            ).execute()

            return f"Email moved to {folder_name} successfully."
        except Exception as e:
            logging.error(f"Error moving email: {str(e)}")
            return f"Failed to move email: {str(e)}"

    async def get_calendar_items(self, start_date=None, end_date=None, max_items=10):
        """
        Retrieves calendar events from Google Calendar.

        Args:
            start_date (datetime): Start date for events (defaults to today)
            end_date (datetime): End date for events (defaults to 7 days from start)
            max_items (int): Maximum number of events to retrieve

        Returns:
            list: List of dictionaries containing calendar event information
        """
        try:
            service = build(
                "calendar",
                "v3",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            if start_date is None:
                start_date = datetime.utcnow()
            if end_date is None:
                end_date = start_date + timedelta(days=7)

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_date.isoformat() + "Z",
                    timeMax=end_date.isoformat() + "Z",
                    maxResults=max_items,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = []
            for event in events_result.get("items", []):
                event_data = {
                    "id": event["id"],
                    "summary": event["summary"],
                    "start": event["start"].get("dateTime", event["start"].get("date")),
                    "end": event["end"].get("dateTime", event["end"].get("date")),
                    "location": event.get("location", ""),
                    "description": event.get("description", ""),
                    "organizer": event["organizer"]["email"],
                    "attendees": [
                        attendee["email"] for attendee in event.get("attendees", [])
                    ],
                    "conference_data": event.get("conferenceData", {}),
                }
                events.append(event_data)

            return events
        except Exception as e:
            logging.error(f"Error retrieving calendar events: {str(e)}")
            return []

    async def add_calendar_item(
        self,
        summary,
        start_time,
        end_time,
        description=None,
        location=None,
        attendees=None,
        is_online_meeting=False,
    ):
        """
        Creates a new Google Calendar event.

        Args:
            summary (str): Event title/summary
            start_time (datetime): Event start time
            end_time (datetime): Event end time
            description (str): Optional event description
            location (str): Optional physical location
            attendees (list): Optional list of attendee email addresses
            is_online_meeting (bool): Whether to create as Google Meet meeting

        Returns:
            str: Success or failure message
        """
        try:
            service = build(
                "calendar",
                "v3",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            event = {
                "summary": summary,
                "start": {
                    "dateTime": start_time.isoformat(),
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": end_time.isoformat(),
                    "timeZone": "UTC",
                },
            }

            if description:
                event["description"] = description
            if location:
                event["location"] = location
            if attendees:
                event["attendees"] = [{"email": email} for email in attendees]
            if is_online_meeting:
                event["conferenceData"] = {
                    "createRequest": {
                        "requestId": f"{start_time.timestamp()}-{end_time.timestamp()}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                }

            event = (
                service.events()
                .insert(
                    calendarId="primary",
                    body=event,
                    conferenceDataVersion=1 if is_online_meeting else 0,
                )
                .execute()
            )

            return "Calendar event created successfully."
        except Exception as e:
            logging.error(f"Error creating calendar event: {str(e)}")
            return f"Failed to create calendar event: {str(e)}"

    async def remove_calendar_item(self, event_id):
        """
        Deletes a calendar event.

        Args:
            event_id (str): ID of the event to delete

        Returns:
            str: Success or failure message
        """
        try:
            service = build(
                "calendar",
                "v3",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            service.events().delete(calendarId="primary", eventId=event_id).execute()

            return "Calendar event deleted successfully."
        except Exception as e:
            logging.error(f"Error deleting calendar event: {str(e)}")
            return f"Failed to delete calendar event: {str(e)}"

    async def create_draft_email(
        self, recipient, subject, body, attachments=None, importance="normal"
    ):
        """
        Creates a draft email in Gmail.

        Args:
            recipient (str): Email address of the recipient
            subject (str): Email subject
            body (str): Email content
            attachments (list): Optional list of file paths to attach
            importance (str): Email importance level ("low", "normal", "high")

        Returns:
            str: Success or failure message
        """
        try:
            service = build(
                "gmail",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            message = MIMEMultipart()
            message["to"] = recipient
            message["subject"] = subject

            if importance == "high":
                message["X-Priority"] = "1"
            elif importance == "low":
                message["X-Priority"] = "5"

            msg = MIMEText(body, "html")
            message.attach(msg)

            if attachments:
                for attachment_path in attachments:
                    if os.path.exists(attachment_path):
                        content_type, _ = mimetypes.guess_type(attachment_path)
                        if content_type is None:
                            content_type = "application/octet-stream"

                        main_type, sub_type = content_type.split("/", 1)
                        with open(attachment_path, "rb") as fp:
                            attach_msg = MIMEApplication(fp.read(), _subtype=sub_type)

                        attach_msg.add_header(
                            "Content-Disposition",
                            "attachment",
                            filename=os.path.basename(attachment_path),
                        )
                        message.attach(attach_msg)

            raw = urlsafe_b64encode(message.as_bytes()).decode()
            draft = {"message": {"raw": raw}}

            service.users().drafts().create(userId="me", body=draft).execute()

            return "Draft email created successfully."
        except Exception as e:
            logging.error(f"Error creating draft email: {str(e)}")
            return f"Failed to create draft email: {str(e)}"

    async def delete_email(self, message_id):
        """
        Permanently deletes an email from Gmail.

        Args:
            message_id (str): ID of the email to delete

        Returns:
            str: Success or failure message
        """
        try:
            service = build(
                "gmail",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            service.users().messages().trash(userId="me", id=message_id).execute()

            return "Email moved to trash successfully."
        except Exception as e:
            logging.error(f"Error deleting email: {str(e)}")
            return f"Failed to delete email: {str(e)}"

    async def search_emails(self, query, max_emails=10, include_spam=False):
        """
        Searches for emails in Gmail using Google's search syntax.

        Args:
            query (str): Search query using Gmail search operators
            max_emails (int): Maximum number of emails to retrieve
            include_spam (bool): Whether to include spam/trash in search

        Returns:
            list: List of dictionaries containing matching email information
        """
        try:
            service = build(
                "gmail",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            result = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=max_emails,
                    includeSpamTrash=include_spam,
                )
                .execute()
            )

            messages = result.get("messages", [])
            emails = []

            for message in messages:
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message["id"], format="full")
                    .execute()
                )

                headers = {
                    header["name"].lower(): header["value"]
                    for header in msg["payload"]["headers"]
                }

                email_data = {
                    "id": msg["id"],
                    "thread_id": msg["threadId"],
                    "sender": headers.get("from", "Unknown"),
                    "to": headers.get("to", ""),
                    "subject": headers.get("subject", "No Subject"),
                    "date": headers.get("date", ""),
                    "body": msg["snippet"],
                    "labels": msg["labelIds"],
                    "attachments": [
                        part["filename"]
                        for part in msg["payload"].get("parts", [])
                        if part.get("filename")
                    ],
                    "received_time": datetime.fromtimestamp(
                        int(msg["internalDate"]) / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }
                emails.append(email_data)

            return emails
        except Exception as e:
            logging.error(f"Error searching emails: {str(e)}")
            return []

    async def reply_to_email(
        self, message_id, body, attachments=None, include_history=True
    ):
        """
        Replies to an existing email thread.

        Args:
            message_id (str): ID of the email to reply to
            body (str): Reply content
            attachments (list): Optional list of file paths to attach
            include_history (bool): Whether to include previous messages

        Returns:
            str: Success or failure message
        """
        try:
            service = build(
                "gmail",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            # Get the original message
            original = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=[
                        "Subject",
                        "From",
                        "To",
                        "References",
                        "Message-ID",
                    ],
                )
                .execute()
            )

            headers = {
                header["name"].lower(): header["value"]
                for header in original["payload"]["headers"]
            }

            # Create reply message
            message = MIMEMultipart()
            message["to"] = headers.get("from")
            message["subject"] = (
                f"Re: {headers.get('subject', '').removeprefix('Re: ')}"
            )
            message["References"] = (
                f"{headers.get('references', '')} {headers.get('message-id', '')}".strip()
            )
            message["In-Reply-To"] = headers.get("message-id", "")

            msg = MIMEText(body, "html")
            message.attach(msg)

            if attachments:
                for attachment_path in attachments:
                    if os.path.exists(attachment_path):
                        content_type, _ = mimetypes.guess_type(attachment_path)
                        if content_type is None:
                            content_type = "application/octet-stream"

                        main_type, sub_type = content_type.split("/", 1)
                        with open(attachment_path, "rb") as fp:
                            attach_msg = MIMEApplication(fp.read(), _subtype=sub_type)

                        attach_msg.add_header(
                            "Content-Disposition",
                            "attachment",
                            filename=os.path.basename(attachment_path),
                        )
                        message.attach(attach_msg)

            raw = urlsafe_b64encode(message.as_bytes()).decode()

            service.users().messages().send(
                userId="me", body={"raw": raw, "threadId": original["threadId"]}
            ).execute()

            return "Reply sent successfully."
        except Exception as e:
            logging.error(f"Error sending reply: {str(e)}")
            return f"Failed to send reply: {str(e)}"

    async def process_attachments(self, message_id):
        """
        Downloads all attachments from a specific email.

        Args:
            message_id (str): ID of the email containing attachments

        Returns:
            list: List of paths to saved attachment files
        """
        try:
            service = build(
                "gmail",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            message = (
                service.users().messages().get(userId="me", id=message_id).execute()
            )

            saved_paths = []
            if "parts" not in message["payload"]:
                return saved_paths

            for part in message["payload"]["parts"]:
                if part.get("filename"):
                    if "data" in part["body"]:
                        data = part["body"]["data"]
                    else:
                        att_id = part["body"]["attachmentId"]
                        att = (
                            service.users()
                            .messages()
                            .attachments()
                            .get(userId="me", messageId=message_id, id=att_id)
                            .execute()
                        )
                        data = att["data"]

                    file_data = urlsafe_b64decode(data.encode("UTF-8"))
                    file_path = os.path.join(self.attachments_dir, part["filename"])

                    with open(file_path, "wb") as f:
                        f.write(file_data)
                    saved_paths.append(file_path)

            return saved_paths
        except Exception as e:
            logging.error(f"Error processing attachments: {str(e)}")
            return []

    async def get_keep_notes(self, max_notes=50):
        """
        Retrieves notes from Google Keep.
        Note: This requires the Google Keep API to be enabled.

        Args:
            max_notes (int): Maximum number of notes to retrieve

        Returns:
            list: List of dictionaries containing note information
        """
        try:
            service = build(
                "keep",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            results = (
                service.notes()
                .list(maxResults=max_notes, filter="trashed = false")
                .execute()
            )

            notes = []
            for note in results.get("notes", []):
                note_data = {
                    "id": note["id"],
                    "title": note.get("title", ""),
                    "text": note.get("textContent", ""),
                    "created_time": note.get("createTime", ""),
                    "updated_time": note.get("updateTime", ""),
                    "color": note.get("color", ""),
                    "archived": note.get("archived", False),
                    "labels": [label["name"] for label in note.get("labels", [])],
                }
                notes.append(note_data)

            return notes
        except Exception as e:
            logging.error(f"Error retrieving Keep notes: {str(e)}")
            return []

    async def create_keep_note(self, title, text_content, color=None, labels=None):
        """
        Creates a new note in Google Keep.

        Args:
            title (str): Note title
            text_content (str): Note content
            color (str): Optional color for the note
            labels (list): Optional list of label names

        Returns:
            str: Success or failure message
        """
        try:
            service = build(
                "keep",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            note_data = {"title": title, "textContent": text_content}

            if color:
                note_data["color"] = color

            if labels:
                note_data["labels"] = [{"name": label} for label in labels]

            service.notes().create(body=note_data).execute()

            return "Note created successfully."
        except Exception as e:
            logging.error(f"Error creating Keep note: {str(e)}")
            return f"Failed to create note: {str(e)}"

    async def delete_keep_note(self, note_id):
        """
        Moves a note to trash in Google Keep.

        Args:
            note_id (str): ID of the note to delete

        Returns:
            str: Success or failure message
        """
        try:
            service = build(
                "keep",
                "v1",
                credentials=self.authenticate(),
                always_use_jwt_access=True,
            )

            service.notes().trash(noteId=note_id).execute()

            return "Note moved to trash successfully."
        except Exception as e:
            logging.error(f"Error deleting Keep note: {str(e)}")
            return f"Failed to delete note: {str(e)}"
