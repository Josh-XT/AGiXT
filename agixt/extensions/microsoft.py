import os
import logging
import requests
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
import base64


class microsoft(Extensions):
    """
    The Microsoft 365 extension provides comprehensive integration with Microsoft Office 365 services.
    This extension allows AI agents to:
    - Manage emails (read, send, move, search)
    - Handle calendar events
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

            # Try getting messages directly from the well-known folder name first
            # This is more reliable than searching for folders by display name
            try:
                url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder_name}/messages?$top={page_size}&$orderby=receivedDateTime desc"
                response = requests.get(url, headers=headers)
                if response.status_code != 200:
                    # If direct lookup fails, try to find folder by display name
                    folder_response = requests.get(
                        f"https://graph.microsoft.com/v1.0/me/mailFolders?$filter=displayName eq '{folder_name}'",
                        headers=headers,
                    )

                    if (
                        folder_response.status_code != 200
                        or not folder_response.json().get("value")
                    ):
                        logging.error(f"Folder search response: {folder_response.text}")
                        raise Exception(
                            f"Failed to find folder '{folder_name}': {folder_response.text}"
                        )

                    folder_id = folder_response.json()["value"][0]["id"]
                    url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder_id}/messages?$top={page_size}&$orderby=receivedDateTime desc"
            except Exception as e:
                logging.error(f"Error finding folder: {str(e)}")
                # Fall back to all messages in case folder can't be found
                url = f"https://graph.microsoft.com/v1.0/me/messages?$top={page_size}&$orderby=receivedDateTime desc"

            # Then get the messages
            emails = []
            while len(emails) < max_emails:
                response = requests.get(url, headers=headers)
                if response.status_code != 200:
                    logging.error(f"Failed to fetch emails: {response.text}")
                    break  # Don't raise exception here - return what we have

                data = response.json()
                if not data.get("value"):
                    logging.warning("No emails found in response")
                    break

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
                        logging.error(f"Key error processing message: {ke}")
                        continue  # Skip this message and continue with others

                if "@odata.nextLink" in data and len(emails) < max_emails:
                    url = data["@odata.nextLink"]
                else:
                    break

            return emails

        except Exception as e:
            logging.error(f"Error retrieving emails: {str(e)}")
            return []

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

            # Build update data with only provided fields
            update_data = {}

            if subject:
                update_data["subject"] = subject
            if start_time:
                # Ensure datetime is properly formatted
                if isinstance(start_time, datetime):
                    start_time = start_time.isoformat()
                update_data["start"] = {
                    "dateTime": start_time,
                    "timeZone": self.timezone,
                }
            if end_time:
                # Ensure datetime is properly formatted
                if isinstance(end_time, datetime):
                    end_time = end_time.isoformat()
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
                "Prefer": f'outlook.timezone="{self.timezone}"',
            }

            # Set default dates if not provided
            if not start_date:
                start_date = datetime.now()
            if not end_date:
                end_date = start_date + timedelta(days=7)

            # Format dates properly for the API
            start_str = (
                start_date.isoformat() + "Z"
                if "Z" not in start_date.isoformat()
                else start_date.isoformat()
            )
            end_str = (
                end_date.isoformat() + "Z"
                if "Z" not in end_date.isoformat()
                else end_date.isoformat()
            )

            logging.info(f"Fetching calendar items from {start_str} to {end_str}")

            # First check if we can access the calendar at all
            try:
                cal_check = requests.get(
                    "https://graph.microsoft.com/v1.0/me/calendar", headers=headers
                )
                if cal_check.status_code != 200:
                    logging.error(f"Calendar access error: {cal_check.text}")
            except Exception as cal_err:
                logging.error(f"Error checking calendar access: {str(cal_err)}")

            # Build URL with parameters
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

                # Try an alternative endpoint
                alt_url = (
                    f"https://graph.microsoft.com/v1.0/me/events?"
                    f"$filter=start/dateTime ge '{start_str}' and end/dateTime le '{end_str}'&"
                    f"$top={max_items}&$orderby=start/dateTime"
                )

                alt_response = requests.get(alt_url, headers=headers)
                if alt_response.status_code == 200:
                    response = alt_response
                else:
                    raise Exception(f"Failed to fetch calendar items: {error_response}")

            data = response.json()
            if not data.get("value"):
                logging.warning("No calendar events found in the specified date range")
                return []

            events = []
            for event in data["value"]:
                try:
                    # Extract and format the event details
                    event_dict = {
                        "id": event["id"],
                        "subject": event.get("subject", "(No Subject)"),
                        "start_time": event.get("start", {}).get("dateTime", ""),
                        "end_time": event.get("end", {}).get("dateTime", ""),
                        "location": event.get("location", {}).get("displayName", ""),
                        "is_online_meeting": event.get("isOnlineMeeting", False),
                        "meeting_url": event.get("onlineMeeting", {}).get(
                            "joinUrl", ""
                        ),
                        "organizer": event.get("organizer", {})
                        .get("emailAddress", {})
                        .get("address", ""),
                        "is_all_day": event.get("isAllDay", False),
                        "sensitivity": event.get("sensitivity", "normal"),
                        "status": event.get("showAs", "busy"),
                    }
                    events.append(event_dict)
                except KeyError as ke:
                    logging.error(f"Key error processing event: {ke}")
                    continue  # Skip this event but continue with others

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

            # Make sure start_date is a datetime object
            if isinstance(start_date, str):
                try:
                    start_date = datetime.fromisoformat(
                        start_date.replace("Z", "+00:00")
                    )
                except ValueError:
                    start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%S")

            logging.info(f"Finding available time slots starting from {start_date}")

            # Calculate end date
            end_date = start_date + timedelta(days=num_days)

            # Get all existing calendar events for the date range with increased limit
            existing_events = await self.get_calendar_items(
                start_date=start_date,
                end_date=end_date,
                max_items=100,  # Increased to handle busy calendars
            )

            logging.info(f"Found {len(existing_events)} existing events")

            # If we couldn't get any events, log a warning but continue
            if not existing_events and isinstance(existing_events, list):
                logging.warning("No existing events found - assuming empty calendar")

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
                        event_start_str = event["start_time"].rstrip("Z")
                        event_end_str = event["end_time"].rstrip("Z")

                        try:
                            event_start = datetime.fromisoformat(event_start_str)
                            event_end = datetime.fromisoformat(event_end_str)
                        except ValueError:
                            # Handle alternative formats
                            event_start = datetime.strptime(
                                event_start_str, "%Y-%m-%dT%H:%M:%S"
                            )
                            event_end = datetime.strptime(
                                event_end_str, "%Y-%m-%dT%H:%M:%S"
                            )

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
                "Prefer": 'outlook.timezone="{self.timezone}"',
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
                start_date, end_date = date_range
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
