import os
import logging
import requests
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
import base64


class microsoft365(Extensions):
    """
    The Microsoft 365 extension provides comprehensive integration with Microsoft Office 365 services.
    This extension allows AI agents to:
    - Manage emails (read, send, move, search)
    - Handle calendar events
    - Manage todo tasks
    - Process email attachments

    The extension requires the user to be authenticated with Microsoft 365 through OAuth.
    AI agents should use this when they need to interact with a user's Microsoft 365 account
    for tasks like scheduling meetings, sending emails, or managing tasks.
    """

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("MICROSOFT_ACCESS_TOKEN", None)
        microsoft_client_id = getenv("MICROSOFT_CLIENT_ID")
        microsoft_client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.timezone = getenv("TZ")
        self.auth = None
        if microsoft_client_id and microsoft_client_secret:
            self.commands = {
                "Microsoft - Get Emails": self.get_emails,
                "Microsoft - Send Email": self.send_email,
                "Microsoft - Create Draft Email": self.create_draft_email,
                "Microsoft - Delete Email": self.delete_email,
                "Microsoft - Search Emails": self.search_emails,
                "Microsoft - Reply to Email": self.reply_to_email,
                "Microsoft - Process Attachments": self.process_attachments,
                "Microsoft - Get Calendar Items": self.get_calendar_items,
                "Microsoft - Get Available Timeslots": self.get_available_timeslots,
                "Microsoft - Add Calendar Item": self.add_calendar_item,
                "Microsoft - Modify Calendar Item": self.modify_calendar_item,
                "Microsoft - Remove Calendar Item": self.remove_calendar_item,
                "Microsoft - Get Todo Tasks": self.get_todo_tasks,
                "Microsoft - Create Todo Task": self.create_todo_task,
                "Microsoft - Update Todo Task": self.update_todo_task,
                "Microsoft - Delete Todo Task": self.delete_todo_task,
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

    def verify_user(self):
        """
        Verifies that the current access token corresponds to a valid user.
        If the /me endpoint fails, raises an exception indicating the user is not found.
        """
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="microsoft")

        logging.info(f"Verifying user with token: {self.access_token}")
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        logging.info(f"User verification response: {response.text}")
        if response.status_code != 200:
            raise Exception(
                f"User not found or invalid token. Status: {response.status_code}, "
                f"Response: {response.text}. Ensure the token is a user-delegated token "
                "with the correct scopes (e.g., Calendars.ReadWrite), and the user is properly signed in."
            )

    async def get_emails(self, folder_name="Inbox", max_emails=10, page_size=10):
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

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # First get the folder id
            folder_response = requests.get(
                f"https://graph.microsoft.com/v1.0/me/mailFolders?$filter=displayName eq '{folder_name}'",
                headers=headers,
            )

            if folder_response.status_code != 200:
                raise Exception(f"Failed to find folder: {folder_response.text}")

            folder_id = folder_response.json()["value"][0]["id"]

            # Then get the messages
            emails = []
            url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder_id}/messages?$top={page_size}&$orderby=receivedDateTime desc"

            while len(emails) < max_emails:
                response = requests.get(url, headers=headers)
                if response.status_code != 200:
                    raise Exception(f"Failed to fetch emails: {response.text}")

                data = response.json()
                for message in data["value"]:
                    emails.append(
                        {
                            "id": message["id"],
                            "subject": message["subject"],
                            "sender": message["from"]["emailAddress"]["address"],
                            "received_time": message["receivedDateTime"],
                            "body": message["body"]["content"],
                            "has_attachments": message["hasAttachments"],
                        }
                    )
                    if len(emails) >= max_emails:
                        break

                if "@odata.nextLink" in data and len(emails) < max_emails:
                    url = data["@odata.nextLink"]
                else:
                    break

            return emails

        except Exception as e:
            logging.error(f"Error retrieving emails: {str(e)}")
            return []

    async def send_email(
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

    async def create_draft_email(
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
                        with open(attachment_path, "rb") as file:
                            content = file.read()
                            draft_data["attachments"].append(
                                {
                                    "@odata.type": "#microsoft.graph.fileAttachment",
                                    "name": os.path.basename(attachment_path),
                                    "contentBytes": base64.b64encode(content).decode(),
                                }
                            )

            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=draft_data,
            )

            if response.status_code == 201:
                return "Draft email created successfully."
            else:
                raise Exception(f"Failed to create draft: {response.text}")

        except Exception as e:
            logging.error(f"Error creating draft email: {str(e)}")
            return f"Failed to create draft email: {str(e)}"

    async def search_emails(
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

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            search_params = f"$search='{query}'"
            if date_range:
                start_date, end_date = date_range
                search_params += f" AND receivedDateTime ge {start_date.isoformat()}Z AND receivedDateTime le {end_date.isoformat()}Z"

            response = requests.get(
                f"https://graph.microsoft.com/v1.0/me/messages?{search_params}&$top={max_emails}",
                headers=headers,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to search emails: {response.text}")

            emails = []
            for message in response.json()["value"]:
                emails.append(
                    {
                        "id": message["id"],
                        "subject": message["subject"],
                        "sender": message["from"]["emailAddress"]["address"],
                        "received_time": message["receivedDateTime"],
                        "body": message["body"]["content"],
                        "has_attachments": message["hasAttachments"],
                    }
                )

            return emails

        except Exception as e:
            logging.error(f"Error searching emails: {str(e)}")
            return []

    async def reply_to_email(self, message_id, body, attachments=None):
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

            reply_data = {"message": {"body": {"contentType": "HTML", "content": body}}}

            if attachments:
                reply_data["message"]["attachments"] = []
                for attachment_path in attachments:
                    if os.path.exists(attachment_path):
                        with open(attachment_path, "rb") as file:
                            content = file.read()
                            reply_data["message"]["attachments"].append(
                                {
                                    "@odata.type": "#microsoft.graph.fileAttachment",
                                    "name": os.path.basename(attachment_path),
                                    "contentBytes": base64.b64encode(content).decode(),
                                }
                            )

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply",
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
            logging.error(f"Error sending reply: {str(e)}")
            return f"Failed to send reply: {str(e)}"

    async def delete_email(self, message_id):
        """
        Deletes a specific email.

        Args:
            message_id (str): ID of the email to delete

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

    async def process_attachments(self, message_id):
        """
        Downloads attachments from a specific email.

        Args:
            message_id (str): ID of the email containing attachments

        Returns:
            list: List of paths to saved attachment files
        """
        try:

            self.verify_user()

            headers = {"Authorization": f"Bearer {self.access_token}"}

            # Get attachments metadata
            attachments_response = requests.get(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments",
                headers=headers,
            )

            if attachments_response.status_code != 200:
                raise Exception(
                    f"Failed to get attachments: {attachments_response.text}"
                )

            saved_files = []
            for attachment in attachments_response.json()["value"]:
                if attachment["@odata.type"] == "#microsoft.graph.fileAttachment":
                    file_path = os.path.join(self.attachments_dir, attachment["name"])
                    with open(file_path, "wb") as f:
                        f.write(base64.b64decode(attachment["contentBytes"]))
                    saved_files.append(file_path)
            return saved_files

        except Exception as e:
            logging.error(f"Error processing attachments: {str(e)}")
            return []

    async def get_calendar_items(self, start_date=None, end_date=None, max_items=10):
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

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if not start_date:
                start_date = datetime.now()
            if not end_date:
                end_date = start_date + timedelta(days=7)

            url = (
                f"https://graph.microsoft.com/v1.0/me/calendar/calendarView?"
                f"startDateTime={start_date.isoformat()}Z&"
                f"endDateTime={end_date.isoformat()}Z&"
                f"$top={max_items}&$orderby=start/dateTime"
            )

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                raise Exception(f"Failed to fetch calendar items: {response.text}")

            events = []
            for event in response.json()["value"]:
                events.append(
                    {
                        "id": event["id"],
                        "subject": event["subject"],
                        "start_time": event["start"]["dateTime"],
                        "end_time": event["end"]["dateTime"],
                        "location": event.get("location", {}).get("displayName", ""),
                        "is_online_meeting": event.get("isOnlineMeeting", False),
                        "meeting_url": event.get("onlineMeeting", {}).get(
                            "joinUrl", ""
                        ),
                        "organizer": event["organizer"]["emailAddress"]["address"],
                        "is_all_day": event.get("isAllDay", False),
                        "sensitivity": event.get("sensitivity", "normal"),
                        "status": event["showAs"],
                    }
                )

            return events

        except Exception as e:
            logging.error(f"Error retrieving calendar items: {str(e)}")
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
            list: List of available time slots as datetime objects
        """
        try:
            self.verify_user()

            end_date = start_date + timedelta(days=num_days)

            # Get all existing calendar events for the date range
            existing_events = await self.get_calendar_items(
                start_date=start_date,
                end_date=end_date,
                max_items=100,  # Increased to handle busy calendars
            )

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
                    for event in existing_events
                    if datetime.fromisoformat(
                        event["start_time"].replace("Z", "+")
                    ).date()
                    == current_date.date()
                ]

                # Sort events by start time
                day_events.sort(
                    key=lambda x: datetime.fromisoformat(
                        x["start_time"].replace("Z", "+")
                    )
                )

                while (
                    current_slot_start + timedelta(minutes=duration_minutes)
                    <= day_end_time
                ):
                    slot_end = current_slot_start + timedelta(minutes=duration_minutes)
                    is_available = True

                    # Check if slot conflicts with any existing events
                    for event in day_events:
                        event_start = datetime.fromisoformat(
                            event["start_time"].replace("Z", "+")
                        )
                        event_end = datetime.fromisoformat(
                            event["end_time"].replace("Z", "+")
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
            self.verify_user()

            # Get events for the day
            existing_events = await self.get_calendar_items(
                start_date=start_time, end_date=end_time, max_items=50
            )

            for event in existing_events:
                event_start = datetime.fromisoformat(
                    event["start_time"].replace("Z", "+")
                )
                event_end = datetime.fromisoformat(event["end_time"].replace("Z", "+"))

                if start_time <= event_end and end_time >= event_start:
                    return False, event

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
        body=None,
        is_online_meeting=False,
        reminder_minutes_before=15,
    ):
        """
        Creates a new calendar event.

        Args:
            subject (str): Event title/subject
            start_time (datetime): Event start time
            end_time (datetime): Event end time
            location (str): Optional physical location
            attendees (list): Optional list of attendee email addresses
            body (str): Optional event description
            is_online_meeting (bool): Whether to create as Teams meeting
            reminder_minutes_before (int): Minutes before event to send reminder

        Returns:
            str: Success or failure message
        """
        try:
            is_available, conflict = await self.check_time_availability(
                start_time, end_time
            )

            if not is_available:
                return {
                    "success": False,
                    "message": f"The user isn't available at {start_time.strftime('%Y-%m-%d %H:%M')}. "
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
                "start": {"dateTime": start_time, "timeZone": self.timezone},
                "end": {"dateTime": end_time, "timeZone": self.timezone},
                "isOnlineMeeting": is_online_meeting,
                "reminderMinutesBeforeStart": reminder_minutes_before,
            }

            if location:
                event_data["location"] = {"displayName": location}

            if body:
                event_data["body"] = {"contentType": "HTML", "content": body}

            if attendees:
                if isinstance(attendees, str):
                    attendees = [attendees]
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

    async def modify_calendar_item(
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

            # If changing time, check availability
            if check_availability and start_time and end_time:
                is_available, conflict = await self.check_time_availability(
                    start_time, end_time
                )

                if not is_available:
                    return {
                        "success": False,
                        "message": f"The user isn't available at {start_time.strftime('%Y-%m-%d %H:%M')}. "
                        f"There is a conflict with '{conflict['subject']}'. "
                        f"Ask the user if they would like to choose a different time.",
                    }

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Build update data with only provided fields
            update_data = {}

            if subject:
                update_data["subject"] = subject
            if start_time:
                update_data["start"] = {
                    "dateTime": start_time,
                    "timeZone": self.timezone,
                }
            if end_time:
                update_data["end"] = {"dateTime": end_time, "timeZone": self.timezone}
            if location is not None:
                update_data["location"] = {"displayName": location}
            if body is not None:
                update_data["body"] = {"contentType": "HTML", "content": body}
            if is_online_meeting is not None:
                update_data["isOnlineMeeting"] = is_online_meeting
            if reminder_minutes_before is not None:
                update_data["reminderMinutesBeforeStart"] = reminder_minutes_before
            if attendees is not None:
                if isinstance(attendees, str):
                    attendees = [attendees]
                update_data["attendees"] = [
                    {"emailAddress": {"address": email}, "type": "required"}
                    for email in attendees
                ]

            response = requests.patch(
                f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                headers=headers,
                json=update_data,
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "message": "Calendar event modified successfully.",
                }
            else:
                raise Exception(
                    f"Failed to modify event: {response.status_code}: {response.text}"
                )

        except Exception as e:
            logging.error(f"Error modifying calendar event: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to modify calendar event: {str(e)}",
            }

    async def remove_calendar_item(self, event_id):
        """
        Deletes a calendar event.

        Args:
            event_id (str): ID of the event to delete

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()
            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

            if response.status_code == 204:
                return "Calendar event deleted successfully."
            else:
                raise Exception(f"Failed to delete event: {response.text}")

        except Exception as e:
            logging.error(f"Error deleting calendar event: {str(e)}")
            return f"Failed to delete calendar event: {str(e)}"

    async def get_todo_tasks(self, list_name="Tasks", max_tasks=50):
        """
        Retrieves tasks from a specified todo list.

        Args:
            list_name (str): Name of the todo list to fetch from
            max_tasks (int): Maximum number of tasks to retrieve

        Returns:
            list: List of task dictionaries
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get lists
            lists_response = requests.get(
                "https://graph.microsoft.com/v1.0/me/todo/lists", headers=headers
            )

            if lists_response.status_code != 200:
                raise Exception(f"Failed to fetch todo lists: {lists_response.text}")

            list_id = None
            for todo_list in lists_response.json()["value"]:
                if todo_list["displayName"].lower() == list_name.lower():
                    list_id = todo_list["id"]
                    break

            if not list_id:
                raise Exception(f"Todo list '{list_name}' not found")

            # Get tasks
            tasks_response = requests.get(
                f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks?$top={max_tasks}",
                headers=headers,
            )

            if tasks_response.status_code != 200:
                raise Exception(f"Failed to fetch tasks: {tasks_response.text}")

            tasks = []
            for task in tasks_response.json()["value"]:
                tasks.append(
                    {
                        "id": task["id"],
                        "title": task["title"],
                        "body": task.get("body", {}).get("content", ""),
                        "due_date": task.get("dueDateTime", {}).get("dateTime", ""),
                        "completed": task["status"] == "completed",
                        "importance": task["importance"],
                        "created_date": task["createdDateTime"],
                        "last_modified": task["lastModifiedDateTime"],
                    }
                )

            return tasks

        except Exception as e:
            logging.error(f"Error retrieving todo tasks: {str(e)}")
            return []

    async def create_todo_task(
        self,
        title,
        list_name="Tasks",
        body=None,
        due_date=None,
        importance="normal",
        reminder=None,
    ):
        """
        Creates a new task in a todo list.

        Args:
            title (str): Task title
            list_name (str): Name of the todo list to add task to
            body (str): Optional task description
            due_date (datetime): Optional due date
            importance (str): Task importance ("low", "normal", "high")
            reminder (datetime): Optional reminder date/time

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get list ID
            lists_response = requests.get(
                "https://graph.microsoft.com/v1.0/me/todo/lists", headers=headers
            )

            list_id = None
            for todo_list in lists_response.json()["value"]:
                if todo_list["displayName"].lower() == list_name.lower():
                    list_id = todo_list["id"]
                    break

            if not list_id:
                raise Exception(f"Todo list '{list_name}' not found")

            task_data = {"title": title, "importance": importance}

            if body:
                task_data["body"] = {"content": body, "contentType": "text"}

            if due_date:
                task_data["dueDateTime"] = {
                    "dateTime": due_date,
                    "timeZone": self.timezone,
                }

            if reminder:
                task_data["reminderDateTime"] = {
                    "dateTime": reminder,
                    "timeZone": self.timezone,
                }

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks",
                headers=headers,
                json=task_data,
            )

            if response.status_code == 201:
                return "Task created successfully."
            else:
                raise Exception(f"Failed to create task: {response.text}")

        except Exception as e:
            logging.error(f"Error creating todo task: {str(e)}")
            return f"Failed to create task: {str(e)}"

    async def update_todo_task(self, task_id, list_name="Tasks", **updates):
        """
        Updates an existing todo task.

        Args:
            task_id (str): ID of the task to update
            list_name (str): Name of the todo list containing the task
            **updates: Keyword arguments for fields to update:
                - title (str): New task title
                - body (str): New task description
                - due_date (datetime): New due date
                - importance (str): New importance level
                - status (str): New status
                - reminder (datetime): New reminder time

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get list ID
            lists_response = requests.get(
                "https://graph.microsoft.com/v1.0/me/todo/lists", headers=headers
            )

            list_id = None
            for todo_list in lists_response.json()["value"]:
                if todo_list["displayName"].lower() == list_name.lower():
                    list_id = todo_list["id"]
                    break

            if not list_id:
                raise Exception(f"Todo list '{list_name}' not found")

            update_data = {}

            if "title" in updates:
                update_data["title"] = updates["title"]
            if "body" in updates:
                update_data["body"] = {
                    "content": updates["body"],
                    "contentType": "text",
                }
            if "due_date" in updates:
                update_data["dueDateTime"] = {
                    "dateTime": updates["due_date"],
                    "timeZone": self.timezone,
                }
            if "importance" in updates:
                update_data["importance"] = updates["importance"]
            if "status" in updates:
                update_data["status"] = updates["status"]
            if "reminder" in updates:
                update_data["reminderDateTime"] = {
                    "dateTime": updates["reminder"],
                    "timeZone": self.timezone,
                }

            response = requests.patch(
                f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}",
                headers=headers,
                json=update_data,
            )

            if response.status_code == 200:
                return "Task updated successfully."
            else:
                raise Exception(f"Failed to update task: {response.text}")

        except Exception as e:
            logging.error(f"Error updating todo task: {str(e)}")
            return f"Failed to update task: {str(e)}"

    async def delete_todo_task(self, task_id, list_name="Tasks"):
        """
        Deletes a task from a todo list.

        Args:
            task_id (str): ID of the task to delete
            list_name (str): Name of the todo list containing the task

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get list ID
            lists_response = requests.get(
                "https://graph.microsoft.com/v1.0/me/todo/lists", headers=headers
            )

            list_id = None
            for todo_list in lists_response.json()["value"]:
                if todo_list["displayName"].lower() == list_name.lower():
                    list_id = todo_list["id"]
                    break

            if not list_id:
                raise Exception(f"Todo list '{list_name}' not found")

            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}",
                headers=headers,
            )

            if response.status_code == 204:
                return "Task deleted successfully."
            else:
                raise Exception(f"Failed to delete task: {response.text}")

        except Exception as e:
            logging.error(f"Error deleting todo task: {str(e)}")
            return f"Failed to delete task: {str(e)}"
