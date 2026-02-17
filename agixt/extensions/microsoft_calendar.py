import logging
import requests
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from fastapi import HTTPException

"""
Microsoft Calendar Extension - Outlook Calendar functionality.

This extension provides access to Microsoft Outlook Calendar features including
creating, reading, modifying, and deleting calendar events. It requires separate
OAuth authorization from the main Microsoft SSO connection.

Required environment variables:

- MICROSOFT_CLIENT_ID: Microsoft OAuth client ID
- MICROSOFT_CLIENT_SECRET: Microsoft OAuth client secret

Required scopes:
- offline_access: Required for refresh tokens
- User.Read: Read user profile information
- Calendars.ReadWrite: Read and write calendar events
- Calendars.ReadWrite.Shared: Access shared calendars
"""

SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/Calendars.ReadWrite.Shared",
]
AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
PKCE_REQUIRED = False


class MicrosoftCalendarSSO:
    """SSO handler for Microsoft Calendar with calendar-specific scopes."""

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
            raise Exception(f"Microsoft Calendar token refresh failed: {response.text}")

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


def sso(code, redirect_uri=None) -> MicrosoftCalendarSSO:
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
        logging.error(f"Error getting Microsoft Calendar access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "Not provided")
    return MicrosoftCalendarSSO(access_token=access_token, refresh_token=refresh_token)


class microsoft_calendar(Extensions):
    """
    Microsoft Calendar (Outlook) Extension.

    This extension provides comprehensive integration with Microsoft Outlook Calendar,
    allowing AI agents to manage calendar events, check availability, and schedule meetings.

    Features:
    - View calendar events
    - Create new events with Teams meeting support
    - Modify existing events
    - Delete/cancel events
    - Check time slot availability
    - Get available timeslots

    This extension requires separate authorization with calendar-specific scopes,
    independent from the basic Microsoft SSO connection.
    """

    CATEGORY = "Productivity"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("MICROSOFT_CALENDAR_ACCESS_TOKEN", None)
        microsoft_client_id = getenv("MICROSOFT_CLIENT_ID")
        microsoft_client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.timezone = getenv("TZ")
        self.auth = None

        if microsoft_client_id and microsoft_client_secret:
            self.commands = {
                "Get Calendar Events": self.get_calendar_items,
                "Get Available Timeslots": self.get_available_timeslots,
                "Add Calendar Event": self.add_calendar_item,
                "Modify Calendar Event": self.modify_calendar_item,
                "Remove Calendar Event": self.remove_calendar_item,
                "Check Time Availability": self.check_time_availability,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                    self.timezone = self.auth.get_timezone()
                except Exception as e:
                    logging.error(
                        f"Error initializing Microsoft Calendar client: {str(e)}"
                    )

    def verify_user(self):
        """Verifies that the current access token is valid."""
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(
                provider="microsoft_calendar"
            )

        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        if response.status_code != 200:
            raise Exception(
                f"User not found or invalid token. Status: {response.status_code}, "
                f"Response: {response.text}. Ensure the Microsoft Calendar extension is connected."
            )

    def _parse_datetime(self, dt_input):
        """Parse datetime input that can be either a string or datetime object."""
        if isinstance(dt_input, str):
            dt_str = dt_input.strip()

            try:
                if dt_str.endswith("Z"):
                    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                elif "+" in dt_str or dt_str.endswith("00:00"):
                    return datetime.fromisoformat(dt_str)
                else:
                    if "." in dt_str:
                        date_part, time_part = dt_str.split("T")
                        if "." in time_part:
                            time_base, microseconds = time_part.split(".")
                            microseconds = microseconds[:6].ljust(6, "0")
                            dt_str = f"{date_part}T{time_base}.{microseconds}"

                    return datetime.fromisoformat(dt_str)
            except ValueError:
                try:
                    if "T" in dt_str:
                        dt_str = dt_str.split(".")[0]
                    return datetime.fromisoformat(dt_str)
                except ValueError:
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
        """Format datetime for Microsoft Graph API."""
        if isinstance(dt, str):
            dt = self._parse_datetime(dt)

        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

    async def check_time_availability(self, start_time, end_time):
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

            start_dt = self._parse_datetime(start_time)
            end_dt = self._parse_datetime(end_time)

            existing_events = await self.get_calendar_items(
                start_date=start_dt, end_date=end_dt, max_items=50
            )

            for event in existing_events:
                event_start = self._parse_datetime(event["start_time"])
                event_end = self._parse_datetime(event["end_time"])

                if start_dt < event_end and end_dt > event_start:
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
            start_time (datetime or str): Event start time
            end_time (datetime or str): Event end time
            location (str): Optional physical location
            attendees (list): Optional list of attendee email addresses
            body (str): Optional event description
            is_online_meeting (bool): Whether to create as Teams meeting
            reminder_minutes_before (int): Minutes before event to send reminder

        Returns:
            dict: Success status and event information
        """
        try:
            start_dt = self._parse_datetime(start_time)
            end_dt = self._parse_datetime(end_time)

            if isinstance(is_online_meeting, str):
                is_online_meeting = is_online_meeting.lower() in ("true", "1", "yes")

            if isinstance(reminder_minutes_before, str):
                try:
                    reminder_minutes_before = int(reminder_minutes_before)
                except ValueError:
                    reminder_minutes_before = 15

            is_available, conflict = await self.check_time_availability(
                start_dt, end_dt
            )

            if not is_available:
                return {
                    "success": False,
                    "message": f"The user isn't available at {start_dt.strftime('%Y-%m-%d %H:%M')}. "
                    f"There is a conflict with '{conflict['subject']}'. "
                    f"Ask the user if they would like to schedule a different time.",
                }

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
                    if attendees.strip():
                        attendees = [
                            email.strip()
                            for email in attendees.split(",")
                            if email.strip()
                        ]
                    else:
                        attendees = []

                if attendees:
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

            max_items = int(max_items)

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Prefer": f'outlook.timezone="{self.timezone}"',
            }

            if not start_date:
                start_date = datetime.now()
            if not end_date:
                end_date = start_date + timedelta(days=7)

            if isinstance(start_date, str):
                start_date = self._parse_datetime(start_date)

            if isinstance(end_date, str):
                end_date = self._parse_datetime(end_date)
                if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
                    end_date = end_date.replace(hour=23, minute=59, second=59)

            if (
                start_date.date() == end_date.date()
                and end_date.hour == 0
                and end_date.minute == 0
                and end_date.second == 0
            ):
                end_date = end_date.replace(hour=23, minute=59, second=59)

            if start_date.tzinfo is None:
                start_str = start_date.isoformat() + "Z"
            else:
                start_str = start_date.isoformat()

            if end_date.tzinfo is None:
                end_str = end_date.isoformat() + "Z"
            else:
                end_str = end_date.isoformat()

            url = (
                f"https://graph.microsoft.com/v1.0/me/calendarView?"
                f"startDateTime={start_str}&"
                f"endDateTime={end_str}&"
                f"$top={max_items}&$orderby=start/dateTime"
            )

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                alt_url = f"https://graph.microsoft.com/v1.0/me/events?$top={max_items}"
                alt_response = requests.get(alt_url, headers=headers)

                if alt_response.status_code == 200:
                    response = alt_response
                else:
                    return []

            data = response.json()

            if not data.get("value"):
                return []

            events = []
            for event in data["value"]:
                try:
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
                except Exception as event_err:
                    logging.error(f"Error processing event: {str(event_err)}")
                    continue

            return events

        except Exception as e:
            logging.error(f"Error retrieving calendar items: {str(e)}")
            return []

    async def get_available_timeslots(
        self,
        date=None,
        duration_minutes=30,
        start_hour=9,
        end_hour=17,
    ):
        """
        Gets available time slots for a given day.

        Args:
            date (datetime or str): The date to check (defaults to today)
            duration_minutes (int): Required duration for the meeting
            start_hour (int): Start of working hours (default 9 AM)
            end_hour (int): End of working hours (default 5 PM)

        Returns:
            list: List of available time slot dictionaries
        """
        try:
            self.verify_user()

            if date is None:
                date = datetime.now()
            elif isinstance(date, str):
                date = self._parse_datetime(date)

            duration_minutes = int(duration_minutes)
            start_hour = int(start_hour)
            end_hour = int(end_hour)

            start_of_day = date.replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )
            end_of_day = date.replace(hour=end_hour, minute=0, second=0, microsecond=0)

            events = await self.get_calendar_items(
                start_date=start_of_day,
                end_date=end_of_day,
                max_items=50,
            )

            busy_times = []
            for event in events:
                event_start = self._parse_datetime(event["start_time"])
                event_end = self._parse_datetime(event["end_time"])
                busy_times.append((event_start, event_end))

            busy_times.sort(key=lambda x: x[0])

            available_slots = []
            current_time = start_of_day

            for busy_start, busy_end in busy_times:
                if current_time + timedelta(minutes=duration_minutes) <= busy_start:
                    available_slots.append(
                        {
                            "start": current_time.strftime("%Y-%m-%d %H:%M"),
                            "end": busy_start.strftime("%Y-%m-%d %H:%M"),
                            "duration_available": int(
                                (busy_start - current_time).total_seconds() / 60
                            ),
                        }
                    )
                current_time = max(current_time, busy_end)

            if current_time + timedelta(minutes=duration_minutes) <= end_of_day:
                available_slots.append(
                    {
                        "start": current_time.strftime("%Y-%m-%d %H:%M"),
                        "end": end_of_day.strftime("%Y-%m-%d %H:%M"),
                        "duration_available": int(
                            (end_of_day - current_time).total_seconds() / 60
                        ),
                    }
                )

            return available_slots

        except Exception as e:
            logging.error(f"Error getting available timeslots: {str(e)}")
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
            subject (str): New event title/subject
            start_time (datetime): New event start time
            end_time (datetime): New event end time
            location (str): New physical location
            attendees (list): New list of attendee email addresses
            body (str): New event description
            is_online_meeting (bool): Whether to set as Teams meeting
            reminder_minutes_before (int): New reminder time
            check_availability (bool): Whether to check for conflicts

        Returns:
            dict: Success status and any conflict information
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Prefer": f'outlook.timezone="{self.timezone}"',
            }

            event_check = requests.get(
                f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                headers=headers,
            )

            if event_check.status_code != 200:
                return {
                    "success": False,
                    "message": f"Event with ID {event_id} not found or inaccessible.",
                }

            if check_availability and start_time and end_time:
                start_dt = self._parse_datetime(start_time)
                end_dt = self._parse_datetime(end_time)

                is_available, conflict = await self.check_time_availability(
                    start_dt, end_dt
                )

                if not is_available and conflict.get("id") != event_id:
                    return {
                        "success": False,
                        "message": f"Time conflict with '{conflict['subject']}'.",
                    }

            update_data = {}

            if subject:
                update_data["subject"] = subject
            if start_time:
                start_dt = self._parse_datetime(start_time)
                update_data["start"] = {
                    "dateTime": self._format_datetime_for_api(start_dt),
                    "timeZone": self.timezone or "UTC",
                }
            if end_time:
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
                if isinstance(is_online_meeting, str):
                    is_online_meeting = is_online_meeting.lower() in (
                        "true",
                        "1",
                        "yes",
                    )
                update_data["isOnlineMeeting"] = is_online_meeting
            if reminder_minutes_before is not None:
                if isinstance(reminder_minutes_before, str):
                    try:
                        reminder_minutes_before = int(reminder_minutes_before)
                    except ValueError:
                        reminder_minutes_before = 15
                update_data["reminderMinutesBeforeStart"] = reminder_minutes_before
            if attendees is not None:
                if isinstance(attendees, str):
                    if attendees.strip():
                        attendees = [
                            email.strip()
                            for email in attendees.split(",")
                            if email.strip()
                        ]
                    else:
                        attendees = []

                if attendees:
                    update_data["attendees"] = [
                        {"emailAddress": {"address": email}, "type": "required"}
                        for email in attendees
                    ]

            if not update_data:
                return {
                    "success": True,
                    "message": "No changes requested for calendar event.",
                }

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
                raise Exception(f"Failed to modify event: {response.text}")

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

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                headers=headers,
            )

            if response.status_code == 204:
                return "Calendar event deleted successfully."
            else:
                cancel_data = {"comment": "Cancelled by AI assistant"}
                cancel_response = requests.post(
                    f"https://graph.microsoft.com/v1.0/me/events/{event_id}/cancel",
                    headers=headers,
                    json=cancel_data,
                )

                if cancel_response.status_code == 202:
                    return "Calendar event cancelled successfully."

                raise Exception(f"Failed to delete event: {response.text}")

        except Exception as e:
            logging.error(f"Error deleting calendar event: {str(e)}")
            return f"Failed to delete calendar event: {str(e)}"
