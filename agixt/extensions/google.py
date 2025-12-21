from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
import os
import mimetypes
import email
from base64 import urlsafe_b64decode
import logging
import requests
import json
import asyncio
from typing import Dict, List, Any, Optional
from fastapi import HTTPException
from Extensions import Extensions
from MagicalAuth import MagicalAuth
from Globals import getenv, install_package_if_missing

install_package_if_missing("google-api-python-client", "googleapiclient")
install_package_if_missing("google-ads", "google.ads.googleads")

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.ads.googleads.client import GoogleAdsClient

"""
Required environment variables:

- GOOGLE_CLIENT_ID: Google OAuth client ID
- GOOGLE_CLIENT_SECRET: Google OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` environment variables to your `.env` file.

- People API https://console.cloud.google.com/marketplace/product/google/people.googleapis.com
- Gmail API https://console.cloud.google.com/marketplace/product/google/gmail.googleapis.com

Required scopes for Google SSO
"""

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    # Marketing scopes for Google Ads, Analytics, and Tag Manager
    "https://www.googleapis.com/auth/adwords",  # Google Ads management
    "https://www.googleapis.com/auth/analytics.readonly",  # GA4 data read
    "https://www.googleapis.com/auth/analytics.edit",  # GA4 configuration
    "https://www.googleapis.com/auth/tagmanager.edit.containers",  # GTM containers
    "https://www.googleapis.com/auth/tagmanager.publish",  # GTM publishing
    "https://www.googleapis.com/auth/content",  # Merchant Center (optional)
]
AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
PKCE_REQUIRED = False


class GoogleSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("GOOGLE_CLIENT_ID")
        self.client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.email_address = None  # Initialize this
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
            raise Exception(f"Google token refresh failed: {response.text}")

        token_data = response.json()

        # Update our access token for immediate use
        if "access_token" in token_data:
            self.access_token = token_data["access_token"]

        return token_data

    def get_user_info(self):
        uri = "https://people.googleapis.com/v1/people/me?personFields=names,emailAddresses"
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
            self.email_address = email  # Set this here
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Google",
            )


def sso(code, redirect_uri=None) -> GoogleSSO:
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
        return None  # Fixed from return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else None
    return GoogleSSO(access_token=access_token, refresh_token=refresh_token)


class google(Extensions):
    """
    The Google extension provides comprehensive functionality for interacting with Google services including:
    - Gmail: Send, manage, and organize emails
    - Google Calendar: Manage events and availability
    - Google Keep: Create and manage notes
    - Google Ads: Campaign management, ad groups, keywords, and performance metrics
    - Google Analytics: GA4 properties, reports, and audience data
    - Google Tag Manager: Container management, tags, triggers, and variables

    This extension uses the logged-in user's Google account through OAuth authentication.
    """

    CATEGORY = "Productivity"

    def __init__(
        self,
        **kwargs,
    ):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("GOOGLE_ACCESS_TOKEN", None)
        self.auth = None
        google_client_id = getenv("GOOGLE_CLIENT_ID")
        google_client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.google_ads_customer_id = getenv("GOOGLE_ADS_CUSTOMER_ID")
        self.timezone = getenv("TZ")

        # Initialize session for API requests
        self.session = requests.Session()
        if self.access_token:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                }
            )

        if google_client_id and google_client_secret:
            self.commands = {
                # Email commands
                "Google - Get Emails": self.get_emails,
                "Google - Send Email": self.send_email,
                "Google - Move Email to Folder": self.move_email_to_folder,
                "Google - Create Draft Email": self.create_draft_email,
                "Google - Delete Email": self.delete_email,
                "Google - Search Emails": self.search_emails,
                "Google - Reply to Email": self.reply_to_email,
                "Google - Process Attachments": self.process_attachments,
                # Calendar commands
                "Google - Get Calendar Items": self.get_calendar_items,
                "Google - Get Available Timeslots": self.get_available_timeslots,
                "Google - Add Calendar Item": self.add_calendar_item,
                "Google - Modify Calendar Item": self.modify_calendar_item,
                "Google - Remove Calendar Item": self.remove_calendar_item,
                # Keep Notes commands
                "Google - Get Keep Notes": self.get_keep_notes,
                "Google - Create Keep Note": self.create_keep_note,
                "Google - Delete Keep Note": self.delete_keep_note,
                # Google Ads commands
                "Google Ads - Get Accounts": self.get_google_ads_accounts,
                "Google Ads - Create Campaign": self.create_google_ads_campaign,
                "Google Ads - Get Campaigns": self.get_google_ads_campaigns,
                "Google Ads - Update Campaign": self.update_google_ads_campaign,
                "Google Ads - Create Ad Group": self.create_google_ads_ad_group,
                "Google Ads - Get Ad Groups": self.get_google_ads_ad_groups,
                "Google Ads - Create Ad": self.create_google_ads_ad,
                "Google Ads - Get Performance": self.get_google_ads_performance,
                "Google Ads - Manage Keywords": self.manage_google_ads_keywords,
                "Google Ads - Create Audience": self.create_google_ads_audience,
                # Google Analytics commands
                "Google Analytics - Get Properties": self.get_analytics_properties,
                "Google Analytics - Get Reports": self.get_analytics_reports,
                "Google Analytics - Get Real Time Data": self.get_analytics_realtime,
                "Google Analytics - Get Audiences": self.get_analytics_audiences,
                "Google Analytics - Create Custom Dimension": self.create_analytics_dimension,
                # Google Tag Manager commands
                "GTM - Get Containers": self.get_gtm_containers,
                "GTM - Create Tag": self.create_gtm_tag,
                "GTM - Update Tag": self.update_gtm_tag,
                "GTM - Create Trigger": self.create_gtm_trigger,
                "GTM - Create Variable": self.create_gtm_variable,
                "GTM - Publish Container": self.publish_gtm_container,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                    self.timezone = self.auth.get_timezone()
                except Exception as e:
                    logging.error(f"Error initializing Google extension: {str(e)}")
        self.attachments_dir = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else "./WORKSPACE/attachments"
        )
        os.makedirs(self.attachments_dir, exist_ok=True)

    def authenticate(self):
        """
        Verifies that the current access token corresponds to a valid user.
        If the /me endpoint fails, refreshes the token using the OAuth refresh flow.
        """
        if self.auth:
            # Get both access and refresh tokens from MagicalAuth
            oauth_data = self.auth.get_oauth_functions("google")
            if oauth_data and hasattr(oauth_data, "refresh_token"):
                credentials = Credentials(
                    token=self.access_token,
                    refresh_token=oauth_data.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=getenv("GOOGLE_CLIENT_ID"),
                    client_secret=getenv("GOOGLE_CLIENT_SECRET"),
                    scopes=[
                        "https://www.googleapis.com/auth/gmail.modify",
                        "https://www.googleapis.com/auth/gmail.compose",
                        "https://www.googleapis.com/auth/gmail.send",
                        "https://www.googleapis.com/auth/calendar",
                        "https://www.googleapis.com/auth/calendar.events",
                    ],
                )
                return credentials
            else:
                # Fallback to just access token if refresh token isn't available
                self.access_token = self.auth.refresh_oauth_token(provider="google")

        credentials = Credentials(
            token=self.access_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=getenv("GOOGLE_CLIENT_ID"),
            client_secret=getenv("GOOGLE_CLIENT_SECRET"),
            scopes=[
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/calendar.events",
            ],
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
            access_token = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=access_token,
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
                email_data = {
                    "id": msg["id"],
                    "sender": msg["payload"]["headers"][0]["value"],
                    "subject": msg["payload"]["headers"][1]["value"],
                    "body": msg["snippet"],
                    "attachments": [
                        part["filename"]
                        for part in msg["payload"]["parts"]
                        if part.get("filename")
                    ],
                    "received_time": datetime.fromtimestamp(
                        int(msg["internalDate"]) / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }
                emails.append(email_data)

            return emails
        except Exception as e:
            logging.info(f"Error retrieving emails: {str(e)}")
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
            access_token = self.authenticate()

            service = build("gmail", "v1", credentials=access_token)

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
            return "Failed to send email."

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
            access_token = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=access_token,
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
            logging.info(f"Error moving email: {str(e)}")
            return "Failed to move email."

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
            access_token = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=access_token,
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
            logging.info(f"Error creating draft email: {str(e)}")
            return "Failed to create draft email."

    async def delete_email(self, message_id):
        """
        Delete an email from the user's Gmail account

        Args:
        message_id (str): The ID of the email message

        Returns:
        str: The result of deleting the email
        """
        try:
            access_token = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=access_token,
                always_use_jwt_access=True,
            )
            service.users().messages().delete(userId="me", id=message_id).execute()
            return "Email deleted successfully."
        except Exception as e:
            logging.info(f"Error deleting email: {str(e)}")
            return "Failed to delete email."

    async def search_emails(self, query, max_emails=10):
        """
        Search emails in the user's Gmail account

        Args:
        query (str): The search query to filter emails
        max_emails (int): The maximum number of emails to retrieve

        Returns:
        List[Dict]: A list of email data
        """
        try:
            access_token = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=access_token,
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
                email_data = {
                    "id": msg["id"],
                    "sender": msg["payload"]["headers"][0]["value"],
                    "subject": msg["payload"]["headers"][1]["value"],
                    "body": msg["snippet"],
                    "attachments": [
                        part["filename"]
                        for part in msg["payload"]["parts"]
                        if part.get("filename")
                    ],
                    "received_time": datetime.fromtimestamp(
                        int(msg["internalDate"]) / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }
                emails.append(email_data)

            return emails
        except Exception as e:
            logging.info(f"Error searching emails: {str(e)}")
            return []

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
            access_token = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=access_token,
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
            logging.info(f"Error replying to email: {str(e)}")
            return "Failed to send reply."

    async def process_attachments(self, message_id):
        """
        Process attachments from an email in the user's Gmail account

        Args:
        message_id (str): The ID of the email message

        Returns:
        List[str]: A list of file paths to the saved attachments
        """
        try:
            access_token = self.authenticate()
            service = build(
                "gmail",
                "v1",
                credentials=access_token,
                always_use_jwt_access=True,
            )
            message = (
                service.users().messages().get(userId="me", id=message_id).execute()
            )
            saved_attachments = []

            for part in message["payload"]["parts"]:
                if part["filename"]:
                    attachment_id = part["body"]["attachmentId"]
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
            logging.info(f"Error processing attachments: {str(e)}")
            return []

    async def get_calendar_items(self, start_date=None, end_date=None, max_items=10):
        """
        Get calendar items from the user's Google Calendar

        Args:
        start_date (datetime): The start date to filter calendar items
        end_date (datetime): The end date to filter calendar items
        max_items (int): The maximum number of calendar items to retrieve

        Returns:
        List[Dict]: A list of calendar item data
        """
        try:
            access_token = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=access_token,
                always_use_jwt_access=True,
            )

            if start_date is None:
                start_date = datetime.utcnow().isoformat() + "Z"
            else:
                start_date = start_date.isoformat() + "Z"

            if end_date is None:
                end_date = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
            else:
                end_date = end_date.isoformat() + "Z"

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_date,
                    timeMax=end_date,
                    maxResults=max_items,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])

            calendar_items = []
            for event in events:
                item_data = {
                    "id": event["id"],
                    "subject": event["summary"],
                    "start_time": event["start"]["dateTime"],
                    "end_time": event["end"]["dateTime"],
                    "location": event.get("location", ""),
                    "organizer": event["organizer"]["email"],
                }
                calendar_items.append(item_data)

            return calendar_items
        except Exception as e:
            logging.info(f"Error retrieving calendar items: {str(e)}")
            return []

    async def get_available_timeslots(
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
            list: List of available time slots with start and end times
        """
        try:
            access_token = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=access_token,
                always_use_jwt_access=True,
            )

            end_date = start_date + timedelta(days=num_days)

            # Get all existing calendar events for the date range
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_date.isoformat() + "Z",
                    timeMax=end_date.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])

            available_slots = []
            current_date = start_date

            while current_date < end_date:
                # Convert work day times to datetime
                day_start = datetime.strptime(work_day_start, "%H:%M").time()
                day_end = datetime.strptime(work_day_end, "%H:%M").time()

                current_slot_start = datetime.combine(current_date.date(), day_start)
                day_end_time = datetime.combine(current_date.date(), day_end)

                # Filter events for current day
                day_events = [
                    event
                    for event in events
                    if event["start"].get("dateTime")
                    and datetime.fromisoformat(
                        event["start"]["dateTime"].replace("Z", "+00:00")
                    ).date()
                    == current_date.date()
                ]

                # Sort events by start time
                day_events.sort(key=lambda x: x["start"]["dateTime"])

                while (
                    current_slot_start + timedelta(minutes=duration_minutes)
                    <= day_end_time
                ):
                    slot_end = current_slot_start + timedelta(minutes=duration_minutes)
                    is_available = True

                    # Check if slot conflicts with any existing events
                    for event in day_events:
                        event_start = datetime.fromisoformat(
                            event["start"]["dateTime"].replace("Z", "+00:00")
                        )
                        event_end = datetime.fromisoformat(
                            event["end"]["dateTime"].replace("Z", "+00:00")
                        )

                        if current_slot_start <= event_end and slot_end >= event_start:
                            is_available = False
                            # Move current_slot to end of conflicting event plus buffer
                            current_slot_start = event_end + timedelta(
                                minutes=buffer_minutes
                            )
                            break

                    if is_available:
                        available_slots.append(
                            {
                                "start_time": current_slot_start.isoformat(),
                                "end_time": slot_end.isoformat(),
                            }
                        )
                        current_slot_start += timedelta(
                            minutes=duration_minutes + buffer_minutes
                        )

                current_date += timedelta(days=1)

            return available_slots

        except Exception as e:
            logging.error(f"Error finding available timeslots: {str(e)}")
            return []

    async def check_time_availability(self, start_time, end_time):
        """
        Checks if a specific time slot is available.

        Args:
            start_time (datetime): Start time of proposed event
            end_time (datetime): End time of proposed event

        Returns:
            tuple: (bool, dict) - (is_available, conflicting_event_if_any)
        """
        try:
            access_token = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=access_token,
                always_use_jwt_access=True,
            )

            # Get events for the time period
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_time.isoformat() + "Z",
                    timeMax=end_time.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])

            for event in events:
                if "dateTime" not in event["start"]:  # Skip all-day events
                    continue

                event_start = datetime.fromisoformat(
                    event["start"]["dateTime"].replace("Z", "+00:00")
                )
                event_end = datetime.fromisoformat(
                    event["end"]["dateTime"].replace("Z", "+00:00")
                )

                if start_time <= event_end and end_time >= event_start:
                    return False, {
                        "id": event["id"],
                        "summary": event["summary"],
                        "start_time": event["start"]["dateTime"],
                        "end_time": event["end"]["dateTime"],
                    }

            return True, None

        except Exception as e:
            logging.error(f"Error checking time availability: {str(e)}")
            raise

    async def add_calendar_item(
        self,
        subject,
        start_time,
        end_time,
        location=None,
        attendees=None,
        description=None,
        check_availability=True,
    ):
        """
        Add a calendar item with availability checking.

        Args:
            subject (str): The subject of the calendar item
            start_time (datetime): The start time of the calendar item
            end_time (datetime): The end time of the calendar item
            location (str): Optional location of the calendar item
            attendees (List[str]): Optional list of attendee email addresses
            description (str): Optional event description
            check_availability (bool): Whether to check for conflicts before creating

        Returns:
            dict: Response containing success status and any conflict information
        """
        try:
            if check_availability:
                is_available, conflict = await self.check_time_availability(
                    start_time, end_time
                )

                if not is_available:
                    return {
                        "success": False,
                        "message": f"The user isn't available at {start_time.strftime('%Y-%m-%d %H:%M')}. "
                        f"There is a conflict with '{conflict['summary']}'. "
                        f"Ask the user if they would like to schedule a different time or "
                        f"move their scheduled item '{conflict['summary']}' to a different time.",
                    }

            access_token = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=access_token,
                always_use_jwt_access=True,
            )

            event = {
                "summary": subject,
                "start": {
                    "dateTime": start_time.isoformat(),
                    "timeZone": self.timezone,
                },
                "end": {
                    "dateTime": end_time.isoformat(),
                    "timeZone": self.timezone,
                },
            }

            if location:
                event["location"] = location

            if description:
                event["description"] = description

            if attendees:
                if isinstance(attendees, str):
                    attendees = [attendees]
                event["attendees"] = [{"email": attendee} for attendee in attendees]

            created_event = (
                service.events().insert(calendarId="primary", body=event).execute()
            )

            return {
                "success": True,
                "message": "Calendar event created successfully.",
                "event_id": created_event["id"],
            }

        except Exception as e:
            logging.error(f"Error adding calendar item: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to add calendar item: {str(e)}",
            }

    async def modify_calendar_item(
        self,
        event_id,
        subject=None,
        start_time=None,
        end_time=None,
        location=None,
        attendees=None,
        description=None,
        check_availability=True,
    ):
        """
        Modifies an existing calendar event.

        Args:
            event_id (str): ID of the event to modify
            [all other parameters are optional and match add_calendar_item]
            check_availability (bool): Whether to check for conflicts before modifying time

        Returns:
            dict: Response containing success status and any conflict information
        """
        try:
            access_token = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=access_token,
                always_use_jwt_access=True,
            )

            # Get existing event
            event = (
                service.events().get(calendarId="primary", eventId=event_id).execute()
            )

            # If changing time, check availability
            if check_availability and start_time and end_time:
                is_available, conflict = await self.check_time_availability(
                    start_time, end_time
                )

                if (
                    not is_available and conflict["id"] != event_id
                ):  # Ignore conflict with self
                    return {
                        "success": False,
                        "message": f"The user isn't available at {start_time.strftime('%Y-%m-%d %H:%M')}. "
                        f"There is a conflict with '{conflict['summary']}'. "
                        f"Ask the user if they would like to choose a different time.",
                    }

            # Update event data with only provided fields
            if subject:
                event["summary"] = subject
            if start_time:
                event["start"] = {
                    "dateTime": start_time.isoformat(),
                    "timeZone": self.timezone,
                }
            if end_time:
                event["end"] = {
                    "dateTime": end_time.isoformat(),
                    "timeZone": self.timezone,
                }
            if location is not None:
                event["location"] = location
            if description is not None:
                event["description"] = description
            if attendees is not None:
                if isinstance(attendees, str):
                    attendees = [attendees]
                event["attendees"] = [{"email": attendee} for attendee in attendees]

            updated_event = (
                service.events()
                .update(calendarId="primary", eventId=event_id, body=event)
                .execute()
            )

            return {"success": True, "message": "Calendar event modified successfully."}

        except Exception as e:
            logging.error(f"Error modifying calendar event: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to modify calendar event: {str(e)}",
            }

    async def remove_calendar_item(self, item_id):
        """
        Remove a calendar item from the user's Google Calendar

        Args:
        item_id (str): The ID of the calendar item to remove

        Returns:
        str: The result of removing the calendar item
        """
        try:
            access_token = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=access_token,
                always_use_jwt_access=True,
            )
            service.events().delete(calendarId="primary", eventId=item_id).execute()
            return "Calendar item removed successfully."
        except Exception as e:
            logging.info(f"Error removing calendar item: {str(e)}")
            return "Failed to remove calendar item."

    async def get_keep_notes(self):
        """
        Get all notes from Google Keep

        Returns:
        List[Dict]: A list of note data
        """
        try:
            access_token = self.authenticate()
            service = build("keep", "v1", credentials=access_token)
            notes = service.notes().list().execute()
            return notes.get("items", [])
        except Exception as e:
            logging.info(f"Error retrieving notes: {str(e)}")
            return []

    async def create_keep_note(self, title, content):
        """
        Create a new note in Google Keep

        Args:
        title (str): The title of the note
        content (str): The content of the note

        Returns:
        str: The result of creating the note
        """
        try:
            access_token = self.authenticate()
            service = build("keep", "v1", credentials=access_token)
            note = {"title": title, "content": content}
            service.notes().create(body=note).execute()
            return "Note created successfully."
        except Exception as e:
            logging.info(f"Error creating note: {str(e)}")
            return "Failed to create note."

    async def delete_keep_note(self, note_id):
        """
        Delete a note from Google Keep

        Args:
        note_id (str): The ID of the note to delete

        Returns:
        str: The result of deleting the note
        """
        try:
            access_token = self.authenticate()
            service = build("keep", "v1", credentials=access_token)
            service.notes().delete(noteId=note_id).execute()
            return "Note deleted successfully."
        except Exception as e:
            logging.info(f"Error deleting note: {str(e)}")
            return "Failed to delete note."

    # Google Ads Marketing Functions
    async def get_google_ads_accounts(self) -> str:
        """
        Get all Google Ads accounts accessible to the user

        Returns:
            str: JSON formatted list of Google Ads accounts
        """
        try:
            # Use Google Ads API to get accounts
            url = f"https://googleads.googleapis.com/v15/customers:listAccessibleCustomers"
            response = self.session.get(url)

            if response.status_code == 200:
                accounts = response.json()
                return (
                    f"Found {len(accounts.get('resourceNames', []))} Google Ads accounts:\n\n"
                    + json.dumps(accounts, indent=2)
                )
            else:
                return f"Error retrieving Google Ads accounts: {response.text}"
        except Exception as e:
            logging.error(f"Error getting Google Ads accounts: {str(e)}")
            return f"Error retrieving Google Ads accounts: {str(e)}"

    async def create_google_ads_campaign(
        self,
        customer_id: str,
        name: str,
        budget_amount: int,
        advertising_channel_type: str = "SEARCH",
        status: str = "PAUSED",
    ) -> str:
        """
        Create a new Google Ads campaign

        Args:
            customer_id (str): The Google Ads customer ID
            name (str): Campaign name
            budget_amount (int): Daily budget in micros (e.g., 10000000 = $10)
            advertising_channel_type (str): Campaign type (SEARCH, DISPLAY, SHOPPING, VIDEO)
            status (str): Campaign status (ENABLED, PAUSED, REMOVED)

        Returns:
            str: Campaign creation result
        """
        try:
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/campaigns:mutate"

            campaign_data = {
                "operations": [
                    {
                        "create": {
                            "name": name,
                            "status": status,
                            "advertisingChannelType": advertising_channel_type,
                            "campaignBudget": f"customers/{customer_id}/campaignBudgets/temp_budget_id",
                            "biddingStrategy": "MAXIMIZE_CONVERSIONS",
                        }
                    }
                ]
            }

            response = self.session.post(url, json=campaign_data)

            if response.status_code == 200:
                result = response.json()
                return f"Successfully created campaign '{name}'"
            else:
                return f"Campaign creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating Google Ads campaign: {str(e)}")
            return f"Error creating campaign: {str(e)}"

    async def get_google_ads_campaigns(self, customer_id: str) -> str:
        """
        Get campaigns from a Google Ads account

        Args:
            customer_id (str): The Google Ads customer ID

        Returns:
            str: JSON formatted list of campaigns
        """
        try:
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/googleAds:search"

            query = {
                "query": """
                    SELECT campaign.id, campaign.name, campaign.status, 
                           campaign.advertising_channel_type, campaign_budget.amount_micros
                    FROM campaign 
                    ORDER BY campaign.id
                """
            }

            response = self.session.post(url, json=query)

            if response.status_code == 200:
                campaigns = response.json()
                return f"Google Ads campaigns:\n\n" + json.dumps(campaigns, indent=2)
            else:
                return f"Error retrieving campaigns: {response.text}"

        except Exception as e:
            logging.error(f"Error getting Google Ads campaigns: {str(e)}")
            return f"Error retrieving campaigns: {str(e)}"

    async def update_google_ads_campaign(
        self, customer_id: str, campaign_id: str, **updates
    ) -> str:
        """
        Update a Google Ads campaign

        Args:
            customer_id (str): The Google Ads customer ID
            campaign_id (str): The campaign ID to update
            **updates: Campaign fields to update

        Returns:
            str: Update result
        """
        try:
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/campaigns:mutate"

            operation = {
                "operations": [
                    {"update": updates, "updateMask": ",".join(updates.keys())}
                ]
            }

            response = self.session.post(url, json=operation)

            if response.status_code == 200:
                return f"Successfully updated campaign {campaign_id}"
            else:
                return f"Campaign update failed: {response.text}"

        except Exception as e:
            logging.error(f"Error updating campaign: {str(e)}")
            return f"Error updating campaign: {str(e)}"

    async def create_google_ads_ad_group(
        self,
        customer_id: str,
        campaign_id: str,
        name: str,
        cpc_bid_micros: int = 1000000,
    ) -> str:
        """
        Create an ad group within a Google Ads campaign

        Args:
            customer_id (str): The Google Ads customer ID
            campaign_id (str): The parent campaign ID
            name (str): Ad group name
            cpc_bid_micros (int): CPC bid in micros

        Returns:
            str: Ad group creation result
        """
        try:
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/adGroups:mutate"

            ad_group_data = {
                "operations": [
                    {
                        "create": {
                            "campaign": f"customers/{customer_id}/campaigns/{campaign_id}",
                            "name": name,
                            "status": "ENABLED",
                            "type": "SEARCH_STANDARD",
                            "cpcBidMicros": cpc_bid_micros,
                        }
                    }
                ]
            }

            response = self.session.post(url, json=ad_group_data)

            if response.status_code == 200:
                return f"Successfully created ad group '{name}'"
            else:
                return f"Ad group creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating ad group: {str(e)}")
            return f"Error creating ad group: {str(e)}"

    async def get_google_ads_ad_groups(self, customer_id: str, campaign_id: str) -> str:
        """
        Get ad groups from a Google Ads campaign

        Args:
            customer_id (str): The Google Ads customer ID
            campaign_id (str): The campaign ID

        Returns:
            str: JSON formatted list of ad groups
        """
        try:
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/googleAds:search"

            query = {
                "query": f"""
                    SELECT ad_group.id, ad_group.name, ad_group.status, 
                           ad_group.cpc_bid_micros
                    FROM ad_group 
                    WHERE campaign.id = {campaign_id}
                """
            }

            response = self.session.post(url, json=query)

            if response.status_code == 200:
                ad_groups = response.json()
                return f"Ad groups:\n\n" + json.dumps(ad_groups, indent=2)
            else:
                return f"Error retrieving ad groups: {response.text}"

        except Exception as e:
            logging.error(f"Error getting ad groups: {str(e)}")
            return f"Error retrieving ad groups: {str(e)}"

    async def create_google_ads_ad(
        self,
        customer_id: str,
        ad_group_id: str,
        headlines: List[str],
        descriptions: List[str],
        final_urls: List[str],
    ) -> str:
        """
        Create a responsive search ad

        Args:
            customer_id (str): The Google Ads customer ID
            ad_group_id (str): The parent ad group ID
            headlines (List[str]): List of headline texts (max 30 chars each)
            descriptions (List[str]): List of description texts (max 90 chars each)
            final_urls (List[str]): Landing page URLs

        Returns:
            str: Ad creation result
        """
        try:
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/ads:mutate"

            ad_data = {
                "operations": [
                    {
                        "create": {
                            "adGroup": f"customers/{customer_id}/adGroups/{ad_group_id}",
                            "status": "ENABLED",
                            "responsiveSearchAd": {
                                "headlines": [{"text": h} for h in headlines],
                                "descriptions": [{"text": d} for d in descriptions],
                            },
                            "finalUrls": final_urls,
                        }
                    }
                ]
            }

            response = self.session.post(url, json=ad_data)

            if response.status_code == 200:
                return "Successfully created responsive search ad"
            else:
                return f"Ad creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating ad: {str(e)}")
            return f"Error creating ad: {str(e)}"

    async def get_google_ads_performance(
        self, customer_id: str, date_range: str = "LAST_7_DAYS"
    ) -> str:
        """
        Get performance metrics for Google Ads campaigns

        Args:
            customer_id (str): The Google Ads customer ID
            date_range (str): Date range for metrics

        Returns:
            str: JSON formatted performance metrics
        """
        try:
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/googleAds:search"

            query = {
                "query": f"""
                    SELECT campaign.name, metrics.impressions, metrics.clicks, 
                           metrics.cost_micros, metrics.conversions, metrics.ctr, 
                           metrics.average_cpc
                    FROM campaign 
                    WHERE segments.date DURING {date_range}
                """
            }

            response = self.session.post(url, json=query)

            if response.status_code == 200:
                performance = response.json()
                return f"Google Ads performance ({date_range}):\n\n" + json.dumps(
                    performance, indent=2
                )
            else:
                return f"Error retrieving performance: {response.text}"

        except Exception as e:
            logging.error(f"Error getting performance: {str(e)}")
            return f"Error retrieving performance: {str(e)}"

    async def manage_google_ads_keywords(
        self,
        customer_id: str,
        ad_group_id: str,
        keywords: List[Dict],
        action: str = "ADD",
    ) -> str:
        """
        Manage keywords for an ad group

        Args:
            customer_id (str): The Google Ads customer ID
            ad_group_id (str): The ad group ID
            keywords (List[Dict]): List of keyword dictionaries with 'text' and 'match_type'
            action (str): ADD, REMOVE, or UPDATE

        Returns:
            str: Keyword management result
        """
        try:
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/keywordCriteria:mutate"

            operations = []
            for keyword in keywords:
                if action == "ADD":
                    operations.append(
                        {
                            "create": {
                                "adGroup": f"customers/{customer_id}/adGroups/{ad_group_id}",
                                "keyword": {
                                    "text": keyword["text"],
                                    "matchType": keyword.get("match_type", "BROAD"),
                                },
                                "status": "ENABLED",
                            }
                        }
                    )
                elif action == "REMOVE":
                    operations.append(
                        {
                            "remove": f"customers/{customer_id}/keywordCriteria/{keyword['id']}"
                        }
                    )

            response = self.session.post(url, json={"operations": operations})

            if response.status_code == 200:
                return f"Successfully {action.lower()}ed {len(keywords)} keywords"
            else:
                return f"Keyword operation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error managing keywords: {str(e)}")
            return f"Error managing keywords: {str(e)}"

    async def create_google_ads_audience(
        self, customer_id: str, name: str, description: str, members: List[Dict]
    ) -> str:
        """
        Create a custom audience for Google Ads

        Args:
            customer_id (str): The Google Ads customer ID
            name (str): Audience name
            description (str): Audience description
            members (List[Dict]): List of audience members

        Returns:
            str: Audience creation result
        """
        try:
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/userLists:mutate"

            audience_data = {
                "operations": [
                    {
                        "create": {
                            "name": name,
                            "description": description,
                            "membershipStatus": "OPEN",
                            "membershipLifeSpan": 540,  # days
                            "crmBasedUserList": {
                                "uploadKeyType": "CONTACT_INFO",
                                "dataSourceType": "FIRST_PARTY",
                            },
                        }
                    }
                ]
            }

            response = self.session.post(url, json=audience_data)

            if response.status_code == 200:
                return f"Successfully created audience '{name}'"
            else:
                return f"Audience creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating audience: {str(e)}")
            return f"Error creating audience: {str(e)}"

    # Google Analytics Functions
    async def get_analytics_properties(self) -> str:
        """
        Get all Google Analytics 4 properties accessible to the user

        Returns:
            str: JSON formatted list of GA4 properties
        """
        try:
            url = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                properties = []
                for account in data.get("accountSummaries", []):
                    for property_summary in account.get("propertySummaries", []):
                        properties.append(
                            {
                                "property": property_summary.get("property"),
                                "displayName": property_summary.get("displayName"),
                                "propertyType": property_summary.get("propertyType"),
                                "parent": property_summary.get("parent"),
                            }
                        )

                return f"Found {len(properties)} GA4 properties:\n\n" + json.dumps(
                    properties, indent=2
                )
            else:
                return f"Error retrieving GA4 properties: {response.text}"
        except Exception as e:
            logging.error(f"Error getting GA4 properties: {str(e)}")
            return f"Error retrieving GA4 properties: {str(e)}"

    async def get_analytics_reports(
        self,
        property_id: str,
        start_date: str = "7daysAgo",
        end_date: str = "today",
        metrics: Optional[List[str]] = None,
        dimensions: Optional[List[str]] = None,
    ) -> str:
        """
        Get reports from Google Analytics 4

        Args:
            property_id (str): The GA4 property ID (e.g., "properties/123456")
            start_date (str): Start date (e.g., "2024-01-01" or "7daysAgo")
            end_date (str): End date (e.g., "2024-01-31" or "today")
            metrics (List[str]): List of metrics to retrieve
            dimensions (List[str]): List of dimensions to retrieve

        Returns:
            str: JSON formatted analytics report
        """
        try:
            url = f"https://analyticsdata.googleapis.com/v1beta/{property_id}:runReport"

            # Default metrics and dimensions if not provided
            if not metrics:
                metrics = [
                    "activeUsers",
                    "sessions",
                    "bounceRate",
                    "averageSessionDuration",
                    "screenPageViews",
                ]

            if not dimensions:
                dimensions = ["date", "country", "deviceCategory"]

            report_request = {
                "dateRanges": [{"startDate": start_date, "endDate": end_date}],
                "metrics": [{"name": metric} for metric in metrics],
                "dimensions": [{"name": dimension} for dimension in dimensions],
            }

            response = self.session.post(url, json=report_request)

            if response.status_code == 200:
                report = response.json()
                return f"GA4 Report ({start_date} to {end_date}):\n\n" + json.dumps(
                    report, indent=2
                )
            else:
                return f"Error retrieving GA4 report: {response.text}"

        except Exception as e:
            logging.error(f"Error getting GA4 reports: {str(e)}")
            return f"Error retrieving GA4 reports: {str(e)}"

    async def get_analytics_realtime(self, property_id: str) -> str:
        """
        Get real-time data from Google Analytics 4

        Args:
            property_id (str): The GA4 property ID

        Returns:
            str: JSON formatted real-time data
        """
        try:
            url = f"https://analyticsdata.googleapis.com/v1beta/{property_id}:runRealtimeReport"

            realtime_request = {
                "metrics": [
                    {"name": "activeUsers"},
                    {"name": "screenPageViews"},
                    {"name": "eventCount"},
                ],
                "dimensions": [
                    {"name": "country"},
                    {"name": "deviceCategory"},
                    {"name": "unifiedPageScreen"},
                ],
            }

            response = self.session.post(url, json=realtime_request)

            if response.status_code == 200:
                realtime_data = response.json()
                return f"GA4 Real-time Data:\n\n" + json.dumps(realtime_data, indent=2)
            else:
                return f"Error retrieving real-time data: {response.text}"

        except Exception as e:
            logging.error(f"Error getting real-time data: {str(e)}")
            return f"Error retrieving real-time data: {str(e)}"

    async def get_analytics_audiences(self, property_id: str) -> str:
        """
        Get audiences from Google Analytics 4

        Args:
            property_id (str): The GA4 property ID

        Returns:
            str: JSON formatted list of audiences
        """
        try:
            url = (
                f"https://analyticsadmin.googleapis.com/v1beta/{property_id}/audiences"
            )
            response = self.session.get(url)

            if response.status_code == 200:
                audiences = response.json()
                return f"GA4 Audiences:\n\n" + json.dumps(audiences, indent=2)
            else:
                return f"Error retrieving audiences: {response.text}"

        except Exception as e:
            logging.error(f"Error getting audiences: {str(e)}")
            return f"Error retrieving audiences: {str(e)}"

    async def create_analytics_dimension(
        self,
        property_id: str,
        display_name: str,
        scope: str = "EVENT",
        description: str = "",
    ) -> str:
        """
        Create a custom dimension in Google Analytics 4

        Args:
            property_id (str): The GA4 property ID
            display_name (str): Display name for the dimension
            scope (str): Scope of the dimension (EVENT or USER)
            description (str): Description of the dimension

        Returns:
            str: Dimension creation result
        """
        try:
            url = f"https://analyticsadmin.googleapis.com/v1beta/{property_id}/customDimensions"

            dimension_data = {
                "displayName": display_name,
                "scope": scope,
                "description": description,
                "disallowAdsPersonalization": False,
            }

            response = self.session.post(url, json=dimension_data)

            if response.status_code == 200:
                dimension = response.json()
                return f"Successfully created custom dimension '{display_name}'"
            else:
                return f"Dimension creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating dimension: {str(e)}")
            return f"Error creating dimension: {str(e)}"

    # Google Tag Manager Functions
    async def get_gtm_containers(self) -> str:
        """
        Get all Google Tag Manager containers accessible to the user

        Returns:
            str: JSON formatted list of GTM containers
        """
        try:
            url = "https://www.googleapis.com/tagmanager/v2/accounts"
            response = self.session.get(url)

            if response.status_code == 200:
                accounts = response.json()
                containers = []

                for account in accounts.get("account", []):
                    account_id = account.get("accountId")
                    container_url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers"
                    container_response = self.session.get(container_url)

                    if container_response.status_code == 200:
                        container_data = container_response.json()
                        for container in container_data.get("container", []):
                            containers.append(
                                {
                                    "accountId": account_id,
                                    "containerId": container.get("containerId"),
                                    "name": container.get("name"),
                                    "publicId": container.get("publicId"),
                                    "domainName": container.get("domainName", []),
                                    "usageContext": container.get("usageContext", []),
                                }
                            )

                return f"Found {len(containers)} GTM containers:\n\n" + json.dumps(
                    containers, indent=2
                )
            else:
                return f"Error retrieving GTM containers: {response.text}"

        except Exception as e:
            logging.error(f"Error getting GTM containers: {str(e)}")
            return f"Error retrieving GTM containers: {str(e)}"

    async def create_gtm_tag(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        name: str,
        type: str,
        parameter: List[Dict],
        firing_trigger_id: List[str],
    ) -> str:
        """
        Create a new tag in Google Tag Manager

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            name (str): Tag name
            type (str): Tag type (e.g., "ua", "ga4", "html")
            parameter (List[Dict]): Tag parameters
            firing_trigger_id (List[str]): List of trigger IDs

        Returns:
            str: Tag creation result
        """
        try:
            url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}/tags"

            tag_data = {
                "name": name,
                "type": type,
                "parameter": parameter,
                "firingTriggerId": firing_trigger_id,
            }

            response = self.session.post(url, json=tag_data)

            if response.status_code == 200:
                tag = response.json()
                return f"Successfully created tag '{name}' with ID: {tag.get('tagId')}"
            else:
                return f"Tag creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating GTM tag: {str(e)}")
            return f"Error creating tag: {str(e)}"

    async def update_gtm_tag(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        tag_id: str,
        **updates,
    ) -> str:
        """
        Update an existing tag in Google Tag Manager

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            tag_id (str): Tag ID to update
            **updates: Tag fields to update

        Returns:
            str: Tag update result
        """
        try:
            url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}/tags/{tag_id}"

            response = self.session.put(url, json=updates)

            if response.status_code == 200:
                return f"Successfully updated tag {tag_id}"
            else:
                return f"Tag update failed: {response.text}"

        except Exception as e:
            logging.error(f"Error updating GTM tag: {str(e)}")
            return f"Error updating tag: {str(e)}"

    async def create_gtm_trigger(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        name: str,
        type: str,
        custom_event_filter: Optional[List[Dict]] = None,
    ) -> str:
        """
        Create a new trigger in Google Tag Manager

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            name (str): Trigger name
            type (str): Trigger type (e.g., "pageview", "click", "customEvent")
            custom_event_filter (List[Dict]): Optional filters for the trigger

        Returns:
            str: Trigger creation result
        """
        try:
            url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}/triggers"

            trigger_data = {
                "name": name,
                "type": type,
            }

            if custom_event_filter:
                trigger_data["customEventFilter"] = custom_event_filter

            response = self.session.post(url, json=trigger_data)

            if response.status_code == 200:
                trigger = response.json()
                return f"Successfully created trigger '{name}' with ID: {trigger.get('triggerId')}"
            else:
                return f"Trigger creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating GTM trigger: {str(e)}")
            return f"Error creating trigger: {str(e)}"

    async def create_gtm_variable(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        name: str,
        type: str,
        parameter: Optional[List[Dict]] = None,
    ) -> str:
        """
        Create a new variable in Google Tag Manager

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            name (str): Variable name
            type (str): Variable type (e.g., "jsm", "v", "c")
            parameter (List[Dict]): Variable parameters

        Returns:
            str: Variable creation result
        """
        try:
            url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}/variables"

            variable_data = {
                "name": name,
                "type": type,
            }

            if parameter:
                variable_data["parameter"] = parameter

            response = self.session.post(url, json=variable_data)

            if response.status_code == 200:
                variable = response.json()
                return f"Successfully created variable '{name}' with ID: {variable.get('variableId')}"
            else:
                return f"Variable creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating GTM variable: {str(e)}")
            return f"Error creating variable: {str(e)}"

    async def publish_gtm_container(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        version_name: str,
        notes: str = "",
    ) -> str:
        """
        Publish a Google Tag Manager container version

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            version_name (str): Version name for the publication
            notes (str): Optional notes for the version

        Returns:
            str: Publication result
        """
        try:
            # First create a version
            version_url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}:create_version"

            version_data = {
                "name": version_name,
                "notes": notes,
            }

            version_response = self.session.post(version_url, json=version_data)

            if version_response.status_code == 200:
                version = version_response.json()
                version_id = version.get("containerVersion", {}).get(
                    "containerVersionId"
                )

                # Now publish the version
                publish_url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/versions/{version_id}:publish"

                publish_response = self.session.post(publish_url)

                if publish_response.status_code == 200:
                    return f"Successfully published container version '{version_name}'"
                else:
                    return f"Publication failed: {publish_response.text}"
            else:
                return f"Version creation failed: {version_response.text}"

        except Exception as e:
            logging.error(f"Error publishing GTM container: {str(e)}")
            return f"Error publishing container: {str(e)}"
