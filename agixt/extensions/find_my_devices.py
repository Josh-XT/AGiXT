import logging
import requests
import json
import asyncio
import struct
import uuid
import binascii
import hashlib
from datetime import datetime
from Extensions import Extensions
from typing import Dict, List, Any, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class find_my_devices(Extensions):
    """
    Find My Devices extension for AGiXT enables locating, ringing, locking,
    and managing devices across multiple "Find My" networks.

    Supported networks:
    - **Apple iCloud (Find My iPhone/iPad/Mac/AirTag)**: Locate Apple devices,
      play sounds, enable lost mode, and display messages.
      Requires `pyicloud` library (`pip install pyicloud`).
    - **Life360 (Tile devices & family tracking)**: Locate Tile devices and
      family circle members using the Life360 network.
      Uses the Life360 REST API directly.
    - **Google Find My Device (Android phones, tablets & trackers)**: Locate
      Android devices, play sounds, and list registered devices on Google's
      Find My Device / Find Hub network.
      Requires `gpsoauth` library (`pip install gpsoauth`).

    To set up Apple iCloud:
    1. Use your Apple ID email and an app-specific password.
    2. Generate an app-specific password at https://appleid.apple.com/account/manage
       under "Sign-In and Security" > "App-Specific Passwords".
    3. Two-factor authentication may be required on first use; the extension
       will prompt for a verification code.

    To set up Life360:
    1. Create a Life360 account at https://www.life360.com/
    2. Use your Life360 email and password.
    3. Add Tile devices through the Life360 app to track them.

    To set up Google Find My Device:
    1. Clone GoogleFindMyTools: `git clone https://github.com/leonboe1/GoogleFindMyTools`
    2. Install its requirements: `pip install -r requirements.txt`
    3. Run `python main.py` and complete the Google Chrome authentication flow.
    4. After authentication, open `Auth/secrets.json` from the GoogleFindMyTools
       directory. Copy the values for `username`, `aas_token`, and `android_id`
       into the corresponding AGiXT agent settings below.
    5. Ensure Google Chrome is up to date on the machine used for initial auth.
    6. Once authenticated, the extension operates headlessly without Chrome.
    """

    CATEGORY = "Smart Home & IoT"
    friendly_name = "Find My Devices"

    def __init__(
        self,
        ICLOUD_USERNAME: str = "",
        ICLOUD_APP_PASSWORD: str = "",
        LIFE360_EMAIL: str = "",
        LIFE360_PASSWORD: str = "",
        GOOGLE_FINDMY_EMAIL: str = "",
        GOOGLE_FINDMY_AAS_TOKEN: str = "",
        GOOGLE_FINDMY_ANDROID_ID: str = "",
        **kwargs,
    ):
        self.icloud_username = ICLOUD_USERNAME
        self.icloud_app_password = ICLOUD_APP_PASSWORD
        self.life360_email = LIFE360_EMAIL
        self.life360_password = LIFE360_PASSWORD
        self.google_findmy_email = GOOGLE_FINDMY_EMAIL
        self.google_findmy_aas_token = GOOGLE_FINDMY_AAS_TOKEN
        self.google_findmy_android_id = GOOGLE_FINDMY_ANDROID_ID

        self._icloud_api = None
        self._life360_token = None
        self._life360_base_url = "https://api.life360.com"
        self._google_adm_token = None
        self._google_device_cache = None

        self.commands = {
            "Find My - Locate Apple Devices": self.locate_apple_devices,
            "Find My - Play Sound on Apple Device": self.play_sound_apple,
            "Find My - Enable Lost Mode on Apple Device": self.enable_lost_mode_apple,
            "Find My - Send Message to Apple Device": self.send_message_apple,
            "Find My - Get Apple Device Status": self.get_apple_device_status,
            "Find My - Locate Life360 Members": self.locate_life360_members,
            "Find My - Get Life360 Circles": self.get_life360_circles,
            "Find My - Get Life360 Member Location": self.get_life360_member_location,
            "Find My - Get Life360 Places": self.get_life360_places,
            "Find My - List Google Devices": self.list_google_devices,
            "Find My - Locate Google Device": self.locate_google_device,
            "Find My - Ring Google Device": self.ring_google_device,
        }

    # -------------------------------------------------------------------------
    # Apple iCloud Find My
    # -------------------------------------------------------------------------

    def _init_icloud(self):
        """Initialize the iCloud API connection if not already connected."""
        if self._icloud_api is not None:
            return True
        try:
            from pyicloud import PyiCloudService

            self._icloud_api = PyiCloudService(
                self.icloud_username, self.icloud_app_password
            )
            if self._icloud_api.requires_2fa:
                logging.warning(
                    "iCloud account requires two-factor authentication. "
                    "Please complete 2FA on a trusted device and retry."
                )
                return False
            logging.info("Successfully connected to iCloud.")
            return True
        except ImportError:
            logging.error(
                "pyicloud is not installed. Install it with: pip install pyicloud"
            )
            return False
        except Exception as e:
            logging.error(f"Failed to connect to iCloud: {e}")
            self._icloud_api = None
            return False

    def _get_icloud_devices(self) -> list:
        """Get the list of devices from iCloud Find My."""
        if not self._init_icloud():
            return []
        try:
            return list(self._icloud_api.devices)
        except Exception as e:
            logging.error(f"Failed to get iCloud devices: {e}")
            return []

    def _find_icloud_device(self, device_name: str):
        """Find a specific iCloud device by name (case-insensitive partial match)."""
        if not self._init_icloud():
            return None
        try:
            devices = self._icloud_api.devices
            search_name = device_name.lower()
            for device in devices:
                status = device.status()
                name = status.get("name", "").lower()
                device_display = status.get("deviceDisplayName", "").lower()
                if search_name in name or search_name in device_display:
                    return device
            return None
        except Exception as e:
            logging.error(f"Failed to find iCloud device '{device_name}': {e}")
            return None

    def _format_apple_device(self, device) -> dict:
        """Format an Apple device's status into a readable dictionary."""
        try:
            status = device.status()
            location = device.location()
            battery = status.get("batteryLevel")
            battery_pct = f"{battery * 100:.0f}%" if battery is not None else "Unknown"
            result = {
                "name": status.get("name", "Unknown"),
                "device_model": status.get("deviceDisplayName", "Unknown"),
                "battery_level": battery_pct,
                "battery_status": status.get("batteryStatus", "Unknown"),
                "device_status": status.get("deviceStatus", "Unknown"),
                "device_class": status.get("deviceClass", "Unknown"),
            }
            if location:
                result["location"] = {
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                    "accuracy": location.get("horizontalAccuracy"),
                    "timestamp": location.get("timeStamp"),
                    "address": location.get("address", {}).get(
                        "formattedAddress", "Unknown"
                    ),
                }
            else:
                result["location"] = "Location unavailable (device may be offline)"
            return result
        except Exception as e:
            logging.error(f"Failed to format Apple device: {e}")
            return {"error": str(e)}

    async def locate_apple_devices(self) -> str:
        """
        Locate all Apple devices associated with the iCloud account.
        Returns the name, model, battery level, and location of each device.

        Returns:
            str: Markdown-formatted list of all Apple devices and their locations.
        """
        if not self.icloud_username or not self.icloud_app_password:
            return "iCloud credentials not configured. Please set ICLOUD_USERNAME and ICLOUD_APP_PASSWORD in the agent settings."
        if not self._init_icloud():
            return "Failed to connect to iCloud. Please verify your credentials and ensure two-factor authentication is completed."

        try:
            devices = self._icloud_api.devices
            results = []
            for device in devices:
                info = self._format_apple_device(device)
                results.append(info)

            if not results:
                return "No devices found on this iCloud account."

            output = "## Apple Find My Devices\n\n"
            for dev in results:
                if "error" in dev:
                    output += f"- **Error**: {dev['error']}\n\n"
                    continue
                output += f"### {dev['name']}\n"
                output += f"- **Model**: {dev['device_model']}\n"
                output += (
                    f"- **Battery**: {dev['battery_level']} ({dev['battery_status']})\n"
                )
                output += f"- **Status**: {dev['device_status']}\n"
                if isinstance(dev["location"], dict):
                    loc = dev["location"]
                    output += f"- **Location**: {loc.get('address', 'Unknown')}\n"
                    output += f"  - Coordinates: {loc.get('latitude')}, {loc.get('longitude')}\n"
                    output += f"  - Accuracy: {loc.get('accuracy')}m\n"
                else:
                    output += f"- **Location**: {dev['location']}\n"
                output += "\n"
            return output
        except Exception as e:
            logging.error(f"Error locating Apple devices: {e}")
            return f"Error locating Apple devices: {str(e)}"

    async def play_sound_apple(self, device_name: str) -> str:
        """
        Play a sound on an Apple device to help locate it.
        The device will play a loud sound even if it is on silent mode.

        Args:
            device_name: The name (or partial name) of the Apple device to ring.

        Returns:
            str: Confirmation that the sound was triggered or an error message.
        """
        if not self.icloud_username or not self.icloud_app_password:
            return "iCloud credentials not configured. Please set ICLOUD_USERNAME and ICLOUD_APP_PASSWORD in the agent settings."
        device = self._find_icloud_device(device_name)
        if not device:
            return f"Could not find an Apple device matching '{device_name}'. Use 'Find My - Locate Apple Devices' to see all available devices."
        try:
            device.play_sound()
            status = device.status()
            return f"Playing sound on **{status.get('name', device_name)}**. The device should be audible now."
        except Exception as e:
            logging.error(f"Error playing sound on '{device_name}': {e}")
            return f"Failed to play sound on '{device_name}': {str(e)}"

    async def enable_lost_mode_apple(
        self,
        device_name: str,
        phone_number: str,
        message: str = "This device has been lost. Please contact the owner.",
    ) -> str:
        """
        Enable Lost Mode on an Apple device. This locks the device and displays
        a message with a contact phone number on the lock screen.

        Args:
            device_name: The name (or partial name) of the Apple device.
            phone_number: A phone number to display on the locked device.
            message: A message to display on the locked device screen.

        Returns:
            str: Confirmation that Lost Mode was enabled or an error message.
        """
        if not self.icloud_username or not self.icloud_app_password:
            return "iCloud credentials not configured. Please set ICLOUD_USERNAME and ICLOUD_APP_PASSWORD in the agent settings."
        device = self._find_icloud_device(device_name)
        if not device:
            return f"Could not find an Apple device matching '{device_name}'. Use 'Find My - Locate Apple Devices' to see all available devices."
        try:
            device.lost_device(phone_number, message)
            status = device.status()
            return (
                f"Lost Mode enabled on **{status.get('name', device_name)}**.\n"
                f"- Phone number displayed: {phone_number}\n"
                f"- Message: {message}\n\n"
                f"The device is now locked and displaying your contact information."
            )
        except Exception as e:
            logging.error(f"Error enabling lost mode on '{device_name}': {e}")
            return f"Failed to enable Lost Mode on '{device_name}': {str(e)}"

    async def send_message_apple(
        self, device_name: str, message: str, play_sound: bool = True
    ) -> str:
        """
        Send a message to an Apple device. The message will be displayed on
        the device screen, optionally accompanied by a sound.

        Args:
            device_name: The name (or partial name) of the Apple device.
            message: The message text to display on the device.
            play_sound: Whether to play a sound along with the message (default: True).

        Returns:
            str: Confirmation that the message was sent or an error message.
        """
        if not self.icloud_username or not self.icloud_app_password:
            return "iCloud credentials not configured. Please set ICLOUD_USERNAME and ICLOUD_APP_PASSWORD in the agent settings."
        device = self._find_icloud_device(device_name)
        if not device:
            return f"Could not find an Apple device matching '{device_name}'. Use 'Find My - Locate Apple Devices' to see all available devices."
        try:
            device.display_message(message, play_sound)
            status = device.status()
            return (
                f"Message sent to **{status.get('name', device_name)}**.\n"
                f"- Message: {message}\n"
                f"- Sound: {'Yes' if play_sound else 'No'}"
            )
        except Exception as e:
            logging.error(f"Error sending message to '{device_name}': {e}")
            return f"Failed to send message to '{device_name}': {str(e)}"

    async def get_apple_device_status(self, device_name: str) -> str:
        """
        Get detailed status information for a specific Apple device including
        battery level, location, and device model information.

        Args:
            device_name: The name (or partial name) of the Apple device.

        Returns:
            str: Markdown-formatted device status details or an error message.
        """
        if not self.icloud_username or not self.icloud_app_password:
            return "iCloud credentials not configured. Please set ICLOUD_USERNAME and ICLOUD_APP_PASSWORD in the agent settings."
        device = self._find_icloud_device(device_name)
        if not device:
            return f"Could not find an Apple device matching '{device_name}'. Use 'Find My - Locate Apple Devices' to see all available devices."
        try:
            info = self._format_apple_device(device)
            if "error" in info:
                return f"Error getting device status: {info['error']}"

            output = f"## {info['name']} Status\n\n"
            output += f"- **Model**: {info['device_model']}\n"
            output += f"- **Class**: {info['device_class']}\n"
            output += (
                f"- **Battery**: {info['battery_level']} ({info['battery_status']})\n"
            )
            output += f"- **Status**: {info['device_status']}\n"
            if isinstance(info["location"], dict):
                loc = info["location"]
                output += f"- **Location**: {loc.get('address', 'Unknown')}\n"
                output += (
                    f"  - Coordinates: {loc.get('latitude')}, {loc.get('longitude')}\n"
                )
                output += f"  - Accuracy: {loc.get('accuracy')}m\n"
                if loc.get("timestamp"):
                    output += f"  - Last updated: {loc['timestamp']}\n"
            else:
                output += f"- **Location**: {info['location']}\n"
            return output
        except Exception as e:
            logging.error(f"Error getting status for '{device_name}': {e}")
            return f"Failed to get status for '{device_name}': {str(e)}"

    # -------------------------------------------------------------------------
    # Life360 (Tile / Family Tracking)
    # -------------------------------------------------------------------------

    def _life360_authenticate(self) -> bool:
        """Authenticate with the Life360 API and obtain an access token."""
        if self._life360_token:
            return True
        try:
            response = requests.post(
                f"{self._life360_base_url}/v3/oauth2/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": "Basic Y2F0aGFwYWNrZXRzOlQ2OUVDVU5IVkdQNjRM",
                },
                data={
                    "grant_type": "password",
                    "username": self.life360_email,
                    "password": self.life360_password,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            self._life360_token = data.get("access_token")
            if not self._life360_token:
                logging.error("Life360 authentication returned no access token.")
                return False
            logging.info("Successfully authenticated with Life360.")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Life360 authentication failed: {e}")
            return False

    def _life360_request(self, endpoint: str) -> Optional[dict]:
        """Make an authenticated request to the Life360 API."""
        if not self._life360_authenticate():
            return None
        try:
            response = requests.get(
                f"{self._life360_base_url}{endpoint}",
                headers={
                    "Authorization": f"Bearer {self._life360_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if response.status_code == 401:
                # Token expired, re-authenticate
                self._life360_token = None
                if not self._life360_authenticate():
                    return None
                response = requests.get(
                    f"{self._life360_base_url}{endpoint}",
                    headers={
                        "Authorization": f"Bearer {self._life360_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Life360 API request failed for {endpoint}: {e}")
            return None

    def _format_life360_member(self, member: dict) -> dict:
        """Format a Life360 member's data into a readable dictionary."""
        location = member.get("location", {})
        result = {
            "name": f"{member.get('firstName', '')} {member.get('lastName', '')}".strip(),
            "id": member.get("id", "Unknown"),
            "avatar": member.get("avatar", ""),
        }
        if location:
            result["location"] = {
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "accuracy": location.get("accuracy"),
                "address": location.get("address1", "Unknown"),
                "address2": location.get("address2", ""),
                "battery": location.get("battery"),
                "charging": location.get("charge") == "1",
                "wifi_state": location.get("wifiState") == "1",
                "speed": location.get("speed"),
                "timestamp": location.get("timestamp"),
                "since": location.get("since"),
            }
            if result["location"]["timestamp"]:
                try:
                    ts = int(result["location"]["timestamp"])
                    result["location"]["last_updated"] = datetime.fromtimestamp(
                        ts
                    ).strftime("%Y-%m-%d %I:%M:%S %p")
                except (ValueError, TypeError, OSError):
                    pass
        else:
            result["location"] = "Location unavailable"
        return result

    async def get_life360_circles(self) -> str:
        """
        Get all Life360 circles (groups) associated with the account.
        A circle is a group of family members or friends who share their locations.

        Returns:
            str: Markdown-formatted list of Life360 circles with member counts.
        """
        if not self.life360_email or not self.life360_password:
            return "Life360 credentials not configured. Please set LIFE360_EMAIL and LIFE360_PASSWORD in the agent settings."
        data = self._life360_request("/v3/circles")
        if not data:
            return "Failed to retrieve Life360 circles. Please verify your credentials."

        circles = data.get("circles", [])
        if not circles:
            return "No Life360 circles found on this account."

        output = "## Life360 Circles\n\n"
        for circle in circles:
            member_count = len(circle.get("members", []))
            output += f"### {circle.get('name', 'Unnamed')}\n"
            output += f"- **Circle ID**: {circle.get('id', 'Unknown')}\n"
            output += f"- **Members**: {member_count}\n"
            output += f"- **Color**: {circle.get('color', 'N/A')}\n\n"
        return output

    async def locate_life360_members(self, circle_name: str = "") -> str:
        """
        Locate all members in Life360 circles. If a circle name is specified,
        only members in that circle are returned. Otherwise, members from all
        circles are shown.

        Args:
            circle_name: Optional name of the Life360 circle to filter by.

        Returns:
            str: Markdown-formatted list of members and their current locations.
        """
        if not self.life360_email or not self.life360_password:
            return "Life360 credentials not configured. Please set LIFE360_EMAIL and LIFE360_PASSWORD in the agent settings."
        data = self._life360_request("/v3/circles")
        if not data:
            return "Failed to retrieve Life360 circles. Please verify your credentials."

        circles = data.get("circles", [])
        if not circles:
            return "No Life360 circles found on this account."

        output = "## Life360 Member Locations\n\n"
        found_circle = False

        for circle in circles:
            name = circle.get("name", "Unnamed")
            if circle_name and circle_name.lower() not in name.lower():
                continue
            found_circle = True
            circle_id = circle.get("id")
            circle_data = self._life360_request(f"/v3/circles/{circle_id}")
            if not circle_data:
                output += f"### {name}\n- Failed to fetch circle details.\n\n"
                continue

            members = circle_data.get("members", [])
            output += f"### {name}\n\n"
            if not members:
                output += "- No members found.\n\n"
                continue

            for member in members:
                info = self._format_life360_member(member)
                output += f"#### {info['name']}\n"
                if isinstance(info["location"], dict):
                    loc = info["location"]
                    output += f"- **Address**: {loc.get('address', 'Unknown')}"
                    if loc.get("address2"):
                        output += f" {loc['address2']}"
                    output += "\n"
                    output += f"- **Coordinates**: {loc.get('latitude')}, {loc.get('longitude')}\n"
                    output += f"- **Battery**: {loc.get('battery', 'Unknown')}%"
                    if loc.get("charging"):
                        output += " (Charging)"
                    output += "\n"
                    if loc.get("speed") and float(loc.get("speed", 0)) > 0:
                        output += f"- **Speed**: {loc['speed']} mph\n"
                    if loc.get("last_updated"):
                        output += f"- **Last Updated**: {loc['last_updated']}\n"
                else:
                    output += f"- **Location**: {info['location']}\n"
                output += "\n"

        if not found_circle and circle_name:
            return f"No Life360 circle found matching '{circle_name}'. Use 'Find My - Get Life360 Circles' to see available circles."
        return output

    async def get_life360_member_location(
        self, member_name: str, circle_name: str = ""
    ) -> str:
        """
        Get the detailed location of a specific Life360 member by name.

        Args:
            member_name: The name (or partial name) of the member to locate.
            circle_name: Optional circle name to search within.

        Returns:
            str: Markdown-formatted detailed location of the member.
        """
        if not self.life360_email or not self.life360_password:
            return "Life360 credentials not configured. Please set LIFE360_EMAIL and LIFE360_PASSWORD in the agent settings."
        data = self._life360_request("/v3/circles")
        if not data:
            return "Failed to retrieve Life360 circles. Please verify your credentials."

        circles = data.get("circles", [])
        search_name = member_name.lower()

        for circle in circles:
            name = circle.get("name", "Unnamed")
            if circle_name and circle_name.lower() not in name.lower():
                continue

            circle_id = circle.get("id")
            circle_data = self._life360_request(f"/v3/circles/{circle_id}")
            if not circle_data:
                continue

            for member in circle_data.get("members", []):
                full_name = f"{member.get('firstName', '')} {member.get('lastName', '')}".strip().lower()
                if search_name in full_name:
                    info = self._format_life360_member(member)
                    output = f"## {info['name']} - Location Details\n\n"
                    output += f"- **Circle**: {name}\n"
                    if isinstance(info["location"], dict):
                        loc = info["location"]
                        output += f"- **Address**: {loc.get('address', 'Unknown')}"
                        if loc.get("address2"):
                            output += f" {loc['address2']}"
                        output += "\n"
                        output += f"- **Coordinates**: {loc.get('latitude')}, {loc.get('longitude')}\n"
                        output += f"- **Accuracy**: {loc.get('accuracy', 'Unknown')}m\n"
                        output += f"- **Battery**: {loc.get('battery', 'Unknown')}%"
                        if loc.get("charging"):
                            output += " (Charging)"
                        output += "\n"
                        output += f"- **WiFi**: {'Connected' if loc.get('wifi_state') else 'Disconnected'}\n"
                        if loc.get("speed") and float(loc.get("speed", 0)) > 0:
                            output += f"- **Speed**: {loc['speed']} mph\n"
                        if loc.get("last_updated"):
                            output += f"- **Last Updated**: {loc['last_updated']}\n"
                        if loc.get("since"):
                            try:
                                since_ts = int(loc["since"])
                                since_str = datetime.fromtimestamp(since_ts).strftime(
                                    "%Y-%m-%d %I:%M:%S %p"
                                )
                                output += f"- **At Location Since**: {since_str}\n"
                            except (ValueError, TypeError, OSError):
                                pass
                    else:
                        output += f"- **Location**: {info['location']}\n"
                    return output

        return f"Could not find a Life360 member matching '{member_name}'. Use 'Find My - Locate Life360 Members' to see all available members."

    async def get_life360_places(self, circle_name: str = "") -> str:
        """
        Get saved places (geofences) for Life360 circles. Places are locations
        like "Home", "Work", or "School" that trigger arrival/departure notifications.

        Args:
            circle_name: Optional circle name to filter by.

        Returns:
            str: Markdown-formatted list of saved places for each circle.
        """
        if not self.life360_email or not self.life360_password:
            return "Life360 credentials not configured. Please set LIFE360_EMAIL and LIFE360_PASSWORD in the agent settings."
        data = self._life360_request("/v3/circles")
        if not data:
            return "Failed to retrieve Life360 circles. Please verify your credentials."

        circles = data.get("circles", [])
        if not circles:
            return "No Life360 circles found on this account."

        output = "## Life360 Saved Places\n\n"
        found_circle = False

        for circle in circles:
            name = circle.get("name", "Unnamed")
            if circle_name and circle_name.lower() not in name.lower():
                continue
            found_circle = True
            circle_id = circle.get("id")
            places_data = self._life360_request(f"/v3/circles/{circle_id}/places")
            if not places_data:
                output += f"### {name}\n- Failed to fetch places.\n\n"
                continue

            places = places_data.get(
                "places", places_data if isinstance(places_data, list) else []
            )
            output += f"### {name}\n\n"
            if not places:
                output += "- No saved places.\n\n"
                continue

            for place in places:
                output += f"#### {place.get('name', 'Unnamed Place')}\n"
                output += f"- **Coordinates**: {place.get('latitude')}, {place.get('longitude')}\n"
                output += f"- **Radius**: {place.get('radius', 'Unknown')}m\n"
                if place.get("address1"):
                    output += f"- **Address**: {place['address1']}\n"
                output += "\n"

        if not found_circle and circle_name:
            return f"No Life360 circle found matching '{circle_name}'. Use 'Find My - Get Life360 Circles' to see available circles."
        return output

    # -------------------------------------------------------------------------
    # Google Find My Device (Android / Find Hub Network)
    # -------------------------------------------------------------------------

    @staticmethod
    def _pb_encode_varint(value):
        """Encode an integer as a protobuf varint."""
        result = bytearray()
        while value > 0x7F:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value & 0x7F)
        return bytes(result)

    @staticmethod
    def _pb_decode_varint(data, offset):
        """Decode a protobuf varint from data at the given offset."""
        result = 0
        shift = 0
        while offset < len(data):
            byte = data[offset]
            result |= (byte & 0x7F) << shift
            offset += 1
            if not (byte & 0x80):
                break
            shift += 7
        return result, offset

    @staticmethod
    def _pb_encode_field(field_number, wire_type, value):
        """Encode a single protobuf field."""
        tag = find_my_devices._pb_encode_varint((field_number << 3) | wire_type)
        if wire_type == 0:  # Varint
            return tag + find_my_devices._pb_encode_varint(value)
        elif wire_type == 2:  # Length-delimited
            if isinstance(value, str):
                value = value.encode("utf-8")
            return tag + find_my_devices._pb_encode_varint(len(value)) + value
        elif wire_type == 5:  # 32-bit fixed
            return tag + struct.pack("<i", value)
        return tag

    @staticmethod
    def _pb_decode_fields(data):
        """Decode all protobuf fields from binary data into a list of (field_number, wire_type, value) tuples."""
        fields = []
        offset = 0
        while offset < len(data):
            tag, offset = find_my_devices._pb_decode_varint(data, offset)
            field_number = tag >> 3
            wire_type = tag & 0x07
            if wire_type == 0:  # Varint
                value, offset = find_my_devices._pb_decode_varint(data, offset)
            elif wire_type == 1:  # 64-bit
                value = data[offset : offset + 8]
                offset += 8
            elif wire_type == 2:  # Length-delimited
                length, offset = find_my_devices._pb_decode_varint(data, offset)
                value = data[offset : offset + length]
                offset += length
            elif wire_type == 5:  # 32-bit
                value = data[offset : offset + 4]
                offset += 4
            else:
                break
            fields.append((field_number, wire_type, value))
        return fields

    @staticmethod
    def _pb_get_field(fields, field_number, wire_type=None):
        """Get the first field matching the given field number."""
        for fn, wt, val in fields:
            if fn == field_number and (wire_type is None or wt == wire_type):
                return val
        return None

    @staticmethod
    def _pb_get_all_fields(fields, field_number, wire_type=None):
        """Get all fields matching the given field number."""
        return [
            val
            for fn, wt, val in fields
            if fn == field_number and (wire_type is None or wt == wire_type)
        ]

    def _google_authenticate(self) -> bool:
        """Authenticate with Google using gpsoauth and obtain an ADM-scoped OAuth token."""
        if self._google_adm_token:
            return True
        try:
            import gpsoauth

            auth_response = gpsoauth.perform_oauth(
                self.google_findmy_email,
                self.google_findmy_aas_token,
                self.google_findmy_android_id,
                service="oauth2:https://www.googleapis.com/auth/android_device_manager",
                app="com.google.android.apps.adm",
                client_sig="38918a453d07199354f8b19af05ec6562ced5788",
            )
            token = auth_response.get("Auth")
            if not token:
                error = auth_response.get("Error", "Unknown error")
                logging.error(f"Google ADM auth returned no token: {error}")
                return False
            self._google_adm_token = token
            logging.info("Successfully authenticated with Google Find My Device.")
            return True
        except ImportError:
            logging.error(
                "gpsoauth is not installed. Install it with: pip install gpsoauth"
            )
            return False
        except Exception as e:
            logging.error(f"Failed to authenticate with Google: {e}")
            self._google_adm_token = None
            return False

    def _google_nova_request(self, api_scope: str, payload_hex: str) -> Optional[bytes]:
        """Make a request to Google's Nova API with the given protobuf payload."""
        if not self._google_authenticate():
            return None
        try:
            url = f"https://android.googleapis.com/nova/{api_scope}"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Authorization": f"Bearer {self._google_adm_token}",
                "Accept-Language": "en-US",
                "User-Agent": "fmd/20006320; gzip",
            }
            payload = binascii.unhexlify(payload_hex)
            response = requests.post(url, headers=headers, data=payload, timeout=30)
            if response.status_code == 401:
                self._google_adm_token = None
                if not self._google_authenticate():
                    return None
                headers["Authorization"] = f"Bearer {self._google_adm_token}"
                response = requests.post(url, headers=headers, data=payload, timeout=30)
            if response.status_code == 200:
                return response.content
            else:
                logging.error(
                    f"Google Nova API error ({response.status_code}): {response.text[:500]}"
                )
                return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Google Nova API request failed: {e}")
            return None

    def _google_build_device_list_request(self) -> str:
        """Build the protobuf hex payload for a device list request."""
        request_uuid = str(uuid.uuid4())
        # DevicesListRequestPayload: field 1 (type=SPOT_DEVICE=2), field 3 (id=UUID)
        inner = self._pb_encode_field(1, 0, 2) + self._pb_encode_field(
            3, 2, request_uuid
        )
        # DevicesListRequest: field 1 (deviceListRequestPayload)
        outer = self._pb_encode_field(1, 2, inner)
        return binascii.hexlify(outer).decode("utf-8")

    def _google_parse_device_list(self, response_data: bytes) -> list:
        """Parse a DevicesList protobuf response into a list of device dicts."""
        devices = []
        try:
            top_fields = self._pb_decode_fields(response_data)
            # DevicesList.deviceMetadata is field 2 (repeated)
            device_blobs = self._pb_get_all_fields(top_fields, 2, wire_type=2)
            for device_blob in device_blobs:
                device_info = self._google_parse_device_metadata(device_blob)
                if device_info:
                    devices.append(device_info)
        except Exception as e:
            logging.error(f"Error parsing Google device list: {e}")
        return devices

    def _google_parse_device_metadata(self, data: bytes) -> Optional[dict]:
        """Parse a DeviceMetadata protobuf blob into a device dict."""
        try:
            fields = self._pb_decode_fields(data)
            # Field 5: userDefinedDeviceName (string)
            name_bytes = self._pb_get_field(fields, 5, wire_type=2)
            name = name_bytes.decode("utf-8") if name_bytes else "Unknown Device"
            # Field 6: imageInformation
            image_url = ""
            image_blob = self._pb_get_field(fields, 6, wire_type=2)
            if image_blob:
                image_fields = self._pb_decode_fields(image_blob)
                url_bytes = self._pb_get_field(image_fields, 1, wire_type=2)
                if url_bytes:
                    image_url = url_bytes.decode("utf-8")
            # Field 1: identifierInformation
            canonic_ids = []
            device_type = "unknown"
            id_blob = self._pb_get_field(fields, 1, wire_type=2)
            if id_blob:
                id_fields = self._pb_decode_fields(id_blob)
                # Field 2: type (enum IdentifierInformationType)
                id_type = self._pb_get_field(id_fields, 2, wire_type=0)
                if id_type == 1:
                    device_type = "android"
                elif id_type == 2:
                    device_type = "tracker"
                # Field 3: canonicIds (for trackers)
                cids_blob = self._pb_get_field(id_fields, 3, wire_type=2)
                if cids_blob:
                    cids_fields = self._pb_decode_fields(cids_blob)
                    for cid_blob in self._pb_get_all_fields(
                        cids_fields, 1, wire_type=2
                    ):
                        cid_fields = self._pb_decode_fields(cid_blob)
                        cid_id = self._pb_get_field(cid_fields, 1, wire_type=2)
                        if cid_id:
                            canonic_ids.append(cid_id.decode("utf-8"))
                # Field 1: phoneInformation (for Android devices)
                phone_blob = self._pb_get_field(id_fields, 1, wire_type=2)
                if phone_blob:
                    phone_fields = self._pb_decode_fields(phone_blob)
                    phone_cids_blob = self._pb_get_field(phone_fields, 2, wire_type=2)
                    if phone_cids_blob:
                        phone_cids_fields = self._pb_decode_fields(phone_cids_blob)
                        for cid_blob in self._pb_get_all_fields(
                            phone_cids_fields, 1, wire_type=2
                        ):
                            cid_fields = self._pb_decode_fields(cid_blob)
                            cid_id = self._pb_get_field(cid_fields, 1, wire_type=2)
                            if cid_id:
                                cid_str = cid_id.decode("utf-8")
                                if cid_str not in canonic_ids:
                                    canonic_ids.append(cid_str)
            # Field 4: DeviceInformation
            device_type_name = ""
            manufacturer = ""
            model = ""
            info_blob = self._pb_get_field(fields, 4, wire_type=2)
            if info_blob:
                info_fields = self._pb_decode_fields(info_blob)
                # Field 1: deviceRegistration
                reg_blob = self._pb_get_field(info_fields, 1, wire_type=2)
                if reg_blob:
                    reg_fields = self._pb_decode_fields(reg_blob)
                    # Field 20: manufacturer
                    mfr_bytes = self._pb_get_field(reg_fields, 20, wire_type=2)
                    if mfr_bytes:
                        manufacturer = mfr_bytes.decode("utf-8")
                    # Field 34: model
                    model_bytes = self._pb_get_field(reg_fields, 34, wire_type=2)
                    if model_bytes:
                        model = model_bytes.decode("utf-8")
                    # Field 2: deviceTypeInformation
                    dtype_blob = self._pb_get_field(reg_fields, 2, wire_type=2)
                    if dtype_blob:
                        dtype_fields = self._pb_decode_fields(dtype_blob)
                        spot_type = self._pb_get_field(dtype_fields, 2, wire_type=0)
                        spot_type_names = {
                            1: "Beacon",
                            2: "Headphones",
                            3: "Keys",
                            4: "Watch",
                            5: "Wallet",
                            7: "Bag",
                            8: "Laptop",
                            9: "Car",
                            10: "Remote Control",
                            11: "Badge",
                            12: "Bike",
                            13: "Camera",
                            14: "Cat",
                            15: "Charger",
                            16: "Clothing",
                            17: "Dog",
                            18: "Notebook",
                            19: "Passport",
                            20: "Phone",
                            21: "Speaker",
                            22: "Tablet",
                            23: "Toy",
                            24: "Umbrella",
                            25: "Stylus",
                            26: "Earbuds",
                        }
                        if spot_type is not None:
                            device_type_name = spot_type_names.get(
                                spot_type, f"Type {spot_type}"
                            )
            return {
                "name": name,
                "device_type": device_type,
                "device_type_name": device_type_name,
                "manufacturer": manufacturer,
                "model": model,
                "canonic_ids": canonic_ids,
                "image_url": image_url,
            }
        except Exception as e:
            logging.error(f"Error parsing device metadata: {e}")
            return None

    def _google_find_device(self, device_name: str) -> Optional[dict]:
        """Find a Google device by name (case-insensitive partial match)."""
        if not self._google_device_cache:
            hex_payload = self._google_build_device_list_request()
            response = self._google_nova_request("nbe_list_devices", hex_payload)
            if not response:
                return None
            self._google_device_cache = self._google_parse_device_list(response)
        search = device_name.lower()
        for device in self._google_device_cache:
            if search in device["name"].lower():
                return device
        return None

    def _google_build_ring_request(self, canonic_id: str) -> str:
        """Build the protobuf hex payload for a ring/start-sound action request."""
        request_uuid = str(uuid.uuid4())
        client_uuid = str(uuid.uuid4())
        # ExecuteActionScope (field 1)
        canonic_id_msg = self._pb_encode_field(1, 2, canonic_id)
        device_identifier = self._pb_encode_field(1, 2, canonic_id_msg)
        scope = self._pb_encode_field(2, 0, 2) + self._pb_encode_field(
            3, 2, device_identifier
        )
        # ExecuteActionType (field 2) - startSound (field 31)
        sound_type = self._pb_encode_field(1, 0, 0)
        action = self._pb_encode_field(31, 2, sound_type)
        # ExecuteActionRequestMetadata (field 3)
        gcm_id = self._pb_encode_field(1, 2, "")
        metadata = (
            self._pb_encode_field(1, 0, 2)
            + self._pb_encode_field(2, 2, request_uuid)
            + self._pb_encode_field(3, 2, client_uuid)
            + self._pb_encode_field(4, 2, gcm_id)
            + self._pb_encode_field(6, 0, 1)
        )
        # ExecuteActionRequest
        request = (
            self._pb_encode_field(1, 2, scope)
            + self._pb_encode_field(2, 2, action)
            + self._pb_encode_field(3, 2, metadata)
        )
        return binascii.hexlify(request).decode("utf-8")

    def _google_build_locate_request(self, canonic_id: str, fcm_token: str = "") -> str:
        """Build the protobuf hex payload for a locate action request."""
        request_uuid = str(uuid.uuid4())
        client_uuid = str(uuid.uuid4())
        # ExecuteActionScope
        canonic_id_msg = self._pb_encode_field(1, 2, canonic_id)
        device_identifier = self._pb_encode_field(1, 2, canonic_id_msg)
        scope = self._pb_encode_field(2, 0, 2) + self._pb_encode_field(
            3, 2, device_identifier
        )
        # ExecuteActionType - locateTracker (field 30)
        time_msg = self._pb_encode_field(1, 0, 1732120060)
        locate_tracker = self._pb_encode_field(2, 2, time_msg) + self._pb_encode_field(
            3, 0, 2
        )  # FMDN_ALL_LOCATIONS
        action = self._pb_encode_field(30, 2, locate_tracker)
        # ExecuteActionRequestMetadata
        gcm_id = self._pb_encode_field(1, 2, fcm_token)
        metadata = (
            self._pb_encode_field(1, 0, 2)
            + self._pb_encode_field(2, 2, request_uuid)
            + self._pb_encode_field(3, 2, client_uuid)
            + self._pb_encode_field(4, 2, gcm_id)
            + self._pb_encode_field(6, 0, 1)
        )
        # ExecuteActionRequest
        request = (
            self._pb_encode_field(1, 2, scope)
            + self._pb_encode_field(2, 2, action)
            + self._pb_encode_field(3, 2, metadata)
        )
        return binascii.hexlify(request).decode("utf-8")

    async def list_google_devices(self) -> str:
        """
        List all devices registered on Google Find My Device / Find Hub network.
        Returns device names, types, manufacturers, and model information for
        all Android devices and trackers associated with the Google account.

        Returns:
            str: Markdown-formatted list of all Google Find My devices.
        """
        if not self.google_findmy_email or not self.google_findmy_aas_token:
            return (
                "Google Find My Device credentials not configured. "
                "Please set GOOGLE_FINDMY_EMAIL, GOOGLE_FINDMY_AAS_TOKEN, and "
                "GOOGLE_FINDMY_ANDROID_ID in the agent settings. "
                "See the extension documentation for setup instructions using GoogleFindMyTools."
            )

        hex_payload = self._google_build_device_list_request()
        response = self._google_nova_request("nbe_list_devices", hex_payload)
        if not response:
            return "Failed to retrieve Google devices. Please verify your credentials are correct and not expired."

        devices = self._google_parse_device_list(response)
        self._google_device_cache = devices

        if not devices:
            return "No devices found on this Google account's Find My Device network."

        output = "## Google Find My Devices\n\n"
        for idx, dev in enumerate(devices, start=1):
            output += f"### {idx}. {dev['name']}\n"
            type_label = dev["device_type"].capitalize()
            if dev["device_type_name"]:
                type_label += f" ({dev['device_type_name']})"
            output += f"- **Type**: {type_label}\n"
            if dev["manufacturer"]:
                output += f"- **Manufacturer**: {dev['manufacturer']}\n"
            if dev["model"]:
                output += f"- **Model**: {dev['model']}\n"
            if dev["canonic_ids"]:
                output += f"- **Device ID**: {dev['canonic_ids'][0]}\n"
            output += "\n"
        return output

    async def locate_google_device(self, device_name: str) -> str:
        """
        Request the location of a Google Find My Device. This sends a locate
        request to the device through Google's Find Hub network.

        Note: Full location decryption requires the device's end-to-end encryption
        keys and an active FCM (Firebase Cloud Messaging) listener. This command
        sends the locate request which will trigger the device to report its
        location to Google's servers. The location can then be viewed in the
        Google Find My Device app or web interface at https://www.google.com/android/find

        Args:
            device_name: The name (or partial name) of the Google device to locate.

        Returns:
            str: Confirmation that the locate request was sent or an error message.
        """
        if not self.google_findmy_email or not self.google_findmy_aas_token:
            return (
                "Google Find My Device credentials not configured. "
                "Please set GOOGLE_FINDMY_EMAIL, GOOGLE_FINDMY_AAS_TOKEN, and "
                "GOOGLE_FINDMY_ANDROID_ID in the agent settings."
            )

        device = self._google_find_device(device_name)
        if not device:
            return (
                f"Could not find a Google device matching '{device_name}'. "
                "Use 'Find My - List Google Devices' to see all available devices."
            )

        if not device["canonic_ids"]:
            return f"Device '{device['name']}' has no canonic ID. Cannot send locate request."

        canonic_id = device["canonic_ids"][0]
        hex_payload = self._google_build_locate_request(canonic_id)
        response = self._google_nova_request("nbe_execute_action", hex_payload)

        if response is not None:
            return (
                f"Locate request sent to **{device['name']}**.\n\n"
                f"The device has been asked to report its location to Google's servers. "
                f"You can view the updated location at: https://www.google.com/android/find\n\n"
                f"**Note**: For trackers on the Find My Device Network, encrypted location "
                f"reports may take a few minutes to be collected from nearby Android devices."
            )
        else:
            return f"Failed to send locate request to '{device['name']}'. The device may be offline or the credentials may have expired."

    async def ring_google_device(self, device_name: str) -> str:
        """
        Play a sound on a Google Find My Device to help locate it.
        The device will ring at full volume even if it is on silent mode.
        Works with Android phones, tablets, and supported trackers.

        Args:
            device_name: The name (or partial name) of the Google device to ring.

        Returns:
            str: Confirmation that the ring command was sent or an error message.
        """
        if not self.google_findmy_email or not self.google_findmy_aas_token:
            return (
                "Google Find My Device credentials not configured. "
                "Please set GOOGLE_FINDMY_EMAIL, GOOGLE_FINDMY_AAS_TOKEN, and "
                "GOOGLE_FINDMY_ANDROID_ID in the agent settings."
            )

        device = self._google_find_device(device_name)
        if not device:
            return (
                f"Could not find a Google device matching '{device_name}'. "
                "Use 'Find My - List Google Devices' to see all available devices."
            )

        if not device["canonic_ids"]:
            return f"Device '{device['name']}' has no canonic ID. Cannot send ring command."

        canonic_id = device["canonic_ids"][0]
        hex_payload = self._google_build_ring_request(canonic_id)
        response = self._google_nova_request("nbe_execute_action", hex_payload)

        if response is not None:
            return (
                f"Ring command sent to **{device['name']}**. "
                f"The device should start playing a sound now."
            )
        else:
            return f"Failed to ring '{device['name']}'. The device may be offline or the credentials may have expired."
