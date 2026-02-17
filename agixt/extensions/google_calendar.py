from datetime import datetime, timedelta
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
Google Calendar Extension - Google Calendar event management.

This extension provides full Google Calendar functionality including creating,
modifying, and removing calendar events, as well as checking availability.
It requires separate OAuth authorization from the main Google SSO connection.

Required environment variables:

- GOOGLE_CLIENT_ID: Google OAuth client ID
- GOOGLE_CLIENT_SECRET: Google OAuth client secret

Required APIs:
- Calendar API: https://console.cloud.google.com/marketplace/product/google/calendar-json.googleapis.com

Required scopes:
- calendar.events.owned: Full access to owned calendar events
- calendar: Full calendar access
"""

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]
AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
PKCE_REQUIRED = False


class GoogleCalendarSSO:
    """SSO handler for Google Calendar with calendar-specific scopes."""

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
            raise Exception(f"Google Calendar token refresh failed: {response.text}")

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


def sso(code, redirect_uri=None) -> GoogleCalendarSSO:
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
    return GoogleCalendarSSO(access_token=access_token, refresh_token=refresh_token)


class google_calendar(Extensions):
    """
    Google Calendar Extension.

    This extension provides comprehensive Google Calendar functionality including:
    - Getting calendar events
    - Adding new events
    - Modifying existing events
    - Removing events
    - Checking time availability
    - Finding available time slots

    This extension requires separate authorization with Calendar-specific scopes,
    independent from the basic Google SSO connection.
    """

    CATEGORY = "Productivity"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("GOOGLE_CALENDAR_ACCESS_TOKEN", None)
        google_client_id = getenv("GOOGLE_CLIENT_ID")
        google_client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.timezone = getenv("TZ")
        self.auth = None

        if google_client_id and google_client_secret:
            self.commands = {
                "Google Calendar - Get Calendar Items": self.get_calendar_items,
                "Google Calendar - Get Available Timeslots": self.get_available_timeslots,
                "Google Calendar - Add Calendar Item": self.add_calendar_item,
                "Google Calendar - Modify Calendar Item": self.modify_calendar_item,
                "Google Calendar - Remove Calendar Item": self.remove_calendar_item,
                "Google Calendar - Check Availability": self.check_time_availability,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                    self.timezone = self.auth.get_timezone()
                except Exception as e:
                    logging.error(f"Error initializing Google Calendar: {str(e)}")

    def authenticate(self):
        """
        Verifies that the current access token corresponds to a valid user.
        Returns Google API credentials.
        """
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(
                provider="google_calendar"
            )

        credentials = Credentials(
            token=self.access_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=getenv("GOOGLE_CLIENT_ID"),
            client_secret=getenv("GOOGLE_CLIENT_SECRET"),
            scopes=SCOPES,
        )
        return credentials

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
            credentials = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=credentials,
                always_use_jwt_access=True,
            )

            if start_date is None:
                start_date = datetime.utcnow().isoformat() + "Z"
            elif isinstance(start_date, datetime):
                start_date = start_date.isoformat() + "Z"

            if end_date is None:
                end_date = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
            elif isinstance(end_date, datetime):
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
                start = event.get("start", {})
                end = event.get("end", {})

                item_data = {
                    "id": event["id"],
                    "subject": event.get("summary", "No Title"),
                    "start_time": start.get("dateTime", start.get("date", "")),
                    "end_time": end.get("dateTime", end.get("date", "")),
                    "location": event.get("location", ""),
                    "organizer": event.get("organizer", {}).get("email", ""),
                    "description": event.get("description", ""),
                }
                calendar_items.append(item_data)

            return calendar_items
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
            list: List of available time slots with start and end times
        """
        try:
            credentials = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=credentials,
                always_use_jwt_access=True,
            )

            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))

            end_date = start_date + timedelta(days=num_days)

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
                day_start = datetime.strptime(work_day_start, "%H:%M").time()
                day_end = datetime.strptime(work_day_end, "%H:%M").time()

                current_slot_start = datetime.combine(current_date.date(), day_start)
                day_end_time = datetime.combine(current_date.date(), day_end)

                day_events = [
                    event
                    for event in events
                    if event["start"].get("dateTime")
                    and datetime.fromisoformat(
                        event["start"]["dateTime"].replace("Z", "+00:00")
                    ).date()
                    == current_date.date()
                ]

                day_events.sort(key=lambda x: x["start"]["dateTime"])

                while (
                    current_slot_start + timedelta(minutes=duration_minutes)
                    <= day_end_time
                ):
                    slot_end = current_slot_start + timedelta(minutes=duration_minutes)
                    is_available = True

                    for event in day_events:
                        event_start = datetime.fromisoformat(
                            event["start"]["dateTime"].replace("Z", "+00:00")
                        )
                        event_end = datetime.fromisoformat(
                            event["end"]["dateTime"].replace("Z", "+00:00")
                        )

                        if current_slot_start <= event_end and slot_end >= event_start:
                            is_available = False
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
            dict: Availability status and any conflicting event information
        """
        try:
            credentials = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=credentials,
                always_use_jwt_access=True,
            )

            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

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
                if "dateTime" not in event["start"]:
                    continue

                event_start = datetime.fromisoformat(
                    event["start"]["dateTime"].replace("Z", "+00:00")
                )
                event_end = datetime.fromisoformat(
                    event["end"]["dateTime"].replace("Z", "+00:00")
                )

                if start_time <= event_end and end_time >= event_start:
                    return {
                        "is_available": False,
                        "conflict": {
                            "id": event["id"],
                            "summary": event.get("summary", "Untitled"),
                            "start_time": event["start"]["dateTime"],
                            "end_time": event["end"]["dateTime"],
                        },
                    }

            return {"is_available": True, "conflict": None}

        except Exception as e:
            logging.error(f"Error checking time availability: {str(e)}")
            return {"error": str(e)}

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
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

            if check_availability:
                availability = await self.check_time_availability(start_time, end_time)

                if not availability.get("is_available", True):
                    conflict = availability.get("conflict", {})
                    return {
                        "success": False,
                        "message": f"The user isn't available at {start_time.strftime('%Y-%m-%d %H:%M')}. "
                        f"There is a conflict with '{conflict.get('summary', 'another event')}'. "
                        f"Ask the user if they would like to schedule a different time.",
                    }

            credentials = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=credentials,
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
            subject (str): New subject (optional)
            start_time (datetime): New start time (optional)
            end_time (datetime): New end time (optional)
            location (str): New location (optional)
            attendees (List[str]): New attendee list (optional)
            description (str): New description (optional)
            check_availability (bool): Whether to check for conflicts

        Returns:
            dict: Response containing success status
        """
        try:
            credentials = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=credentials,
                always_use_jwt_access=True,
            )

            event = (
                service.events().get(calendarId="primary", eventId=event_id).execute()
            )

            if check_availability and start_time and end_time:
                if isinstance(start_time, str):
                    start_time = datetime.fromisoformat(
                        start_time.replace("Z", "+00:00")
                    )
                if isinstance(end_time, str):
                    end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

                availability = await self.check_time_availability(start_time, end_time)

                if not availability.get("is_available", True):
                    conflict = availability.get("conflict", {})
                    if conflict.get("id") != event_id:
                        return {
                            "success": False,
                            "message": f"The user isn't available at {start_time.strftime('%Y-%m-%d %H:%M')}. "
                            f"There is a conflict with '{conflict.get('summary', 'another event')}'.",
                        }

            if subject:
                event["summary"] = subject
            if start_time:
                event["start"] = {
                    "dateTime": (
                        start_time.isoformat()
                        if isinstance(start_time, datetime)
                        else start_time
                    ),
                    "timeZone": self.timezone,
                }
            if end_time:
                event["end"] = {
                    "dateTime": (
                        end_time.isoformat()
                        if isinstance(end_time, datetime)
                        else end_time
                    ),
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

            service.events().update(
                calendarId="primary", eventId=event_id, body=event
            ).execute()

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
            credentials = self.authenticate()
            service = build(
                "calendar",
                "v3",
                credentials=credentials,
                always_use_jwt_access=True,
            )
            service.events().delete(calendarId="primary", eventId=item_id).execute()
            return "Calendar item removed successfully."
        except Exception as e:
            logging.error(f"Error removing calendar item: {str(e)}")
            return f"Failed to remove calendar item: {str(e)}"
