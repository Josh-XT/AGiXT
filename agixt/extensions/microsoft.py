import os
import logging
import requests
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
import base64
from fastapi import HTTPException


"""
Required environment variables:

- MICROSOFT_CLIENT_ID: Microsoft OAuth client ID
- MICROSOFT_CLIENT_SECRET: Microsoft OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Microsoft OAuth

- offline_access
- https://graph.microsoft.com/User.Read
- https://graph.microsoft.com/Mail.Send
- https://graph.microsoft.com/Calendars.ReadWrite.Shared
- https://graph.microsoft.com/Calendars.ReadWrite
- https://graph.microsoft.com/Files.ReadWrite.All (OneDrive access)
- https://graph.microsoft.com/Sites.ReadWrite.All (SharePoint access)

"""
SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Calendars.ReadWrite.Shared",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/Files.ReadWrite.All",
    "https://graph.microsoft.com/Sites.ReadWrite.All",
]
AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
PKCE_REQUIRED = False


class MicrosoftSSO:
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
            raise Exception(f"Microsoft token refresh failed: {response.text}")

        token_data = response.json()

        # Update our access token for immediate use
        if "access_token" in token_data:
            new_token = token_data["access_token"]
            self.access_token = new_token
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
            # Handle missing or null fields gracefully
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


def sso(code, redirect_uri=None) -> MicrosoftSSO:
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
        f"https://login.microsoftonline.com/common/oauth2/v2.0/token",
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
        logging.error(f"Error getting Microsoft access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return MicrosoftSSO(access_token=access_token, refresh_token=refresh_token)


class microsoft(Extensions):
    """
    The Microsoft 365 extension provides comprehensive integration with Microsoft Office 365 services.
    This extension allows AI agents to:
    - Manage emails (read, send, move, search)
    - Handle calendar events
    - Process email attachments
    - Access and manage OneDrive files (list, read, upload, download, delete, search)
    - Access and manage SharePoint sites and document libraries

    The extension requires the user to be authenticated with Microsoft 365 through OAuth.
    AI agents should use this when they need to interact with a user's Microsoft 365 account
    for tasks like scheduling meetings, sending emails, managing files in OneDrive/SharePoint,
    or managing tasks.
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
        self.access_token = kwargs.get("MICROSOFT_ACCESS_TOKEN", None)
        microsoft_client_id = getenv("MICROSOFT_CLIENT_ID")
        microsoft_client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.timezone = getenv("TZ")
        self.auth = None
        if microsoft_client_id and microsoft_client_secret:
            self.commands = {
                "Get Emails from Microsoft Account": self.microsoft_get_emails,
                "Send Email from Microsoft Account": self.microsoft_send_email,
                "Create Draft Email in Microsoft Account": self.microsoft_create_draft_email,
                "Delete Email from Microsoft Account": self.microsoft_delete_email,
                "Search Emails in Microsoft Account": self.microsoft_search_emails,
                "Reply to Email in Microsoft Account": self.microsoft_reply_to_email,
                "Process Attachments from Microsoft Email": self.microsoft_process_attachments,
                "Get Calendar Items from Microsoft Account": self.microsoft_get_calendar_items,
                "Get Available Timeslots from Microsoft Calendar": self.microsoft_get_available_timeslots,
                "Add Calendar Item to Microsoft Account": self.microsoft_add_calendar_item,
                "Modify Calendar Item in Microsoft Account": self.microsoft_modify_calendar_item,
                "Remove Calendar Item from Microsoft Account": self.microsoft_remove_calendar_item,
                # OneDrive commands
                "List OneDrive Files": self.onedrive_list_files,
                "Get OneDrive File Content": self.onedrive_get_file_content,
                "Upload File to OneDrive": self.onedrive_upload_file,
                "Download File from OneDrive": self.onedrive_download_file,
                "Create OneDrive Folder": self.onedrive_create_folder,
                "Delete OneDrive Item": self.onedrive_delete_item,
                "Search OneDrive": self.onedrive_search,
                "Move OneDrive Item": self.onedrive_move_item,
                "Copy OneDrive Item": self.onedrive_copy_item,
                # SharePoint commands
                "List SharePoint Sites": self.sharepoint_list_sites,
                "Get SharePoint Site": self.sharepoint_get_site,
                "List SharePoint Document Libraries": self.sharepoint_list_libraries,
                "List SharePoint Files": self.sharepoint_list_files,
                "Get SharePoint File Content": self.sharepoint_get_file_content,
                "Upload File to SharePoint": self.sharepoint_upload_file,
                "Download File from SharePoint": self.sharepoint_download_file,
                "Create SharePoint Folder": self.sharepoint_create_folder,
                "Delete SharePoint Item": self.sharepoint_delete_item,
                "Search SharePoint": self.sharepoint_search,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                    self.timezone = self.auth.get_timezone()
                except Exception as e:
                    logging.error(f"Error initializing Microsoft365 client: {str(e)}")

        self.attachments_dir = kwargs.get(
            "conversation_directory", "./WORKSPACE/attachments"
        )
        os.makedirs(self.attachments_dir, exist_ok=True)

    def _parse_datetime(self, dt_input):
        """
        Helper function to parse datetime input that can be either a string or datetime object.
        Returns a datetime object.
        """
        if isinstance(dt_input, str):
            # Remove any trailing zeros and extra precision from microseconds
            dt_str = dt_input.strip()

            # Handle various datetime string formats
            try:
                # First try standard ISO format
                if dt_str.endswith("Z"):
                    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                elif "+" in dt_str or dt_str.endswith("00:00"):
                    return datetime.fromisoformat(dt_str)
                else:
                    # Handle format like "2025-09-14T05:45:00.0000000"
                    if "." in dt_str:
                        # Remove excessive microseconds precision
                        date_part, time_part = dt_str.split("T")
                        if "." in time_part:
                            time_base, microseconds = time_part.split(".")
                            # Keep only up to 6 digits for microseconds
                            microseconds = microseconds[:6].ljust(6, "0")
                            dt_str = f"{date_part}T{time_base}.{microseconds}"

                    # Parse as naive datetime first
                    return datetime.fromisoformat(dt_str)
            except ValueError:
                # Try parsing without microseconds
                try:
                    if "T" in dt_str:
                        dt_str = dt_str.split(".")[0]  # Remove microseconds
                    return datetime.fromisoformat(dt_str)
                except ValueError:
                    # Last resort: try strptime with common formats
                    formats = [
                        "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%dT%H:%M",
                        "%Y-%m-%d %H:%M",
                    ]
                    for fmt in formats:
                        try:
                            return datetime.strptime(dt_str, fmt)
                        except ValueError:
                            continue
                    raise ValueError(f"Unable to parse datetime string: {dt_input}")
        elif isinstance(dt_input, datetime):
            return dt_input
        else:
            raise ValueError(f"Invalid datetime input type: {type(dt_input)}")

    def _format_datetime_for_api(self, dt):
        """
        Helper function to format datetime for Microsoft Graph API.
        Returns properly formatted ISO string.
        """
        if isinstance(dt, str):
            dt = self._parse_datetime(dt)

        # Format as ISO string without timezone info (API handles timezone separately)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[
            :-3
        ]  # Remove last 3 digits of microseconds

    def _normalize_folder_segments(self, folder_name):
        """
        Break a folder path into normalized segments, mapping the first segment to
        a well-known folder name when possible (Inbox, SentItems, etc.).
        """
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
        """
        Resolve a folder path (already normalized into segments) to its unique ID
        by walking down the folder tree using Microsoft Graph.
        """
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
                    # Continue resolving child segments using the resolved ID
                    continue

                logging.debug(
                    f"Direct folder lookup for '{segment}' returned status {response.status_code}"
                )

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
        """
        Build the messages endpoint for the requested folder. Falls back to the
        default mailbox when the folder cannot be resolved.
        """
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
        """
        Normalize a Graph message payload into the structure expected by the
        extension consumers.
        """
        if not isinstance(message, dict):
            return None

        message_id = message.get("id")
        if not message_id:
            logging.debug("Skipping message without an 'id' field")
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

    def verify_user(self):
        """
        Verifies that the current access token corresponds to a valid user.
        If the /me endpoint fails, raises an exception indicating the user is not found.
        """
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="microsoft")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        if response.status_code != 200:
            raise Exception(
                f"User not found or invalid token. Status: {response.status_code}, "
                f"Response: {response.text}. Ensure the token is a user-delegated token "
                "with the correct scopes (e.g., Calendars.ReadWrite), and the user is properly signed in."
            )

    async def microsoft_send_email(
        self, recipient, subject, body, attachments=None, importance="normal"
    ):
        """
        Sends an email using the Microsoft 365 account.

        Args:
            recipient (str): Email address of the recipient
            subject (str): Email subject
            body (str): Email content
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

    async def microsoft_check_time_availability(self, start_time, end_time):
        """
        Checks if a specific time slot is available.

        Args:
            start_time (datetime or str): Start time of proposed event
            end_time (datetime or str): End time of proposed event

        Returns:
            tuple: (bool, dict) - (is_available, conflicting_event_if_any)
        """
        try:
            self.verify_user()

            # Parse datetime inputs
            start_dt = self._parse_datetime(start_time)
            end_dt = self._parse_datetime(end_time)

            # Get events for the day
            existing_events = await self.microsoft_get_calendar_items(
                start_date=start_dt, end_date=end_dt, max_items=50
            )

            for event in existing_events:
                event_start = self._parse_datetime(event["start_time"])
                event_end = self._parse_datetime(event["end_time"])

                # Check for actual overlap (exclusive at boundaries)
                # A meeting ending at 10:00 doesn't conflict with one starting at 10:00
                if start_dt < event_end and end_dt > event_start:
                    return False, event

            return True, None

        except Exception as e:
            logging.error(f"Error checking time availability: {str(e)}")
            raise

    async def microsoft_add_calendar_item(
        self,
        subject,
        start_time,
        end_time,
        location=None,
        attendees=None,
        body=None,
        is_online_meeting=False,
        reminder_minutes_before=15,
    ):
        """
        Creates a new calendar event.

        Args:
            subject (str): Event title/subject
            start_time (datetime or str): Event start time
            end_time (datetime or str): Event end time
            location (str): Optional physical location
            attendees (list): Optional list of attendee email addresses
            body (str): Optional event description
            is_online_meeting (bool): Whether to create as Teams meeting
            reminder_minutes_before (int): Minutes before event to send reminder

        Returns:
            str: Success or failure message
        """
        try:
            # Parse datetime inputs
            start_dt = self._parse_datetime(start_time)
            end_dt = self._parse_datetime(end_time)

            # Convert string boolean values if needed
            if isinstance(is_online_meeting, str):
                is_online_meeting = is_online_meeting.lower() in ("true", "1", "yes")

            # Convert reminder minutes to int if it's a string
            if isinstance(reminder_minutes_before, str):
                try:
                    reminder_minutes_before = int(reminder_minutes_before)
                except ValueError:
                    reminder_minutes_before = 15  # Default fallback

            is_available, conflict = await self.microsoft_check_time_availability(
                start_dt, end_dt
            )

            if not is_available:
                return {
                    "success": False,
                    "message": f"The user isn't available at {start_dt.strftime('%Y-%m-%d %H:%M')}. "
                    f"There is a conflict with '{conflict['subject']}'. "
                    f"Ask the user if they would like to schedule a different time or "
                    f"move their scheduled item '{conflict['subject']}' to a different time.",
                }

            # Original add_calendar_item logic here
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            event_data = {
                "subject": subject,
                "start": {
                    "dateTime": self._format_datetime_for_api(start_dt),
                    "timeZone": self.timezone or "UTC",
                },
                "end": {
                    "dateTime": self._format_datetime_for_api(end_dt),
                    "timeZone": self.timezone or "UTC",
                },
                "isOnlineMeeting": is_online_meeting,
                "reminderMinutesBeforeStart": reminder_minutes_before,
            }

            if location:
                event_data["location"] = {"displayName": location}

            if body:
                event_data["body"] = {"contentType": "HTML", "content": body}

            if attendees:
                if isinstance(attendees, str):
                    # Handle empty string or comma-separated list
                    if attendees.strip():
                        attendees = [
                            email.strip()
                            for email in attendees.split(",")
                            if email.strip()
                        ]
                    else:
                        attendees = []

                if attendees:  # Only add if we have actual attendees
                    event_data["attendees"] = [
                        {"emailAddress": {"address": email}, "type": "required"}
                        for email in attendees
                    ]

            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/events",
                headers=headers,
                json=event_data,
            )

            if response.status_code == 201:
                return {
                    "success": True,
                    "message": "Calendar event created successfully.",
                    "event_id": response.json().get("id"),
                }
            else:
                raise Exception(
                    f"Failed to create event: {response.status_code}: {response.text}"
                )

        except Exception as e:
            logging.error(f"Error creating calendar event: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to create calendar event: {str(e)}",
            }

    async def microsoft_get_emails(
        self, folder_name="Inbox", max_emails=10, page_size=10
    ):
        """
        Retrieves emails from a specified folder in the user's Microsoft 365 mailbox.

        Args:
            folder_name (str): Name of the folder to fetch emails from (e.g., "Inbox", "Sent Items")
            max_emails (int): Maximum number of emails to retrieve
            page_size (int): Number of emails to fetch per page

        Returns:
            list: List of dictionaries containing email information
        """
        try:
            self.verify_user()

            # Convert parameters to appropriate types
            max_emails = int(max_emails)
            page_size = int(page_size) if page_size else 10

            if max_emails <= 0:
                logging.info("Requested max_emails <= 0, returning no emails.")
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
                    logging.info(
                        "Microsoft Graph returned no messages for the requested folder."
                    )
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
            import traceback

            logging.error(f"Traceback: {traceback.format_exc()}")
            return []

    async def microsoft_modify_calendar_item(
        self,
        event_id,
        subject=None,
        start_time=None,
        end_time=None,
        location=None,
        attendees=None,
        body=None,
        is_online_meeting=None,
        reminder_minutes_before=None,
        check_availability=True,
    ):
        """
        Modifies an existing calendar event.

        Args:
            event_id (str): ID of the event to modify
            [all other parameters are optional and match add_calendar_item]
            subject (str): Event title/subject
            start_time (datetime): Event start time
            end_time (datetime): Event end time
            location (str): Optional physical location
            attendees (list): Optional list of attendee email addresses
            body (str): Optional event description
            is_online_meeting (bool): Whether to create as Teams meeting
            reminder_minutes_before (int): Minutes before event to send reminder
            check_availability (bool): Whether to check for conflicts before modifying time

        Returns:
            dict: Response containing success status and any conflict information
        """
        try:
            self.verify_user()

            # First check if the event exists
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Prefer": f'outlook.timezone="{self.timezone}"',
            }

            # Verify the event exists
            try:
                event_check = requests.get(
                    f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                    headers=headers,
                )

                if event_check.status_code != 200:
                    logging.error(f"Event not found: {event_check.text}")
                    return {
                        "success": False,
                        "message": f"Event with ID {event_id} not found or inaccessible. Status: {event_check.status_code}",
                    }

                # If we found the event, store its data for potential conflict checking
                existing_event = event_check.json()
                logging.info(f"Found existing event: {existing_event.get('subject')}")
            except Exception as check_err:
                logging.error(f"Error checking event existence: {str(check_err)}")
                return {
                    "success": False,
                    "message": f"Error verifying event: {str(check_err)}",
                }

            # If changing time, check availability
            if check_availability and start_time and end_time:
                # Parse datetime strings properly
                start_dt = self._parse_datetime(start_time)
                end_dt = self._parse_datetime(end_time)

                is_available, conflict = await self.microsoft_check_time_availability(
                    start_dt, end_dt
                )

                if not is_available:
                    return {
                        "success": False,
                        "message": f"The user isn't available at {start_dt.strftime('%Y-%m-%d %H:%M')}. "
                        f"There is a conflict with '{conflict['subject']}'. "
                        f"Ask the user if they would like to choose a different time.",
                    }

            # Build update data with only provided fields
            update_data = {}

            if subject:
                update_data["subject"] = subject
            if start_time:
                # Parse and format datetime properly
                start_dt = self._parse_datetime(start_time)
                update_data["start"] = {
                    "dateTime": self._format_datetime_for_api(start_dt),
                    "timeZone": self.timezone or "UTC",
                }
            if end_time:
                # Parse and format datetime properly
                end_dt = self._parse_datetime(end_time)
                update_data["end"] = {
                    "dateTime": self._format_datetime_for_api(end_dt),
                    "timeZone": self.timezone or "UTC",
                }
            if location is not None:
                update_data["location"] = {"displayName": location}
            if body is not None:
                update_data["body"] = {"contentType": "HTML", "content": body}
            if is_online_meeting is not None:
                # Convert string boolean values if needed
                if isinstance(is_online_meeting, str):
                    is_online_meeting = is_online_meeting.lower() in (
                        "true",
                        "1",
                        "yes",
                    )
                update_data["isOnlineMeeting"] = is_online_meeting
            if reminder_minutes_before is not None:
                # Convert reminder minutes to int if it's a string
                if isinstance(reminder_minutes_before, str):
                    try:
                        reminder_minutes_before = int(reminder_minutes_before)
                    except ValueError:
                        reminder_minutes_before = 15  # Default fallback
                update_data["reminderMinutesBeforeStart"] = reminder_minutes_before
            if attendees is not None:
                if isinstance(attendees, str):
                    # Handle empty string or comma-separated list
                    if attendees.strip():
                        attendees = [
                            email.strip()
                            for email in attendees.split(",")
                            if email.strip()
                        ]
                    else:
                        attendees = []

                if attendees:  # Only add if we have actual attendees
                    update_data["attendees"] = [
                        {"emailAddress": {"address": email}, "type": "required"}
                        for email in attendees
                    ]

            # If no fields to update, return success
            if not update_data:
                return {
                    "success": True,
                    "message": "No changes requested for calendar event.",
                }

            # Send the update request
            response = requests.patch(
                f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                headers=headers,
                json=update_data,
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "message": "Calendar event modified successfully.",
                    "event_id": event_id,
                }
            else:
                error_response = response.text
                logging.error(f"Event update API error: {error_response}")
                raise Exception(
                    f"Failed to modify event (Status {response.status_code}): {error_response}"
                )

        except Exception as e:
            logging.error(f"Error modifying calendar event: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to modify calendar event: {str(e)}",
            }

    async def microsoft_remove_calendar_item(self, event_id):
        """
        Deletes a calendar event.

        Args:
            event_id (str): ID of the event to delete

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            if not event_id:
                return "Failed to delete event: No event ID provided"

            # First check if the event exists
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            try:
                event_check = requests.get(
                    f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                    headers=headers,
                )

                if event_check.status_code != 200:
                    logging.error(f"Event not found: {event_check.text}")
                    return f"Event with ID {event_id} not found or inaccessible"

                logging.info(
                    f"Found event to delete: {event_check.json().get('subject')}"
                )
            except Exception as check_err:
                logging.error(f"Error checking event existence: {str(check_err)}")
                # Continue with delete attempt anyway

            # Send the delete request
            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                headers=headers,
            )

            if response.status_code == 204:
                return "Calendar event deleted successfully."
            else:
                error_response = response.text
                logging.error(f"Event delete API error: {error_response}")

                # Try alternative - cancel instead of delete
                try:
                    cancel_data = {"comment": "Cancelled by AI assistant"}
                    cancel_response = requests.post(
                        f"https://graph.microsoft.com/v1.0/me/events/{event_id}/cancel",
                        headers=headers,
                        json=cancel_data,
                    )

                    if cancel_response.status_code == 202:
                        return "Calendar event cancelled successfully."

                    logging.error(f"Event cancel API error: {cancel_response.text}")
                except Exception as cancel_err:
                    logging.error(f"Error cancelling event: {str(cancel_err)}")

                raise Exception(f"Failed to delete event: {error_response}")

        except Exception as e:
            logging.error(f"Error deleting calendar event: {str(e)}")
            return f"Failed to delete calendar event: {str(e)}"

    async def microsoft_get_calendar_items(
        self, start_date=None, end_date=None, max_items=10
    ):
        """
        Retrieves calendar events within a date range.

        Args:
            start_date (datetime): Start date for events (defaults to today)
            end_date (datetime): End date for events (defaults to 7 days from start)
            max_items (int): Maximum number of events to retrieve

        Returns:
            list: List of calendar event dictionaries
        """
        try:
            self.verify_user()

            # Convert parameters to appropriate types
            max_items = int(max_items)

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Prefer": f'outlook.timezone="{self.timezone}"',
            }

            # Set default dates if not provided
            if not start_date:
                start_date = datetime.now()
            if not end_date:
                end_date = start_date + timedelta(days=7)

            # Handle string inputs by converting to datetime
            if isinstance(start_date, str):
                start_date = self._parse_datetime(start_date)

            if isinstance(end_date, str):
                end_date = self._parse_datetime(end_date)
                # If it was a date-only string, the parser may have set time to 00:00:00
                # So if both hour/minute/second are 0, set to end of day
                if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
                    end_date = end_date.replace(hour=23, minute=59, second=59)

            # If start and end dates are the same day, adjust end_date to end of day
            if (
                start_date.date() == end_date.date()
                and end_date.hour == 0
                and end_date.minute == 0
                and end_date.second == 0
            ):
                end_date = end_date.replace(hour=23, minute=59, second=59)

            # Format dates properly for the API - ensure proper timezone handling
            if start_date.tzinfo is None:
                start_str = start_date.isoformat() + "Z"
            else:
                start_str = start_date.isoformat()

            if end_date.tzinfo is None:
                end_str = end_date.isoformat() + "Z"
            else:
                end_str = end_date.isoformat()

            # First check if we can access the calendar at all
            try:
                cal_check = requests.get(
                    "https://graph.microsoft.com/v1.0/me/calendar", headers=headers
                )
                if cal_check.status_code != 200:
                    logging.error(f"Calendar access error: {cal_check.text}")
                    return []
            except Exception as cal_err:
                logging.error(f"Error checking calendar access: {str(cal_err)}")
                return []

            # Build URL with parameters - try calendarView first (recommended for date ranges)
            url = (
                f"https://graph.microsoft.com/v1.0/me/calendarView?"
                f"startDateTime={start_str}&"
                f"endDateTime={end_str}&"
                f"$top={max_items}&$orderby=start/dateTime"
            )

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                error_response = response.text
                logging.error(f"Calendar API error: {error_response}")

                # Try alternative: Simple events endpoint without date filters
                alt_url1 = (
                    f"https://graph.microsoft.com/v1.0/me/events?$top={max_items}"
                )
                alt_response1 = requests.get(alt_url1, headers=headers)

                if alt_response1.status_code == 200:
                    alt_data1 = alt_response1.json()
                    if alt_data1.get("value"):
                        response = alt_response1

                # Try alternative: Different calendar view format
                if response.status_code != 200:
                    alt_url2 = f"https://graph.microsoft.com/v1.0/me/calendar/calendarView?startDateTime={start_str}&endDateTime={end_str}&$top={max_items}"
                    alt_response2 = requests.get(alt_url2, headers=headers)

                    if alt_response2.status_code == 200:
                        response = alt_response2
                    else:
                        logging.error(f"Calendar view alt failed: {alt_response2.text}")

                # If still no success, return empty
                if response.status_code != 200:
                    return []

            data = response.json()

            if not data.get("value"):
                return []

            events = []
            for i, event in enumerate(data["value"]):
                try:
                    # Extract and format the event details
                    event_dict = {
                        "id": event["id"],
                        "subject": event.get("subject", "(No Subject)"),
                        "start_time": event.get("start", {}).get("dateTime", ""),
                        "end_time": event.get("end", {}).get("dateTime", ""),
                        "location": event.get("location", {}).get("displayName", ""),
                        "is_online_meeting": event.get("isOnlineMeeting", False),
                        "meeting_url": (event.get("onlineMeeting") or {}).get(
                            "joinUrl", ""
                        ),
                        "organizer": (event.get("organizer") or {})
                        .get("emailAddress", {})
                        .get("address", ""),
                        "is_all_day": event.get("isAllDay", False),
                        "sensitivity": event.get("sensitivity", "normal"),
                        "status": event.get("showAs", "busy"),
                    }
                    events.append(event_dict)
                except KeyError as ke:
                    logging.error(f"Key error processing event {i+1}: {ke}")
                    continue  # Skip this event but continue with others
                except Exception as event_err:
                    logging.error(f"Error processing event {i+1}: {str(event_err)}")
                    continue

            return events

        except Exception as e:
            logging.error(f"Error retrieving calendar items: {str(e)}")
            return []

    async def microsoft_get_available_timeslots(
        self,
        start_date,
        num_days=7,
        work_day_start="09:00",
        work_day_end="17:00",
        duration_minutes=30,
        buffer_minutes=0,
    ):
        """
        Finds available time slots over a specified number of days.

        Args:
            start_date (datetime): Starting date to search from
            num_days (int): Number of days to search
            work_day_start (str): Start time of workday (HH:MM format)
            work_day_end (str): End time of workday (HH:MM format)
            duration_minutes (int): Desired meeting duration in minutes
            buffer_minutes (int): Buffer time between meetings in minutes

        Returns:
            list: List of available time slots as datetime objects
        """
        try:
            self.verify_user()

            # Convert string parameters to appropriate types
            num_days = int(num_days)
            duration_minutes = int(duration_minutes)
            buffer_minutes = int(buffer_minutes)

            # Make sure start_date is a datetime object
            if isinstance(start_date, str):
                start_date = self._parse_datetime(start_date)

            # Calculate end date
            end_date = start_date + timedelta(days=num_days)

            # Get all existing calendar events for the date range with increased limit
            existing_events = await self.microsoft_get_calendar_items(
                start_date=start_date,
                end_date=end_date,
                max_items=100,  # Increased to handle busy calendars
            )

            available_slots = []
            current_date = start_date

            # Convert work day times to datetime.time objects once
            try:
                day_start = datetime.strptime(work_day_start, "%H:%M").time()
                day_end = datetime.strptime(work_day_end, "%H:%M").time()
            except ValueError as ve:
                logging.error(f"Invalid time format: {ve}")
                # Fallback to default hours
                day_start = datetime.strptime("09:00", "%H:%M").time()
                day_end = datetime.strptime("17:00", "%H:%M").time()

            # Loop through each day in the date range
            for day_offset in range(num_days):
                # Get date for current iteration
                current_date = start_date + timedelta(days=day_offset)
                current_day = current_date.date()

                # Combine date and work day start/end times
                current_slot_start = datetime.combine(current_day, day_start)
                day_end_time = datetime.combine(current_day, day_end)

                # Skip weekends if needed (uncomment if necessary)
                # if current_day.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
                #     continue

                # Filter events for current day
                day_events = []
                for event in existing_events:
                    try:
                        # Handle different datetime formats from API
                        event_start = self._parse_datetime(event["start_time"])
                        event_end = self._parse_datetime(event["end_time"])

                        # Check if this event is on the current day
                        if event_start.date() == current_day:
                            day_events.append({"start": event_start, "end": event_end})
                    except Exception as dt_err:
                        logging.error(f"Error parsing event dates: {dt_err}")
                        continue

                # Sort events by start time
                day_events.sort(key=lambda x: x["start"])

                # Find available slots between events
                current_time = current_slot_start
                while (
                    current_time + timedelta(minutes=duration_minutes) <= day_end_time
                ):
                    slot_end = current_time + timedelta(minutes=duration_minutes)
                    is_available = True

                    # Check if current slot conflicts with any existing events
                    for event in day_events:
                        if current_time < event["end"] and slot_end > event["start"]:
                            # Conflict found, move to end of this event
                            current_time = event["end"] + timedelta(
                                minutes=buffer_minutes
                            )
                            is_available = False
                            break

                    if is_available:
                        # Add available slot to results
                        available_slots.append(
                            {
                                "start_time": current_time.isoformat(),
                                "end_time": slot_end.isoformat(),
                                "date": current_day.isoformat(),
                            }
                        )
                        # Move to next slot
                        current_time += timedelta(
                            minutes=duration_minutes + buffer_minutes
                        )

                # If we have enough slots, we can stop here
                if (
                    len(available_slots) >= 20
                ):  # Reasonable limit to avoid too many results
                    break

            # If no available slots were found, log this info
            if not available_slots:
                logging.info("No available time slots found in the specified range")

            return available_slots

        except Exception as e:
            logging.error(f"Error finding available timeslots: {str(e)}")
            return []

    async def microsoft_create_draft_email(
        self, recipient, subject, body, attachments=None, importance="normal"
    ):
        """
        Creates a draft email in the Microsoft 365 account.

        Args:
            recipient (str): Email address of the recipient
            subject (str): Email subject
            body (str): Email content
            attachments (list): Optional list of file paths to attach
            importance (str): Email importance level ("low", "normal", or "high")

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            draft_data = {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body},
                "toRecipients": [{"emailAddress": {"address": recipient}}],
                "importance": importance,
            }

            if attachments:
                draft_data["attachments"] = []
                for attachment_path in attachments:
                    if os.path.exists(attachment_path):
                        try:
                            with open(attachment_path, "rb") as file:
                                content = file.read()
                                draft_data["attachments"].append(
                                    {
                                        "@odata.type": "#microsoft.graph.fileAttachment",
                                        "name": os.path.basename(attachment_path),
                                        "contentBytes": base64.b64encode(
                                            content
                                        ).decode(),
                                    }
                                )
                        except Exception as attach_err:
                            logging.error(
                                f"Error attaching file {attachment_path}: {str(attach_err)}"
                            )

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Prefer": f'outlook.timezone="{self.timezone}"',
            }

            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/messages",
                headers=headers,
                json=draft_data,
            )

            if response.status_code == 201:
                response_data = response.json()
                return f"Draft email created successfully. ID: {response_data.get('id', 'unknown')}"
            else:
                error_response = response.text
                logging.error(f"Draft creation API error: {error_response}")
                raise Exception(
                    f"Failed to create draft (Status {response.status_code}): {error_response}"
                )

        except Exception as e:
            logging.error(f"Error creating draft email: {str(e)}")
            return f"Failed to create draft email: {str(e)}"

    async def microsoft_delete_email(self, message_id):
        """
        Deletes a specific email.

        Args:
            message_id (str): ID of the email to delete

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            if not message_id:
                return "Failed to delete email: No message ID provided"

            # First verify the message exists
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            try:
                check_response = requests.get(
                    f"https://graph.microsoft.com/v1.0/me/messages/{message_id}",
                    headers=headers,
                )
                if check_response.status_code != 200:
                    return f"Failed to find email with ID {message_id}: {check_response.status_code}"
            except Exception as e:
                logging.error(f"Error checking message existence: {str(e)}")
                # Continue with delete anyway

            # Attempt to delete the message
            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}",
                headers=headers,
            )

            if response.status_code == 204:
                return "Email deleted successfully."
            else:
                error_response = response.text
                logging.error(f"Delete API error: {error_response}")
                raise Exception(
                    f"Failed to delete email (Status {response.status_code}): {error_response}"
                )

        except Exception as e:
            logging.error(f"Error deleting email: {str(e)}")
            return f"Failed to delete email: {str(e)}"

    async def microsoft_search_emails(
        self, query, folder_name="Inbox", max_emails=10, date_range=None
    ):
        """
        Searches for emails in a specified folder.

        Args:
            query (str): Search query
            folder_name (str): Folder to search in
            max_emails (int): Maximum number of results
            date_range (tuple): Optional (start_date, end_date) tuple

        Returns:
            list: List of matching email dictionaries
        """
        try:
            self.verify_user()

            # Convert parameters to appropriate types
            max_emails = int(max_emails)

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Prefer": 'outlook.body-content-type="text"',
            }

            # First try to get the folder ID if specified
            folder_id = None
            if folder_name and folder_name.lower() != "all":
                try:
                    folder_response = requests.get(
                        f"https://graph.microsoft.com/v1.0/me/mailFolders?$filter=displayName eq '{folder_name}'",
                        headers=headers,
                    )

                    if (
                        folder_response.status_code == 200
                        and folder_response.json().get("value")
                    ):
                        folder_id = folder_response.json()["value"][0]["id"]
                    else:
                        logging.warning(
                            f"Could not find folder '{folder_name}', searching across all folders"
                        )
                except Exception as folder_err:
                    logging.error(f"Error finding folder: {str(folder_err)}")

            # Build search URL with proper filters
            base_url = f"https://graph.microsoft.com/v1.0/me/{'mailFolders/' + folder_id + '/' if folder_id else ''}messages"

            # Use $search parameter which is more powerful than $filter
            filters = []

            # Add date range filter if provided
            date_filter = ""
            if date_range:
                # Handle date_range passed as string (e.g., "(2025-11-28, 2025-11-30)" or "2025-11-28, 2025-11-30")
                if isinstance(date_range, str):
                    # Remove parentheses and split by comma
                    date_str = date_range.strip().strip("()")
                    parts = [p.strip() for p in date_str.split(",")]
                    if len(parts) == 2:
                        start_date = self._parse_datetime(parts[0])
                        end_date = self._parse_datetime(parts[1])
                    else:
                        logging.warning(
                            f"Invalid date_range format: {date_range}, expected '(start_date, end_date)'"
                        )
                        start_date = None
                        end_date = None
                elif isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                    start_date, end_date = date_range
                    # Parse strings if needed
                    if isinstance(start_date, str):
                        start_date = self._parse_datetime(start_date)
                    if isinstance(end_date, str):
                        end_date = self._parse_datetime(end_date)
                else:
                    logging.warning(f"Unsupported date_range type: {type(date_range)}")
                    start_date = None
                    end_date = None

                if start_date and end_date:
                    date_filter = f" AND receivedDateTime ge {start_date.isoformat()}Z AND receivedDateTime le {end_date.isoformat()}Z"
                    filters.append(date_filter)

            # Construct the final URL with search and/or filter parameters
            if query:
                url = f'{base_url}?$search="{query}"{date_filter}&$top={max_emails}'
            else:
                filter_params = " and ".join(filters) if filters else ""
                url = f"{base_url}?{'$filter=' + filter_params if filter_params else ''}&$top={max_emails}&$orderby=receivedDateTime desc"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                error_response = response.text
                logging.error(f"Search API error: {error_response}")

                # If $search failed, try a simpler approach
                if query:
                    backup_url = f"{base_url}?$filter=contains(subject,'{query}')&$top={max_emails}&$orderby=receivedDateTime desc"
                    backup_response = requests.get(backup_url, headers=headers)
                    if backup_response.status_code == 200:
                        response = backup_response
                    else:
                        raise Exception(f"Failed to search emails: {error_response}")
                else:
                    raise Exception(f"Failed to search emails: {error_response}")

            data = response.json()
            if not data.get("value"):
                logging.warning("No search results found")
                return []

            emails = []
            for message in data["value"]:
                try:
                    emails.append(
                        {
                            "id": message["id"],
                            "subject": message.get("subject", "(No Subject)"),
                            "sender": message.get("from", {})
                            .get("emailAddress", {})
                            .get("address", "unknown"),
                            "received_time": message.get("receivedDateTime", ""),
                            "body": message.get("body", {}).get("content", ""),
                            "has_attachments": message.get("hasAttachments", False),
                        }
                    )
                    if len(emails) >= max_emails:
                        break
                except KeyError as ke:
                    logging.error(f"Key error processing search result: {ke}")
                    continue

            return emails

        except Exception as e:
            logging.error(f"Error searching emails: {str(e)}")
            return []

    async def microsoft_reply_to_email(self, message_id, body, attachments=None):
        """
        Replies to a specific email.

        Args:
            message_id (str): ID of the email to reply to
            body (str): Reply content
            attachments (list): Optional list of file paths to attach

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            if not message_id:
                return "Failed to reply: No message ID provided"

            # First verify the message exists
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            try:
                check_response = requests.get(
                    f"https://graph.microsoft.com/v1.0/me/messages/{message_id}",
                    headers=headers,
                )
                if check_response.status_code != 200:
                    return f"Failed to find email with ID {message_id}: {check_response.status_code}"
            except Exception as e:
                logging.error(f"Error checking message existence: {str(e)}")

            # Prepare reply data
            reply_data = {
                "message": {"body": {"contentType": "HTML", "content": body}},
                "comment": "",
            }

            # Process attachments if any
            if attachments:
                reply_data["message"]["attachments"] = []
                for attachment_path in attachments:
                    if os.path.exists(attachment_path):
                        try:
                            with open(attachment_path, "rb") as file:
                                content = file.read()
                                reply_data["message"]["attachments"].append(
                                    {
                                        "@odata.type": "#microsoft.graph.fileAttachment",
                                        "name": os.path.basename(attachment_path),
                                        "contentBytes": base64.b64encode(
                                            content
                                        ).decode(),
                                    }
                                )
                        except Exception as attach_err:
                            logging.error(
                                f"Error attaching file {attachment_path}: {str(attach_err)}"
                            )

            # Send reply request
            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply",
                headers=headers,
                json=reply_data,
            )

            if response.status_code == 202:
                return "Reply sent successfully."
            else:
                error_response = response.text
                logging.error(f"Reply API error: {error_response}")

                # Try an alternative approach - create a new message as a reply
                try:
                    # Get the original message details
                    msg_response = requests.get(
                        f"https://graph.microsoft.com/v1.0/me/messages/{message_id}",
                        headers=headers,
                    )

                    if msg_response.status_code == 200:
                        original_msg = msg_response.json()

                        # Create a reply message
                        new_message = {
                            "subject": f"RE: {original_msg.get('subject', '')}",
                            "body": {"contentType": "HTML", "content": body},
                            "toRecipients": [
                                {
                                    "emailAddress": original_msg.get("from", {}).get(
                                        "emailAddress", {}
                                    )
                                }
                            ],
                            "conversationId": original_msg.get("conversationId"),
                        }

                        if attachments and reply_data.get("message", {}).get(
                            "attachments"
                        ):
                            new_message["attachments"] = reply_data["message"][
                                "attachments"
                            ]

                        create_response = requests.post(
                            "https://graph.microsoft.com/v1.0/me/messages",
                            headers=headers,
                            json=new_message,
                        )

                        if create_response.status_code == 201:
                            # Send the new message
                            message_id = create_response.json().get("id")
                            send_response = requests.post(
                                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/send",
                                headers=headers,
                            )

                            if send_response.status_code == 202:
                                return "Reply created and sent as a new message."

                        logging.error(
                            f"Alternative reply method failed: {create_response.status_code}"
                        )
                except Exception as alt_err:
                    logging.error(f"Error in alternative reply method: {str(alt_err)}")

                raise Exception(
                    f"Failed to send reply (Status {response.status_code}): {error_response}"
                )

        except Exception as e:
            logging.error(f"Error sending reply: {str(e)}")
            return f"Failed to send reply: {str(e)}"

    async def microsoft_process_attachments(self, message_id):
        """
        Downloads attachments from a specific email.

        Args:
            message_id (str): ID of the email containing attachments

        Returns:
            list: List of paths to saved attachment files
        """
        try:
            self.verify_user()

            if not message_id:
                return "Failed to process attachments: No message ID provided"

            headers = {"Authorization": f"Bearer {self.access_token}"}

            # First verify the message exists and has attachments
            try:
                message_response = requests.get(
                    f"https://graph.microsoft.com/v1.0/me/messages/{message_id}",
                    headers=headers,
                )

                if message_response.status_code != 200:
                    logging.error(f"Error checking message: {message_response.text}")
                    return []

                message_data = message_response.json()
                has_attachments = message_data.get("hasAttachments", False)

                if not has_attachments:
                    logging.info(f"Message {message_id} has no attachments")
                    return []

            except Exception as msg_err:
                logging.error(f"Error checking message: {str(msg_err)}")
                # Continue anyway in case we can still get attachments

            # Get attachments metadata
            attachments_response = requests.get(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments",
                headers=headers,
            )

            if attachments_response.status_code != 200:
                error_response = attachments_response.text
                logging.error(f"Attachments API error: {error_response}")
                raise Exception(
                    f"Failed to get attachments (Status {attachments_response.status_code}): {error_response}"
                )

            attachment_data = attachments_response.json()
            if not attachment_data.get("value"):
                logging.warning(f"No attachments found for message {message_id}")
                return []

            saved_files = []

            # Ensure attachments directory exists
            os.makedirs(self.attachments_dir, exist_ok=True)

            for attachment in attachment_data["value"]:
                try:
                    # Check if it's a file attachment (could also be an item attachment)
                    if (
                        attachment.get("@odata.type")
                        == "#microsoft.graph.fileAttachment"
                    ):
                        attachment_id = attachment.get("id")
                        attachment_name = attachment.get(
                            "name", f"attachment_{attachment_id}"
                        )

                        # Some large attachments might not include contentBytes directly
                        # so we make a separate request for the individual attachment
                        if not attachment.get("contentBytes"):
                            attachment_detail_response = requests.get(
                                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments/{attachment_id}",
                                headers=headers,
                            )

                            if attachment_detail_response.status_code == 200:
                                attachment_detail = attachment_detail_response.json()
                                content_bytes = attachment_detail.get("contentBytes")
                            else:
                                logging.error(
                                    f"Failed to get attachment content: {attachment_detail_response.text}"
                                )
                                continue
                        else:
                            content_bytes = attachment.get("contentBytes")

                        if not content_bytes:
                            logging.error(
                                f"No content found for attachment {attachment_name}"
                            )
                            continue

                        # Save the attachment
                        file_path = os.path.join(self.attachments_dir, attachment_name)
                        with open(file_path, "wb") as f:
                            f.write(base64.b64decode(content_bytes))
                        saved_files.append(file_path)
                        logging.info(f"Successfully saved attachment: {file_path}")
                except Exception as attachment_err:
                    logging.error(f"Error processing attachment: {str(attachment_err)}")
                    continue

            return saved_files

        except Exception as e:
            logging.error(f"Error processing attachments: {str(e)}")
            return []

    # ==================== OneDrive Methods ====================

    async def onedrive_list_files(self, folder_path="root", max_items=50):
        """
        Lists files and folders in OneDrive.

        Args:
            folder_path (str): Path to the folder to list (use "root" for root folder, or a path like "Documents/Reports")
            max_items (int): Maximum number of items to retrieve

        Returns:
            list: List of file/folder dictionaries with id, name, type, size, and other metadata
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Build the URL based on folder path
            if folder_path == "root" or not folder_path:
                url = f"https://graph.microsoft.com/v1.0/me/drive/root/children?$top={max_items}"
            else:
                # Encode the path properly
                encoded_path = folder_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/children?$top={max_items}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"OneDrive list files error: {response.text}")
                return {"error": f"Failed to list files: {response.text}"}

            data = response.json()
            items = []

            for item in data.get("value", []):
                item_info = {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": "folder" if "folder" in item else "file",
                    "size": item.get("size", 0),
                    "created_time": item.get("createdDateTime"),
                    "modified_time": item.get("lastModifiedDateTime"),
                    "web_url": item.get("webUrl"),
                }

                if "file" in item:
                    item_info["mime_type"] = item.get("file", {}).get("mimeType")

                if "folder" in item:
                    item_info["child_count"] = item.get("folder", {}).get(
                        "childCount", 0
                    )

                items.append(item_info)

            return items

        except Exception as e:
            logging.error(f"Error listing OneDrive files: {str(e)}")
            return {"error": str(e)}

    async def onedrive_get_file_content(self, file_path=None, file_id=None):
        """
        Gets the content of a file from OneDrive. Works best with text-based files.

        Args:
            file_path (str): Path to the file (e.g., "Documents/report.txt")
            file_id (str): Alternatively, the unique file ID

        Returns:
            str: File content as text, or base64-encoded content for binary files
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            # Build URL based on whether we have path or ID
            if file_id:
                url = (
                    f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content"
                )
            elif file_path:
                encoded_path = file_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/content"
            else:
                return {"error": "Either file_path or file_id must be provided"}

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"OneDrive get file error: {response.text}")
                return {"error": f"Failed to get file content: {response.text}"}

            # Try to decode as text first
            try:
                return {"content": response.text, "encoding": "text"}
            except:
                # If text decoding fails, return base64
                return {
                    "content": base64.b64encode(response.content).decode(),
                    "encoding": "base64",
                }

        except Exception as e:
            logging.error(f"Error getting OneDrive file content: {str(e)}")
            return {"error": str(e)}

    async def onedrive_upload_file(self, file_path, destination_path, content=None):
        """
        Uploads a file to OneDrive.

        Args:
            file_path (str): Local path to the file to upload, OR if content is provided, this is used as just the filename
            destination_path (str): Destination path in OneDrive (e.g., "Documents/uploads/myfile.txt")
            content (str): Optional - direct content to upload instead of reading from file_path

        Returns:
            dict: Upload result with file ID and web URL
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
            }

            # Get file content
            if content:
                file_content = content.encode() if isinstance(content, str) else content
            elif os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    file_content = f.read()
            else:
                return {"error": f"File not found: {file_path}"}

            # For files <= 4MB, use simple upload
            if len(file_content) <= 4 * 1024 * 1024:
                encoded_dest = destination_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_dest}:/content"

                response = requests.put(url, headers=headers, data=file_content)

                if response.status_code in [200, 201]:
                    result = response.json()
                    return {
                        "success": True,
                        "id": result.get("id"),
                        "name": result.get("name"),
                        "web_url": result.get("webUrl"),
                        "size": result.get("size"),
                    }
                else:
                    logging.error(f"OneDrive upload error: {response.text}")
                    return {"error": f"Failed to upload file: {response.text}"}
            else:
                # For larger files, use upload session
                return await self._onedrive_upload_large_file(
                    destination_path, file_content
                )

        except Exception as e:
            logging.error(f"Error uploading to OneDrive: {str(e)}")
            return {"error": str(e)}

    async def _onedrive_upload_large_file(self, destination_path, file_content):
        """
        Handles upload of files larger than 4MB using upload session.
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Create upload session
            encoded_dest = destination_path.replace(" ", "%20")
            session_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_dest}:/createUploadSession"

            session_response = requests.post(
                session_url,
                headers=headers,
                json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            )

            if session_response.status_code != 200:
                return {
                    "error": f"Failed to create upload session: {session_response.text}"
                }

            upload_url = session_response.json().get("uploadUrl")
            file_size = len(file_content)
            chunk_size = 320 * 1024 * 10  # 3.2 MB chunks

            for i in range(0, file_size, chunk_size):
                chunk = file_content[i : i + chunk_size]
                chunk_end = min(i + chunk_size, file_size) - 1

                chunk_headers = {
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {i}-{chunk_end}/{file_size}",
                }

                chunk_response = requests.put(
                    upload_url, headers=chunk_headers, data=chunk
                )

                if chunk_response.status_code not in [200, 201, 202]:
                    return {"error": f"Failed to upload chunk: {chunk_response.text}"}

            # Get final response
            final_data = chunk_response.json()
            return {
                "success": True,
                "id": final_data.get("id"),
                "name": final_data.get("name"),
                "web_url": final_data.get("webUrl"),
                "size": final_data.get("size"),
            }

        except Exception as e:
            logging.error(f"Error in large file upload: {str(e)}")
            return {"error": str(e)}

    async def onedrive_download_file(self, file_path=None, file_id=None, save_to=None):
        """
        Downloads a file from OneDrive.

        Args:
            file_path (str): Path to the file in OneDrive
            file_id (str): Alternatively, the unique file ID
            save_to (str): Local path to save the file. If not provided, saves to attachments directory

        Returns:
            dict: Download result with local file path
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            # First get file metadata
            if file_id:
                meta_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}"
            elif file_path:
                encoded_path = file_path.replace(" ", "%20")
                meta_url = (
                    f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}"
                )
            else:
                return {"error": "Either file_path or file_id must be provided"}

            meta_response = requests.get(meta_url, headers=headers)
            if meta_response.status_code != 200:
                return {"error": f"Failed to get file metadata: {meta_response.text}"}

            file_metadata = meta_response.json()
            file_name = file_metadata.get("name", "downloaded_file")

            # Get download URL
            download_url = file_metadata.get("@microsoft.graph.downloadUrl")
            if not download_url:
                # Try to get content directly
                if file_id:
                    content_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content"
                else:
                    content_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/content"
                download_response = requests.get(content_url, headers=headers)
            else:
                download_response = requests.get(download_url)

            if download_response.status_code != 200:
                return {"error": f"Failed to download file: {download_response.text}"}

            # Determine save path
            if save_to:
                local_path = save_to
            else:
                os.makedirs(self.attachments_dir, exist_ok=True)
                local_path = os.path.join(self.attachments_dir, file_name)

            # Save file
            with open(local_path, "wb") as f:
                f.write(download_response.content)

            return {
                "success": True,
                "local_path": local_path,
                "file_name": file_name,
                "size": len(download_response.content),
            }

        except Exception as e:
            logging.error(f"Error downloading from OneDrive: {str(e)}")
            return {"error": str(e)}

    async def onedrive_create_folder(self, folder_name, parent_path="root"):
        """
        Creates a new folder in OneDrive.

        Args:
            folder_name (str): Name of the folder to create
            parent_path (str): Path to the parent folder (use "root" for root)

        Returns:
            dict: Created folder information
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Build URL based on parent path
            if parent_path == "root" or not parent_path:
                url = "https://graph.microsoft.com/v1.0/me/drive/root/children"
            else:
                encoded_path = parent_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/children"

            folder_data = {
                "name": folder_name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename",
            }

            response = requests.post(url, headers=headers, json=folder_data)

            if response.status_code == 201:
                result = response.json()
                return {
                    "success": True,
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "web_url": result.get("webUrl"),
                }
            else:
                logging.error(f"OneDrive create folder error: {response.text}")
                return {"error": f"Failed to create folder: {response.text}"}

        except Exception as e:
            logging.error(f"Error creating OneDrive folder: {str(e)}")
            return {"error": str(e)}

    async def onedrive_delete_item(self, item_path=None, item_id=None):
        """
        Deletes a file or folder from OneDrive.

        Args:
            item_path (str): Path to the item to delete
            item_id (str): Alternatively, the unique item ID

        Returns:
            dict: Deletion result
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            if item_id:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}"
            elif item_path:
                encoded_path = item_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}"
            else:
                return {"error": "Either item_path or item_id must be provided"}

            response = requests.delete(url, headers=headers)

            if response.status_code == 204:
                return {"success": True, "message": "Item deleted successfully"}
            else:
                logging.error(f"OneDrive delete error: {response.text}")
                return {"error": f"Failed to delete item: {response.text}"}

        except Exception as e:
            logging.error(f"Error deleting OneDrive item: {str(e)}")
            return {"error": str(e)}

    async def onedrive_search(self, query, max_results=25):
        """
        Searches for files and folders in OneDrive.

        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return

        Returns:
            list: List of matching items
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{query}')?$top={max_results}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"OneDrive search error: {response.text}")
                return {"error": f"Search failed: {response.text}"}

            data = response.json()
            items = []

            for item in data.get("value", []):
                item_info = {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": "folder" if "folder" in item else "file",
                    "size": item.get("size", 0),
                    "path": item.get("parentReference", {}).get("path", ""),
                    "web_url": item.get("webUrl"),
                    "modified_time": item.get("lastModifiedDateTime"),
                }
                items.append(item_info)

            return items

        except Exception as e:
            logging.error(f"Error searching OneDrive: {str(e)}")
            return {"error": str(e)}

    async def onedrive_move_item(
        self, item_path=None, item_id=None, new_parent_path=None, new_name=None
    ):
        """
        Moves or renames an item in OneDrive.

        Args:
            item_path (str): Path to the item to move
            item_id (str): Alternatively, the unique item ID
            new_parent_path (str): New parent folder path (for moving)
            new_name (str): New name (for renaming)

        Returns:
            dict: Move result with new item location
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get item URL
            if item_id:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}"
            elif item_path:
                encoded_path = item_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}"
            else:
                return {"error": "Either item_path or item_id must be provided"}

            update_data = {}

            if new_name:
                update_data["name"] = new_name

            if new_parent_path:
                # Get parent folder ID
                if new_parent_path == "root":
                    parent_url = "https://graph.microsoft.com/v1.0/me/drive/root"
                else:
                    encoded_parent = new_parent_path.replace(" ", "%20")
                    parent_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_parent}"

                parent_response = requests.get(parent_url, headers=headers)
                if parent_response.status_code != 200:
                    return {"error": f"Parent folder not found: {parent_response.text}"}

                parent_id = parent_response.json().get("id")
                update_data["parentReference"] = {"id": parent_id}

            if not update_data:
                return {"error": "Either new_parent_path or new_name must be provided"}

            response = requests.patch(url, headers=headers, json=update_data)

            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "web_url": result.get("webUrl"),
                }
            else:
                logging.error(f"OneDrive move error: {response.text}")
                return {"error": f"Failed to move item: {response.text}"}

        except Exception as e:
            logging.error(f"Error moving OneDrive item: {str(e)}")
            return {"error": str(e)}

    async def onedrive_copy_item(
        self, item_path=None, item_id=None, destination_path=None, new_name=None
    ):
        """
        Copies an item in OneDrive.

        Args:
            item_path (str): Path to the item to copy
            item_id (str): Alternatively, the unique item ID
            destination_path (str): Destination folder path
            new_name (str): Optional new name for the copy

        Returns:
            dict: Copy operation result
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get item URL for copy operation
            if item_id:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/copy"
            elif item_path:
                encoded_path = item_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/copy"
            else:
                return {"error": "Either item_path or item_id must be provided"}

            # Get destination folder ID
            if destination_path == "root" or not destination_path:
                dest_url = "https://graph.microsoft.com/v1.0/me/drive/root"
            else:
                encoded_dest = destination_path.replace(" ", "%20")
                dest_url = (
                    f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_dest}"
                )

            dest_response = requests.get(dest_url, headers=headers)
            if dest_response.status_code != 200:
                return {"error": f"Destination folder not found: {dest_response.text}"}

            dest_id = dest_response.json().get("id")

            copy_data = {"parentReference": {"id": dest_id}}

            if new_name:
                copy_data["name"] = new_name

            response = requests.post(url, headers=headers, json=copy_data)

            if response.status_code == 202:
                # Copy is asynchronous, return monitor URL
                monitor_url = response.headers.get("Location")
                return {
                    "success": True,
                    "status": "copying",
                    "monitor_url": monitor_url,
                    "message": "Copy operation started. Use the monitor URL to check progress.",
                }
            else:
                logging.error(f"OneDrive copy error: {response.text}")
                return {"error": f"Failed to copy item: {response.text}"}

        except Exception as e:
            logging.error(f"Error copying OneDrive item: {str(e)}")
            return {"error": str(e)}

    # ==================== SharePoint Methods ====================

    async def sharepoint_list_sites(self, search_query=None, max_sites=25):
        """
        Lists SharePoint sites the user has access to.

        Args:
            search_query (str): Optional search query to filter sites
            max_sites (int): Maximum number of sites to return

        Returns:
            list: List of SharePoint sites
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if search_query:
                url = f"https://graph.microsoft.com/v1.0/sites?search={search_query}&$top={max_sites}"
            else:
                # Get sites the user is following or has access to
                url = (
                    f"https://graph.microsoft.com/v1.0/sites?search=*&$top={max_sites}"
                )

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint list sites error: {response.text}")
                return {"error": f"Failed to list sites: {response.text}"}

            data = response.json()
            sites = []

            for site in data.get("value", []):
                sites.append(
                    {
                        "id": site.get("id"),
                        "name": site.get("displayName") or site.get("name"),
                        "description": site.get("description"),
                        "web_url": site.get("webUrl"),
                        "created_time": site.get("createdDateTime"),
                    }
                )

            return sites

        except Exception as e:
            logging.error(f"Error listing SharePoint sites: {str(e)}")
            return {"error": str(e)}

    async def sharepoint_get_site(self, site_id=None, site_url=None):
        """
        Gets details of a specific SharePoint site.

        Args:
            site_id (str): The site ID
            site_url (str): Alternatively, the site URL (e.g., "contoso.sharepoint.com:/sites/team")

        Returns:
            dict: Site details
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if site_id:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}"
            elif site_url:
                # Parse site URL to construct the API path
                # Format: hostname:/path (e.g., contoso.sharepoint.com:/sites/team)
                url = f"https://graph.microsoft.com/v1.0/sites/{site_url}"
            else:
                return {"error": "Either site_id or site_url must be provided"}

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint get site error: {response.text}")
                return {"error": f"Failed to get site: {response.text}"}

            site = response.json()
            return {
                "id": site.get("id"),
                "name": site.get("displayName") or site.get("name"),
                "description": site.get("description"),
                "web_url": site.get("webUrl"),
                "created_time": site.get("createdDateTime"),
            }

        except Exception as e:
            logging.error(f"Error getting SharePoint site: {str(e)}")
            return {"error": str(e)}

    async def sharepoint_list_libraries(self, site_id):
        """
        Lists document libraries in a SharePoint site.

        Args:
            site_id (str): The SharePoint site ID

        Returns:
            list: List of document libraries
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint list libraries error: {response.text}")
                return {"error": f"Failed to list libraries: {response.text}"}

            data = response.json()
            libraries = []

            for drive in data.get("value", []):
                libraries.append(
                    {
                        "id": drive.get("id"),
                        "name": drive.get("name"),
                        "description": drive.get("description"),
                        "web_url": drive.get("webUrl"),
                        "drive_type": drive.get("driveType"),
                        "quota_used": drive.get("quota", {}).get("used"),
                        "quota_total": drive.get("quota", {}).get("total"),
                    }
                )

            return libraries

        except Exception as e:
            logging.error(f"Error listing SharePoint libraries: {str(e)}")
            return {"error": str(e)}

    async def sharepoint_list_files(
        self, site_id, drive_id=None, folder_path="root", max_items=50
    ):
        """
        Lists files in a SharePoint document library.

        Args:
            site_id (str): The SharePoint site ID
            drive_id (str): The document library (drive) ID. If not provided, uses the default library
            folder_path (str): Path within the library (use "root" for root)
            max_items (int): Maximum number of items to return

        Returns:
            list: List of files and folders
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # If no drive_id, get the default document library
            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {
                        "error": f"Failed to get default library: {drive_response.text}"
                    }
                drive_id = drive_response.json().get("id")

            # Build URL based on folder path
            if folder_path == "root" or not folder_path:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/children?$top={max_items}"
            else:
                encoded_path = folder_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/children?$top={max_items}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint list files error: {response.text}")
                return {"error": f"Failed to list files: {response.text}"}

            data = response.json()
            items = []

            for item in data.get("value", []):
                item_info = {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": "folder" if "folder" in item else "file",
                    "size": item.get("size", 0),
                    "created_time": item.get("createdDateTime"),
                    "modified_time": item.get("lastModifiedDateTime"),
                    "web_url": item.get("webUrl"),
                    "created_by": item.get("createdBy", {})
                    .get("user", {})
                    .get("displayName"),
                    "modified_by": item.get("lastModifiedBy", {})
                    .get("user", {})
                    .get("displayName"),
                }

                if "file" in item:
                    item_info["mime_type"] = item.get("file", {}).get("mimeType")

                if "folder" in item:
                    item_info["child_count"] = item.get("folder", {}).get(
                        "childCount", 0
                    )

                items.append(item_info)

            return items

        except Exception as e:
            logging.error(f"Error listing SharePoint files: {str(e)}")
            return {"error": str(e)}

    async def sharepoint_get_file_content(
        self, site_id, drive_id=None, file_path=None, file_id=None
    ):
        """
        Gets the content of a file from SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            drive_id (str): The document library ID (optional, uses default if not provided)
            file_path (str): Path to the file
            file_id (str): Alternatively, the unique file ID

        Returns:
            dict: File content
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            # If no drive_id, get the default document library
            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {
                        "error": f"Failed to get default library: {drive_response.text}"
                    }
                drive_id = drive_response.json().get("id")

            # Build URL
            if file_id:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{file_id}/content"
            elif file_path:
                encoded_path = file_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/content"
            else:
                return {"error": "Either file_path or file_id must be provided"}

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint get file error: {response.text}")
                return {"error": f"Failed to get file content: {response.text}"}

            try:
                return {"content": response.text, "encoding": "text"}
            except:
                return {
                    "content": base64.b64encode(response.content).decode(),
                    "encoding": "base64",
                }

        except Exception as e:
            logging.error(f"Error getting SharePoint file content: {str(e)}")
            return {"error": str(e)}

    async def sharepoint_upload_file(
        self, site_id, destination_path, file_path=None, content=None, drive_id=None
    ):
        """
        Uploads a file to SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            destination_path (str): Destination path in the library
            file_path (str): Local file path or filename if content is provided
            content (str): Direct content to upload
            drive_id (str): Document library ID (optional)

        Returns:
            dict: Upload result
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
            }

            # Get file content
            if content:
                file_content = content.encode() if isinstance(content, str) else content
            elif file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    file_content = f.read()
            else:
                return {"error": f"File not found: {file_path}"}

            # If no drive_id, get the default document library
            if not drive_id:
                get_headers = {
                    "Authorization": f"Bearer {self.access_token}",
                }
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=get_headers)
                if drive_response.status_code != 200:
                    return {
                        "error": f"Failed to get default library: {drive_response.text}"
                    }
                drive_id = drive_response.json().get("id")

            encoded_dest = destination_path.replace(" ", "%20")
            url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_dest}:/content"

            response = requests.put(url, headers=headers, data=file_content)

            if response.status_code in [200, 201]:
                result = response.json()
                return {
                    "success": True,
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "web_url": result.get("webUrl"),
                    "size": result.get("size"),
                }
            else:
                logging.error(f"SharePoint upload error: {response.text}")
                return {"error": f"Failed to upload file: {response.text}"}

        except Exception as e:
            logging.error(f"Error uploading to SharePoint: {str(e)}")
            return {"error": str(e)}

    async def sharepoint_download_file(
        self, site_id, drive_id=None, file_path=None, file_id=None, save_to=None
    ):
        """
        Downloads a file from SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            drive_id (str): The document library ID (optional)
            file_path (str): Path to the file in SharePoint
            file_id (str): Alternatively, the unique file ID
            save_to (str): Local path to save the file

        Returns:
            dict: Download result with local file path
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            # If no drive_id, get the default document library
            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {
                        "error": f"Failed to get default library: {drive_response.text}"
                    }
                drive_id = drive_response.json().get("id")

            # Get file metadata first
            if file_id:
                meta_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{file_id}"
            elif file_path:
                encoded_path = file_path.replace(" ", "%20")
                meta_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}"
            else:
                return {"error": "Either file_path or file_id must be provided"}

            meta_response = requests.get(meta_url, headers=headers)
            if meta_response.status_code != 200:
                return {"error": f"Failed to get file metadata: {meta_response.text}"}

            file_metadata = meta_response.json()
            file_name = file_metadata.get("name", "downloaded_file")

            # Get download URL
            download_url = file_metadata.get("@microsoft.graph.downloadUrl")
            if not download_url:
                if file_id:
                    content_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{file_id}/content"
                else:
                    content_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/content"
                download_response = requests.get(content_url, headers=headers)
            else:
                download_response = requests.get(download_url)

            if download_response.status_code != 200:
                return {"error": f"Failed to download file: {download_response.text}"}

            # Determine save path
            if save_to:
                local_path = save_to
            else:
                os.makedirs(self.attachments_dir, exist_ok=True)
                local_path = os.path.join(self.attachments_dir, file_name)

            with open(local_path, "wb") as f:
                f.write(download_response.content)

            return {
                "success": True,
                "local_path": local_path,
                "file_name": file_name,
                "size": len(download_response.content),
            }

        except Exception as e:
            logging.error(f"Error downloading from SharePoint: {str(e)}")
            return {"error": str(e)}

    async def sharepoint_create_folder(
        self, site_id, folder_name, parent_path="root", drive_id=None
    ):
        """
        Creates a folder in SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            folder_name (str): Name of the folder to create
            parent_path (str): Parent folder path
            drive_id (str): Document library ID (optional)

        Returns:
            dict: Created folder information
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # If no drive_id, get the default document library
            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {
                        "error": f"Failed to get default library: {drive_response.text}"
                    }
                drive_id = drive_response.json().get("id")

            # Build URL
            if parent_path == "root" or not parent_path:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/children"
            else:
                encoded_path = parent_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/children"

            folder_data = {
                "name": folder_name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename",
            }

            response = requests.post(url, headers=headers, json=folder_data)

            if response.status_code == 201:
                result = response.json()
                return {
                    "success": True,
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "web_url": result.get("webUrl"),
                }
            else:
                logging.error(f"SharePoint create folder error: {response.text}")
                return {"error": f"Failed to create folder: {response.text}"}

        except Exception as e:
            logging.error(f"Error creating SharePoint folder: {str(e)}")
            return {"error": str(e)}

    async def sharepoint_delete_item(
        self, site_id, drive_id=None, item_path=None, item_id=None
    ):
        """
        Deletes a file or folder from SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            drive_id (str): Document library ID (optional)
            item_path (str): Path to the item
            item_id (str): Alternatively, the unique item ID

        Returns:
            dict: Deletion result
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            # If no drive_id, get the default document library
            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {
                        "error": f"Failed to get default library: {drive_response.text}"
                    }
                drive_id = drive_response.json().get("id")

            if item_id:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{item_id}"
            elif item_path:
                encoded_path = item_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}"
            else:
                return {"error": "Either item_path or item_id must be provided"}

            response = requests.delete(url, headers=headers)

            if response.status_code == 204:
                return {"success": True, "message": "Item deleted successfully"}
            else:
                logging.error(f"SharePoint delete error: {response.text}")
                return {"error": f"Failed to delete item: {response.text}"}

        except Exception as e:
            logging.error(f"Error deleting SharePoint item: {str(e)}")
            return {"error": str(e)}

    async def sharepoint_search(self, query, site_id=None, max_results=25):
        """
        Searches for files across SharePoint. Can search a specific site or all accessible sites.

        Args:
            query (str): Search query
            site_id (str): Optional site ID to limit search to a specific site
            max_results (int): Maximum number of results

        Returns:
            list: List of matching items
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if site_id:
                # Search within a specific site's default drive
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {"error": f"Failed to get site drive: {drive_response.text}"}
                drive_id = drive_response.json().get("id")

                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/search(q='{query}')?$top={max_results}"
            else:
                # Search across all SharePoint using the search API
                url = "https://graph.microsoft.com/v1.0/search/query"
                search_body = {
                    "requests": [
                        {
                            "entityTypes": ["driveItem"],
                            "query": {"queryString": query},
                            "from": 0,
                            "size": max_results,
                        }
                    ]
                }

                response = requests.post(url, headers=headers, json=search_body)

                if response.status_code != 200:
                    logging.error(f"SharePoint search error: {response.text}")
                    return {"error": f"Search failed: {response.text}"}

                data = response.json()
                items = []

                for hit_container in data.get("value", []):
                    for hit in hit_container.get("hitsContainers", []):
                        for result in hit.get("hits", []):
                            resource = result.get("resource", {})
                            items.append(
                                {
                                    "id": resource.get("id"),
                                    "name": resource.get("name"),
                                    "web_url": resource.get("webUrl"),
                                    "size": resource.get("size"),
                                    "modified_time": resource.get(
                                        "lastModifiedDateTime"
                                    ),
                                    "site_name": resource.get(
                                        "parentReference", {}
                                    ).get("siteId"),
                                }
                            )

                return items

            # For site-specific search, use the drive search endpoint
            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint search error: {response.text}")
                return {"error": f"Search failed: {response.text}"}

            data = response.json()
            items = []

            for item in data.get("value", []):
                items.append(
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "type": "folder" if "folder" in item else "file",
                        "size": item.get("size", 0),
                        "path": item.get("parentReference", {}).get("path", ""),
                        "web_url": item.get("webUrl"),
                        "modified_time": item.get("lastModifiedDateTime"),
                    }
                )

            return items

        except Exception as e:
            logging.error(f"Error searching SharePoint: {str(e)}")
            return {"error": str(e)}
