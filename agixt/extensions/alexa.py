import logging
import requests
import asyncio
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class alexa(Extensions):
    """
    The Alexa extension for AGiXT enables you to interact with Amazon Alexa devices and services.
    This extension provides comprehensive control over your Alexa ecosystem including:
    - Music and media playback control
    - Smart home device management
    - Reminder and alarm management
    - Weather and information queries
    - Custom skill interaction
    - Device notification and messaging

    All interactions use Amazon's official Alexa Voice Service API with proper OAuth authentication.
    """

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("ALEXA_ACCESS_TOKEN", None)
        alexa_client_id = getenv("ALEXA_CLIENT_ID")
        alexa_client_secret = getenv("ALEXA_CLIENT_SECRET")

        self.base_url = "https://api.amazonalexa.com/v1"
        self.session = requests.Session()
        self.failures = 0
        self.auth = None

        # Only enable commands if Alexa is properly configured
        if alexa_client_id and alexa_client_secret:
            self.commands = {
                "Play Music": self.play_music,
                "Set Reminder": self.set_reminder,
                "Control Smart Home Device": self.control_smart_home_device,
                "Get Weather": self.get_weather,
                "Check Calendar": self.check_calendar,
                "Send Custom Message": self.send_custom_message,
                "Get Device List": self.get_device_list,
                "Send Notification": self.send_notification,
                "Control Volume": self.control_volume,
                "Get Device Status": self.get_device_status,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Alexa extension auth: {str(e)}")
        else:
            self.commands = {}

    def verify_user(self):
        """
        Verify user access token and refresh if needed using MagicalAuth
        """
        if not self.auth:
            raise Exception("Authentication context not initialized.")

        try:
            # Refresh token via MagicalAuth, which handles expiry checks
            refreshed_token = self.auth.refresh_oauth_token(provider="alexa")
            if refreshed_token:
                self.access_token = refreshed_token
                self.session.headers.update(
                    {
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    }
                )
            else:
                if not self.access_token:
                    raise Exception("No valid Alexa access token found")

        except Exception as e:
            logging.error(f"Error verifying/refreshing Alexa token: {str(e)}")
            raise Exception("Failed to authenticate with Alexa")

    async def play_music(
        self, artist: str = "", song: str = "", playlist: str = "", device_id: str = ""
    ) -> str:
        """
        Play music on an Alexa device

        Args:
        artist (str): Artist name to play
        song (str): Specific song to play
        playlist (str): Playlist name to play
        device_id (str): Target device ID (optional)

        Returns:
        str: Status of the music playback request
        """
        try:
            self.verify_user()

            # Build the speech request based on parameters
            if song and artist:
                speech_text = f"Play {song} by {artist}"
            elif artist:
                speech_text = f"Play music by {artist}"
            elif playlist:
                speech_text = f"Play playlist {playlist}"
            elif song:
                speech_text = f"Play {song}"
            else:
                speech_text = "Play music"

            # If no device specified, use the first available device
            if not device_id:
                devices = await self._get_devices()
                if devices:
                    device_id = devices[0].get("deviceSerialNumber")
                else:
                    return "No Alexa devices found"

            url = f"{self.base_url}/devices/{device_id}/actions"
            payload = {"type": "speech", "text": speech_text}

            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                self.failures = 0
                return f"Successfully sent music command: '{speech_text}' to device {device_id}"
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Unknown error")
                return f"Failed to play music: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.play_music(artist, song, playlist, device_id)
            return f"Error playing music: {str(e)}"

    async def set_reminder(
        self, reminder_text: str, time: str = "", date: str = "", device_id: str = ""
    ) -> str:
        """
        Set a reminder on an Alexa device

        Args:
        reminder_text (str): The reminder message
        time (str): Time for the reminder (e.g., "3:00 PM")
        date (str): Date for the reminder (e.g., "tomorrow", "Monday")
        device_id (str): Target device ID (optional)

        Returns:
        str: Status of the reminder creation
        """
        try:
            self.verify_user()

            # Build the speech request
            speech_parts = ["Set a reminder"]
            if date:
                speech_parts.append(f"for {date}")
            if time:
                speech_parts.append(f"at {time}")
            speech_parts.append(f"to {reminder_text}")

            speech_text = " ".join(speech_parts)

            # If no device specified, use the first available device
            if not device_id:
                devices = await self._get_devices()
                if devices:
                    device_id = devices[0].get("deviceSerialNumber")
                else:
                    return "No Alexa devices found"

            url = f"{self.base_url}/devices/{device_id}/actions"
            payload = {"type": "speech", "text": speech_text}

            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                self.failures = 0
                return (
                    f"Successfully set reminder: '{speech_text}' on device {device_id}"
                )
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Unknown error")
                return f"Failed to set reminder: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.set_reminder(reminder_text, time, date, device_id)
            return f"Error setting reminder: {str(e)}"

    async def control_smart_home_device(
        self,
        device_name: str,
        action: str = "turn on",
        value: str = "",
        alexa_device_id: str = "",
    ) -> str:
        """
        Control smart home devices through Alexa

        Args:
        device_name (str): Name of the smart home device
        action (str): Action to perform (turn on, turn off, set brightness, etc.)
        value (str): Value for the action (e.g., brightness level, temperature)
        alexa_device_id (str): Target Alexa device ID (optional)

        Returns:
        str: Status of the smart home control request
        """
        try:
            self.verify_user()

            # Build the speech command
            if value:
                speech_text = f"{action} {device_name} to {value}"
            else:
                speech_text = f"{action} {device_name}"

            # If no device specified, use the first available device
            if not alexa_device_id:
                devices = await self._get_devices()
                if devices:
                    alexa_device_id = devices[0].get("deviceSerialNumber")
                else:
                    return "No Alexa devices found"

            url = f"{self.base_url}/devices/{alexa_device_id}/actions"
            payload = {"type": "speech", "text": speech_text}

            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                self.failures = 0
                return f"Successfully sent smart home command: '{speech_text}'"
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Unknown error")
                return f"Failed to control smart home device: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.control_smart_home_device(
                    device_name, action, value, alexa_device_id
                )
            return f"Error controlling smart home device: {str(e)}"

    async def get_weather(self, location: str = "", device_id: str = "") -> str:
        """
        Get weather information through Alexa

        Args:
        location (str): Location for weather query (optional)
        device_id (str): Target device ID (optional)

        Returns:
        str: Weather information response
        """
        try:
            self.verify_user()

            # Build the speech request
            if location:
                speech_text = f"What's the weather in {location}"
            else:
                speech_text = "What's the weather"

            # If no device specified, use the first available device
            if not device_id:
                devices = await self._get_devices()
                if devices:
                    device_id = devices[0].get("deviceSerialNumber")
                else:
                    return "No Alexa devices found"

            url = f"{self.base_url}/devices/{device_id}/actions"
            payload = {"type": "speech", "text": speech_text}

            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                self.failures = 0
                return (
                    f"Successfully requested weather information for device {device_id}"
                )
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Unknown error")
                return f"Failed to get weather: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_weather(location, device_id)
            return f"Error getting weather: {str(e)}"

    async def check_calendar(
        self, timeframe: str = "today", device_id: str = ""
    ) -> str:
        """
        Check calendar events through Alexa

        Args:
        timeframe (str): Timeframe to check (today, tomorrow, this week, etc.)
        device_id (str): Target device ID (optional)

        Returns:
        str: Calendar information response
        """
        try:
            self.verify_user()

            speech_text = f"What's on my calendar {timeframe}"

            # If no device specified, use the first available device
            if not device_id:
                devices = await self._get_devices()
                if devices:
                    device_id = devices[0].get("deviceSerialNumber")
                else:
                    return "No Alexa devices found"

            url = f"{self.base_url}/devices/{device_id}/actions"
            payload = {"type": "speech", "text": speech_text}

            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                self.failures = 0
                return f"Successfully requested calendar information for {timeframe}"
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Unknown error")
                return f"Failed to check calendar: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.check_calendar(timeframe, device_id)
            return f"Error checking calendar: {str(e)}"

    async def send_custom_message(self, message: str, device_id: str = "") -> str:
        """
        Send a custom speech command to Alexa

        Args:
        message (str): Custom message/command to send
        device_id (str): Target device ID (optional)

        Returns:
        str: Status of the custom message
        """
        try:
            self.verify_user()

            # If no device specified, use the first available device
            if not device_id:
                devices = await self._get_devices()
                if devices:
                    device_id = devices[0].get("deviceSerialNumber")
                else:
                    return "No Alexa devices found"

            url = f"{self.base_url}/devices/{device_id}/actions"
            payload = {"type": "speech", "text": message}

            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                self.failures = 0
                return f"Successfully sent custom message: '{message}' to device {device_id}"
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Unknown error")
                return f"Failed to send custom message: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.send_custom_message(message, device_id)
            return f"Error sending custom message: {str(e)}"

    async def get_device_list(self) -> str:
        """
        Get list of available Alexa devices

        Returns:
        str: List of Alexa devices with details
        """
        try:
            self.verify_user()
            devices = await self._get_devices()

            if devices:
                device_info = []
                for device in devices:
                    name = device.get("accountName", "Unknown")
                    device_type = device.get("deviceType", "Unknown")
                    serial = device.get("deviceSerialNumber", "Unknown")
                    online = device.get("online", False)

                    status = "Online" if online else "Offline"
                    device_info.append(
                        f"- {name} ({device_type}) - {status} [ID: {serial}]"
                    )

                self.failures = 0
                return f"Available Alexa Devices:\n" + "\n".join(device_info)
            else:
                return "No Alexa devices found"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_device_list()
            return f"Error getting device list: {str(e)}"

    async def send_notification(self, message: str, device_id: str = "") -> str:
        """
        Send a notification to an Alexa device

        Args:
        message (str): Notification message
        device_id (str): Target device ID (optional)

        Returns:
        str: Status of the notification
        """
        try:
            self.verify_user()

            # If no device specified, use the first available device
            if not device_id:
                devices = await self._get_devices()
                if devices:
                    device_id = devices[0].get("deviceSerialNumber")
                else:
                    return "No Alexa devices found"

            url = f"{self.base_url}/devices/{device_id}/notifications"
            payload = {
                "notification": {"variants": [{"type": "SpokenText", "value": message}]}
            }

            response = self.session.post(url, json=payload)

            if response.status_code in [200, 201]:
                self.failures = 0
                return (
                    f"Successfully sent notification: '{message}' to device {device_id}"
                )
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Unknown error")
                return f"Failed to send notification: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.send_notification(message, device_id)
            return f"Error sending notification: {str(e)}"

    async def control_volume(
        self, volume_level: str = "50", device_id: str = ""
    ) -> str:
        """
        Control volume on an Alexa device

        Args:
        volume_level (str): Volume level (0-100 or "up", "down", "mute")
        device_id (str): Target device ID (optional)

        Returns:
        str: Status of the volume control
        """
        try:
            self.verify_user()

            # Build volume command
            if volume_level.lower() in ["up", "down", "mute", "unmute"]:
                speech_text = f"Volume {volume_level}"
            else:
                speech_text = f"Set volume to {volume_level}"

            # If no device specified, use the first available device
            if not device_id:
                devices = await self._get_devices()
                if devices:
                    device_id = devices[0].get("deviceSerialNumber")
                else:
                    return "No Alexa devices found"

            url = f"{self.base_url}/devices/{device_id}/actions"
            payload = {"type": "speech", "text": speech_text}

            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                self.failures = 0
                return f"Successfully controlled volume: '{speech_text}' on device {device_id}"
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Unknown error")
                return f"Failed to control volume: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.control_volume(volume_level, device_id)
            return f"Error controlling volume: {str(e)}"

    async def get_device_status(self, device_id: str = "") -> str:
        """
        Get status information for an Alexa device

        Args:
        device_id (str): Target device ID (optional, gets first device if not specified)

        Returns:
        str: Device status information
        """
        try:
            self.verify_user()

            # If no device specified, use the first available device
            if not device_id:
                devices = await self._get_devices()
                if devices:
                    device_id = devices[0].get("deviceSerialNumber")
                else:
                    return "No Alexa devices found"

            url = f"{self.base_url}/devices/{device_id}"
            response = self.session.get(url)

            if response.status_code == 200:
                device_data = response.json()

                name = device_data.get("accountName", "Unknown")
                device_type = device_data.get("deviceType", "Unknown")
                online = device_data.get("online", False)

                status_text = f"""Device Status for {name}:
- Device Type: {device_type}
- Status: {"Online" if online else "Offline"}
- Device ID: {device_id}"""

                self.failures = 0
                return status_text
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Unknown error")
                return f"Failed to get device status: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_device_status(device_id)
            return f"Error getting device status: {str(e)}"

    async def _get_devices(self) -> List[Dict]:
        """
        Internal method to get list of Alexa devices

        Returns:
        List[Dict]: List of device information
        """
        try:
            url = f"{self.base_url}/devices"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                return data.get("devices", [])
            else:
                logging.error(f"Failed to get devices: {response.status_code}")
                return []

        except Exception as e:
            logging.error(f"Error getting devices: {str(e)}")
            return []
