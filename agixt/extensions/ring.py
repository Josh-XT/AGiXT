import logging
import asyncio
import json
from pathlib import Path
from Extensions import Extensions
from Globals import getenv
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class ring(Extensions):
    """
    Ring Camera System extension for AGiXT

    This extension provides control over Ring camera systems including:
    - Viewing live streams
    - Accessing recorded videos
    - Adjusting device settings
    - Checking motion alerts
    - Enabling/disabling alerts

    Required environment variables:
    - RING_USERNAME: Your Ring account username/email
    - RING_PASSWORD: Your Ring account password
    - RING_USER_AGENT: Optional custom user agent (defaults to "AGiXT-Ring-1.0")

    Authentication: Username/password authentication with 2FA support
    Note: Ring uses token caching to minimize login frequency
    """

    CATEGORY = "Smart Home & IoT"

    def __init__(
        self,
        RING_USERNAME: str = "",
        RING_PASSWORD: str = "",
        RING_USER_AGENT: str = "AGiXT-Ring-1.0",
        **kwargs,
    ):
        self.username = RING_USERNAME
        self.password = RING_PASSWORD
        self.user_agent = RING_USER_AGENT

        self.commands = {
            "View Live Stream": self.view_live_stream,
            "Access Recorded Video": self.access_recorded_video,
            "Adjust Device Settings": self.adjust_device_settings,
            "Check Motion Alerts": self.check_motion_alerts,
            "Enable Motion Alerts": self.enable_motion_alerts,
            "Disable Motion Alerts": self.disable_motion_alerts,
            "Get Device List": self.get_device_list,
            "Download Recent Videos": self.download_recent_videos,
            "Get Device Health": self.get_device_health,
            "Set Device Lights": self.set_device_lights,
            "Test Device Sound": self.test_device_sound,
        }
        self.ring = None
        self.auth = None
        self._initialized = False
        self.cache_file = Path(f"{self.user_agent}.token.cache")

    def _token_updated(self, token):
        """Callback function to save updated tokens"""
        try:
            self.cache_file.write_text(json.dumps(token))
            logging.info("Ring token cache updated")
        except Exception as e:
            logging.error(f"Failed to save token cache: {str(e)}")

    async def _initialize_ring(self):
        """Initialize the Ring connection if not already done"""
        if self._initialized and self.ring:
            return True

        try:
            # Import ring_doorbell inside the method to avoid import errors if not installed
            from ring_doorbell import Auth, Ring, AuthenticationError, Requires2FAError

            # Check for cached token first
            if self.cache_file.is_file():
                try:
                    cached_token = json.loads(self.cache_file.read_text())
                    self.auth = Auth(self.user_agent, cached_token, self._token_updated)
                    self.ring = Ring(self.auth)

                    # Test if cached token is still valid
                    await self.ring.async_create_session()
                    await self.ring.async_update_data()
                    self._initialized = True
                    logging.info("Successfully connected to Ring using cached token")
                    return True

                except AuthenticationError:
                    logging.info("Cached token expired, need to re-authenticate")
                    # Fall through to fresh authentication
                except Exception as cache_error:
                    logging.warning(f"Error using cached token: {str(cache_error)}")
                    # Fall through to fresh authentication

            # Fresh authentication required
            self.auth = Auth(self.user_agent, None, self._token_updated)

            try:
                await self.auth.async_fetch_token(self.username, self.password)
            except Requires2FAError:
                # Note: In a real implementation, you would need to handle 2FA
                # This could be done by prompting the user or having a stored 2FA token
                logging.error("2FA required but not implemented in this extension")
                return False

            self.ring = Ring(self.auth)
            await self.ring.async_create_session()
            await self.ring.async_update_data()

            self._initialized = True
            logging.info(
                "Successfully connected to Ring system with fresh authentication"
            )
            return True

        except ImportError:
            logging.error(
                "ring_doorbell library not installed. Run: pip install ring_doorbell"
            )
            return False
        except Exception as e:
            logging.error(f"Failed to initialize Ring connection: {str(e)}")
            return False

    async def view_live_stream(self, device_name: str) -> str:
        """
        Get live stream URL for a Ring device

        Args:
            device_name (str): Name of the Ring device

        Returns:
            str: Live stream URL or error message
        """
        try:
            if not await self._initialize_ring():
                return "Error: Failed to connect to Ring system"

            devices = self.ring.devices()
            all_devices = devices.get("doorbots", []) + devices.get("stickup_cams", [])

            # Find the device
            target_device = None
            for device in all_devices:
                if device.name == device_name:
                    target_device = device
                    break

            if not target_device:
                available_devices = [device.name for device in all_devices]
                return f"Error: Device '{device_name}' not found. Available devices: {available_devices}"

            # Note: Ring live streaming requires special handling and may not be directly accessible
            # This is a placeholder for the live stream functionality
            return f"Live stream access for '{device_name}' would require additional Ring API integration. Device ID: {target_device.id}"

        except Exception as e:
            logging.error(f"Error accessing live stream: {str(e)}")
            return f"Error accessing live stream: {str(e)}"

    async def access_recorded_video(
        self, device_name: str, video_id: str = None, limit: int = 1
    ) -> str:
        """
        Access recorded videos from a Ring device

        Args:
            device_name (str): Name of the Ring device
            video_id (str): Optional specific video ID. If not provided, gets most recent.
            limit (int): Number of videos to retrieve if video_id not specified

        Returns:
            str: Video URL(s) or download information
        """
        try:
            if not await self._initialize_ring():
                return "Error: Failed to connect to Ring system"

            devices = self.ring.devices()
            all_devices = devices.get("doorbots", []) + devices.get("stickup_cams", [])

            # Find the device
            target_device = None
            for device in all_devices:
                if device.name == device_name:
                    target_device = device
                    break

            if not target_device:
                available_devices = [device.name for device in all_devices]
                return f"Error: Device '{device_name}' not found. Available devices: {available_devices}"

            if video_id:
                # Get specific video URL
                try:
                    video_url = await target_device.async_recording_url(video_id)
                    return f"Video URL for {device_name} (ID: {video_id}):\n{video_url}"
                except Exception as url_error:
                    return f"Error getting video URL: {str(url_error)}"
            else:
                # Get recent videos
                try:
                    history = await target_device.async_history(limit=limit)
                    if not history:
                        return f"No recorded videos found for {device_name}"

                    results = [f"# Recent Videos for {device_name}"]

                    for i, event in enumerate(history[:limit]):
                        event_id = event.get("id", "Unknown")
                        event_kind = event.get("kind", "Unknown")
                        event_time = event.get("created_at", "Unknown time")
                        answered = event.get("answered", False)

                        results.append(f"## Video {i+1}")
                        results.append(f"- **ID:** {event_id}")
                        results.append(f"- **Type:** {event_kind}")
                        results.append(f"- **Time:** {event_time}")
                        results.append(f"- **Answered:** {'Yes' if answered else 'No'}")

                        # Try to get video URL
                        try:
                            video_url = await target_device.async_recording_url(
                                event_id
                            )
                            results.append(f"- **URL:** {video_url}")
                        except:
                            results.append(f"- **URL:** Unable to retrieve")

                        results.append("")

                    return "\n".join(results)

                except Exception as history_error:
                    return f"Error getting video history: {str(history_error)}"

        except Exception as e:
            logging.error(f"Error accessing recorded video: {str(e)}")
            return f"Error accessing recorded video: {str(e)}"

    async def adjust_device_settings(
        self, device_name: str, setting: str, value: str
    ) -> str:
        """
        Adjust settings for a Ring device

        Args:
            device_name (str): Name of the Ring device
            setting (str): Setting to adjust (volume, motion_detection, etc.)
            value (str): New value for the setting

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_ring():
                return "Error: Failed to connect to Ring system"

            devices = self.ring.devices()
            all_devices = (
                devices.get("doorbots", [])
                + devices.get("stickup_cams", [])
                + devices.get("chimes", [])
            )

            # Find the device
            target_device = None
            for device in all_devices:
                if device.name == device_name:
                    target_device = device
                    break

            if not target_device:
                available_devices = [device.name for device in all_devices]
                return f"Error: Device '{device_name}' not found. Available devices: {available_devices}"

            # Handle different settings
            if setting.lower() == "volume":
                try:
                    volume_value = int(value)
                    if 0 <= volume_value <= 10:
                        await target_device.async_set_volume(volume_value)
                        return f"Successfully set volume to {volume_value} for {device_name}"
                    else:
                        return "Error: Volume must be between 0 and 10"
                except ValueError:
                    return "Error: Volume must be a number between 0 and 10"

            elif setting.lower() == "motion_detection":
                try:
                    motion_enabled = value.lower() in [
                        "true",
                        "1",
                        "yes",
                        "on",
                        "enable",
                    ]
                    await target_device.async_set_motion_detection(motion_enabled)
                    status = "enabled" if motion_enabled else "disabled"
                    return f"Successfully {status} motion detection for {device_name}"
                except Exception as motion_error:
                    return f"Error setting motion detection: {str(motion_error)}"

            elif setting.lower() == "lights" and hasattr(target_device, "lights"):
                if target_device.lights:
                    lights_on = value.lower() in ["true", "1", "yes", "on", "enable"]
                    await target_device.async_lights("on" if lights_on else "off")
                    status = "on" if lights_on else "off"
                    return f"Successfully turned lights {status} for {device_name}"
                else:
                    return f"Device {device_name} does not have controllable lights"

            else:
                return f"Error: Setting '{setting}' is not supported. Supported settings: volume, motion_detection, lights"

        except Exception as e:
            logging.error(f"Error adjusting device settings: {str(e)}")
            return f"Error adjusting device settings: {str(e)}"

    async def check_motion_alerts(
        self, device_name: str = None, limit: int = 10
    ) -> str:
        """
        Check motion alerts for Ring devices

        Args:
            device_name (str): Optional specific device name. If not provided,
                             checks all devices.
            limit (int): Maximum number of alerts to retrieve (default: 10)

        Returns:
            str: Motion alerts formatted as markdown
        """
        try:
            if not await self._initialize_ring():
                return "Error: Failed to connect to Ring system"

            devices = self.ring.devices()
            all_devices = devices.get("doorbots", []) + devices.get("stickup_cams", [])

            if device_name:
                # Check specific device
                target_device = None
                for device in all_devices:
                    if device.name == device_name:
                        target_device = device
                        break

                if not target_device:
                    available_devices = [device.name for device in all_devices]
                    return f"Error: Device '{device_name}' not found. Available devices: {available_devices}"

                devices_to_check = [target_device]
            else:
                # Check all devices
                devices_to_check = all_devices

            if not devices_to_check:
                return "No Ring devices found"

            alerts_info = [f"# Motion Alerts (Last {limit})"]

            for device in devices_to_check:
                try:
                    # Get motion events
                    motion_history = await device.async_history(
                        limit=limit, kind="motion"
                    )

                    alerts_info.append(f"## {device.name}")

                    if motion_history:
                        for event in motion_history:
                            event_time = event.get("created_at", "Unknown time")
                            event_id = event.get("id", "Unknown")
                            answered = event.get("answered", False)

                            alerts_info.append(
                                f"- **{event_time}:** Motion detected (ID: {event_id}) - {'Answered' if answered else 'Not answered'}"
                            )
                    else:
                        alerts_info.append("- No recent motion alerts")

                    alerts_info.append("")

                except Exception as device_error:
                    logging.warning(
                        f"Error getting alerts for device {device.name}: {str(device_error)}"
                    )
                    alerts_info.append(f"## {device.name}")
                    alerts_info.append(
                        f"- Error retrieving alerts: {str(device_error)}"
                    )
                    alerts_info.append("")

            return "\n".join(alerts_info)

        except Exception as e:
            logging.error(f"Error checking motion alerts: {str(e)}")
            return f"Error checking motion alerts: {str(e)}"

    async def enable_motion_alerts(self, device_name: str) -> str:
        """
        Enable motion alerts for a Ring device

        Args:
            device_name (str): Name of the Ring device

        Returns:
            str: Success message or error details
        """
        return await self.adjust_device_settings(
            device_name, "motion_detection", "true"
        )

    async def disable_motion_alerts(self, device_name: str) -> str:
        """
        Disable motion alerts for a Ring device

        Args:
            device_name (str): Name of the Ring device

        Returns:
            str: Success message or error details
        """
        return await self.adjust_device_settings(
            device_name, "motion_detection", "false"
        )

    async def get_device_list(self) -> str:
        """
        Get a list of all Ring devices

        Returns:
            str: List of devices formatted as markdown
        """
        try:
            if not await self._initialize_ring():
                return "Error: Failed to connect to Ring system"

            devices = self.ring.devices()

            device_info = ["# Ring Device List"]

            # Doorbells
            doorbells = devices.get("doorbots", [])
            if doorbells:
                device_info.append("## Doorbells")
                for device in doorbells:
                    device_info.extend(
                        [
                            f"### {device.name}",
                            f"- **ID:** {device.id}",
                            f"- **Family:** {device.family}",
                            f"- **Address:** {getattr(device, 'address', 'N/A')}",
                            f"- **Timezone:** {getattr(device, 'timezone', 'N/A')}",
                            "",
                        ]
                    )

            # Stickup Cams
            stickup_cams = devices.get("stickup_cams", [])
            if stickup_cams:
                device_info.append("## Stickup Cameras")
                for device in stickup_cams:
                    device_info.extend(
                        [
                            f"### {device.name}",
                            f"- **ID:** {device.id}",
                            f"- **Family:** {device.family}",
                            f"- **Has Lights:** {'Yes' if getattr(device, 'lights', False) else 'No'}",
                            f"- **Address:** {getattr(device, 'address', 'N/A')}",
                            "",
                        ]
                    )

            # Chimes
            chimes = devices.get("chimes", [])
            if chimes:
                device_info.append("## Chimes")
                for device in chimes:
                    device_info.extend(
                        [
                            f"### {device.name}",
                            f"- **ID:** {device.id}",
                            f"- **Family:** {device.family}",
                            "",
                        ]
                    )

            if len(device_info) == 1:  # Only header added
                device_info.append("No Ring devices found")

            return "\n".join(device_info)

        except Exception as e:
            logging.error(f"Error getting device list: {str(e)}")
            return f"Error getting device list: {str(e)}"

    async def download_recent_videos(self, device_name: str, count: int = 5) -> str:
        """
        Download recent videos from a Ring device

        Args:
            device_name (str): Name of the Ring device
            count (int): Number of recent videos to download (default: 5)

        Returns:
            str: Download results
        """
        try:
            if not await self._initialize_ring():
                return "Error: Failed to connect to Ring system"

            devices = self.ring.devices()
            all_devices = devices.get("doorbots", []) + devices.get("stickup_cams", [])

            # Find the device
            target_device = None
            for device in all_devices:
                if device.name == device_name:
                    target_device = device
                    break

            if not target_device:
                available_devices = [device.name for device in all_devices]
                return f"Error: Device '{device_name}' not found. Available devices: {available_devices}"

            # Get recent history
            history = await target_device.async_history(limit=count)

            if not history:
                return f"No videos found for {device_name}"

            results = [f"# Download Results for {device_name}"]

            for i, event in enumerate(history[:count]):
                event_id = event.get("id", f"unknown_{i}")
                event_kind = event.get("kind", "unknown")
                event_time = event.get("created_at", "unknown_time")

                filename = f"{device_name}_{event_kind}_{event_id}.mp4"

                try:
                    await target_device.async_recording_download(
                        event_id, filename=filename, override=True
                    )
                    results.append(f"✓ Downloaded: {filename} ({event_time})")
                except Exception as download_error:
                    results.append(
                        f"✗ Failed to download {filename}: {str(download_error)}"
                    )

            return "\n".join(results)

        except Exception as e:
            logging.error(f"Error downloading videos: {str(e)}")
            return f"Error downloading videos: {str(e)}"

    async def get_device_health(self, device_name: str = None) -> str:
        """
        Get health information for Ring devices

        Args:
            device_name (str): Optional specific device name. If not provided,
                             gets health for all devices.

        Returns:
            str: Device health information formatted as markdown
        """
        try:
            if not await self._initialize_ring():
                return "Error: Failed to connect to Ring system"

            devices = self.ring.devices()
            all_devices = (
                devices.get("doorbots", [])
                + devices.get("stickup_cams", [])
                + devices.get("chimes", [])
            )

            if device_name:
                # Check specific device
                target_device = None
                for device in all_devices:
                    if device.name == device_name:
                        target_device = device
                        break

                if not target_device:
                    available_devices = [device.name for device in all_devices]
                    return f"Error: Device '{device_name}' not found. Available devices: {available_devices}"

                devices_to_check = [target_device]
            else:
                devices_to_check = all_devices

            if not devices_to_check:
                return "No Ring devices found"

            health_info = ["# Ring Device Health"]

            for device in devices_to_check:
                try:
                    await device.async_update_health_data()

                    health_info.extend(
                        [
                            f"## {device.name}",
                            f"- **WiFi Name:** {getattr(device, 'wifi_name', 'N/A')}",
                            f"- **WiFi Signal Strength:** {getattr(device, 'wifi_signal_strength', 'N/A')}",
                            f"- **Battery Level:** {getattr(device, 'battery_life', 'N/A')}",
                            f"- **Volume:** {getattr(device, 'volume', 'N/A')}",
                            f"- **Address:** {getattr(device, 'address', 'N/A')}",
                            f"- **Timezone:** {getattr(device, 'timezone', 'N/A')}",
                            "",
                        ]
                    )

                except Exception as device_error:
                    health_info.extend(
                        [
                            f"## {device.name}",
                            f"- Error retrieving health data: {str(device_error)}",
                            "",
                        ]
                    )

            return "\n".join(health_info)

        except Exception as e:
            logging.error(f"Error getting device health: {str(e)}")
            return f"Error getting device health: {str(e)}"

    async def set_device_lights(
        self, device_name: str, state: str, duration: int = None
    ) -> str:
        """
        Control lights on Ring devices that support them

        Args:
            device_name (str): Name of the Ring device
            state (str): "on" or "off"
            duration (int): Optional duration in seconds for temporary activation

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_ring():
                return "Error: Failed to connect to Ring system"

            devices = self.ring.devices()
            all_devices = devices.get(
                "stickup_cams", []
            )  # Only stickup cams typically have lights

            # Find the device
            target_device = None
            for device in all_devices:
                if device.name == device_name:
                    target_device = device
                    break

            if not target_device:
                available_devices = [
                    device.name
                    for device in all_devices
                    if getattr(device, "lights", False)
                ]
                return f"Error: Device '{device_name}' not found or doesn't have lights. Devices with lights: {available_devices}"

            if not getattr(target_device, "lights", False):
                return f"Device '{device_name}' does not have controllable lights"

            state_normalized = state.lower()

            if state_normalized == "on":
                if duration:
                    # Use Ring's light group functionality if available
                    groups = self.ring.groups()
                    for group in groups.values():
                        if hasattr(group, "async_set_lights"):
                            await group.async_set_lights(True, duration)
                            return f"Successfully turned on lights for {device_name} for {duration} seconds"

                    # Fallback to device-level control
                    await target_device.async_lights("on")
                    return f"Successfully turned on lights for {device_name} (duration control not available)"
                else:
                    await target_device.async_lights("on")
                    return f"Successfully turned on lights for {device_name}"

            elif state_normalized == "off":
                await target_device.async_lights("off")
                return f"Successfully turned off lights for {device_name}"

            else:
                return "Error: State must be 'on' or 'off'"

        except Exception as e:
            logging.error(f"Error controlling device lights: {str(e)}")
            return f"Error controlling device lights: {str(e)}"

    async def test_device_sound(
        self, device_name: str, sound_type: str = "ding"
    ) -> str:
        """
        Test sound on Ring chime devices

        Args:
            device_name (str): Name of the Ring chime device
            sound_type (str): Type of sound to test ("ding" or "motion")

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_ring():
                return "Error: Failed to connect to Ring system"

            devices = self.ring.devices()
            chimes = devices.get("chimes", [])

            # Find the chime device
            target_chime = None
            for device in chimes:
                if device.name == device_name:
                    target_chime = device
                    break

            if not target_chime:
                available_chimes = [device.name for device in chimes]
                return f"Error: Chime '{device_name}' not found. Available chimes: {available_chimes}"

            if sound_type.lower() not in ["ding", "motion"]:
                return "Error: Sound type must be 'ding' or 'motion'"

            await target_chime.async_test_sound(kind=sound_type.lower())
            return f"Successfully tested {sound_type} sound on {device_name}"

        except Exception as e:
            logging.error(f"Error testing device sound: {str(e)}")
            return f"Error testing device sound: {str(e)}"
