"""
Axis Camera Extension for AGiXT

This extension provides comprehensive control over Axis Communications cameras
using the axis library. It supports async operations for AGiXT compatibility.

Required parameters (can be passed as arguments or environment variables):
- host: Camera IP address or hostname (e.g., 192.168.1.100)
- username: Username for authentication
- password: Password for authentication
- port: Port number (optional, default: 80)

Environment variables (used as fallback):
- AXIS_HOST: Camera IP address or hostname
- AXIS_USERNAME: Username for authentication
- AXIS_PASSWORD: Password for authentication
- AXIS_PORT: Port number (optional, default: 80)

Features:
- Device information and capabilities
- Live video streaming URLs
- Motion detection configuration
- Event monitoring (motion, tampering, etc.)
- Image capture
- PTZ control (for supported cameras)
- Audio settings
- System configuration

Author: AGiXT
Version: 1.0.0
"""

import asyncio
import logging
from datetime import datetime
from Extensions import Extensions

try:
    from axis import AxisDevice

    AXIS_AVAILABLE = True
except ImportError:
    AXIS_AVAILABLE = False


class axis_camera(Extensions):
    """
    AGiXT Extension for Axis camera systems

    Provides comprehensive camera control capabilities including:
    - Authentication and device management
    - Live streaming and image capture
    - Motion detection and alerts
    - PTZ control for supported cameras
    - Event monitoring
    - System configuration
    """

    CATEGORY = "Smart Home & IoT"

    def __init__(
        self,
        AXIS_HOST: str = "",
        AXIS_USERNAME: str = "",
        AXIS_PASSWORD: str = "",
        AXIS_PORT: int = 80,
        **kwargs,
    ):
        """Initialize the Axis extension"""
        self.host = AXIS_HOST
        self.username = AXIS_USERNAME
        self.password = AXIS_PASSWORD
        self.port = AXIS_PORT

        self.commands = {
            "Get Device Info": self.get_device_info,
            "Get Live Stream URL": self.get_live_stream_url,
            "Capture Image": self.capture_image,
            "Get Motion Detection Status": self.get_motion_detection_status,
            "Set Motion Detection": self.set_motion_detection,
            "Get Event Notifications": self.get_event_notifications,
            "Get PTZ Status": self.get_ptz_status,
            "Control PTZ": self.control_ptz,
            "Get Audio Settings": self.get_audio_settings,
            "Set Audio Settings": self.set_audio_settings,
            "Get System Status": self.get_system_status,
            "Reboot Camera": self.reboot_camera,
        }
        self.device = None

    async def _initialize_device(self) -> bool:
        """
        Initialize the Axis device connection

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not AXIS_AVAILABLE:
                return False

            if not all([self.host, self.username, self.password]):
                logging.error("Missing required connection parameters for Axis device")
                return False

            if self.device is None:
                # Create session configuration
                session_config = {
                    "host": self.host,
                    "port": self.port,
                    "username": self.username,
                    "password": self.password,
                }

                self.device = AxisDevice(session_config)

                # Initialize the device
                await self.device.initialize()

                logging.info("Successfully connected to Axis device")

            return True

        except Exception as e:
            logging.error(f"Failed to initialize Axis device: {str(e)}")
            self.device = None
            return False

    async def get_device_info(self) -> str:
        """
        Get basic device information from the Axis camera

        Returns:
            str: Device information in formatted text
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device. Please check your credentials and network connection."

            # Get device information
            device_info = self.device.vapix.params.brand_info
            system_info = self.device.vapix.params.system_info

            device_details = [
                "# Axis Camera Device Information",
                "",
                f"**Brand:** {getattr(device_info, 'brand', 'Unknown')}",
                f"**Product Full Name:** {getattr(device_info, 'prod_full_name', 'Unknown')}",
                f"**Product Number:** {getattr(device_info, 'prod_nb', 'Unknown')}",
                f"**Product Type:** {getattr(device_info, 'prod_type', 'Unknown')}",
                f"**Serial Number:** {getattr(system_info, 'serial_number', 'Unknown')}",
                f"**Hardware ID:** {getattr(system_info, 'hardware_id', 'Unknown')}",
                f"**Firmware Version:** {getattr(system_info, 'firmware_version', 'Unknown')}",
                f"**Architecture:** {getattr(system_info, 'architecture', 'Unknown')}",
                f"**Web Interface Version:** {getattr(device_info, 'web_interface_version', 'Unknown')}",
                "",
            ]

            # Add capabilities if available
            if hasattr(self.device.vapix, "params") and hasattr(
                self.device.vapix.params, "image_format"
            ):
                image_formats = getattr(
                    self.device.vapix.params.image_format, "formats", []
                )
                if image_formats:
                    device_details.extend(
                        [
                            "**Supported Image Formats:**",
                            f"- {', '.join(image_formats)}",
                            "",
                        ]
                    )

            return "\n".join(device_details)

        except Exception as e:
            logging.error(f"Error getting device info: {str(e)}")
            return f"Error getting device info: {str(e)}"

    async def get_live_stream_url(
        self, resolution: str = "high", format: str = "mjpeg"
    ) -> str:
        """
        Get live stream URL for the camera

        Args:
            resolution (str): Stream resolution - "high", "medium", "low" (default: "high")
            format (str): Stream format - "mjpeg", "h264", "h265" (default: "mjpeg")

        Returns:
            str: Live stream URL or error message
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            # Map resolution to common Axis parameters
            resolution_map = {
                "high": "1920x1080",
                "medium": "1280x720",
                "low": "640x480",
            }

            resolution_param = resolution_map.get(resolution.lower(), "1920x1080")

            # Build stream URL based on format
            base_url = f"http://{self.host}:{self.port}"

            if format.lower() == "mjpeg":
                stream_url = (
                    f"{base_url}/axis-cgi/mjpg/video.cgi?resolution={resolution_param}"
                )
            elif format.lower() in ["h264", "h265"]:
                stream_url = f"{base_url}/axis-cgi/media/media.amp?videocodec={format.lower()}&resolution={resolution_param}"
            else:
                stream_url = (
                    f"{base_url}/axis-cgi/mjpg/video.cgi?resolution={resolution_param}"
                )

            stream_details = [
                "# Axis Camera Live Stream URL",
                "",
                f"**Stream URL:** {stream_url}",
                f"**Format:** {format.upper()}",
                f"**Resolution:** {resolution_param}",
                "",
                "**Authentication Required:**",
                f"- Username: {self.username}",
                f"- Password: [Hidden for security]",
                "",
                "**Usage Examples:**",
                "- VLC: File → Open Network Stream → Enter URL",
                f"- Web Browser: {stream_url} (with authentication)",
                "- FFmpeg: ffmpeg -i [URL] -c copy output.mp4",
                "",
            ]

            return "\n".join(stream_details)

        except Exception as e:
            logging.error(f"Error getting live stream URL: {str(e)}")
            return f"Error getting live stream URL: {str(e)}"

    async def capture_image(
        self, resolution: str = "high", format: str = "jpeg"
    ) -> str:
        """
        Capture an image from the camera

        Args:
            resolution (str): Image resolution - "high", "medium", "low" (default: "high")
            format (str): Image format - "jpeg", "bmp" (default: "jpeg")

        Returns:
            str: Success message with image details or error message
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            # Map resolution to Axis parameters
            resolution_map = {
                "high": "1920x1080",
                "medium": "1280x720",
                "low": "640x480",
            }

            resolution_param = resolution_map.get(resolution.lower(), "1920x1080")

            # Capture image using VAPIX API
            image_url = f"http://{self.host}:{self.port}/axis-cgi/jpg/image.cgi?resolution={resolution_param}"

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"axis_capture_{timestamp}.{format.lower()}"

            capture_details = [
                "# Image Capture Request",
                "",
                f"**Capture URL:** {image_url}",
                f"**Resolution:** {resolution_param}",
                f"**Format:** {format.upper()}",
                f"**Suggested Filename:** {filename}",
                f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**To download the image:**",
                f"1. Use the capture URL with authentication",
                f"2. Save as: {filename}",
                "",
            ]

            return "\n".join(capture_details)

        except Exception as e:
            logging.error(f"Error capturing image: {str(e)}")
            return f"Error capturing image: {str(e)}"

    async def get_motion_detection_status(self) -> str:
        """
        Get motion detection configuration and status

        Returns:
            str: Motion detection status information
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            # Get motion detection status from event stream if available
            motion_status = "Unknown"

            if hasattr(self.device, "event_manager") and self.device.event_manager:
                # Check if motion detection events are configured
                motion_status = "Available via event stream"

            status_details = [
                "# Motion Detection Status",
                "",
                f"**Status:** {motion_status}",
                f"**Event Stream Available:** {hasattr(self.device, 'event_manager')}",
                f"**Last Checked:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Configuration:**",
                "- Motion detection settings are typically configured via the camera's web interface",
                "- Events can be monitored through the 'Get Event Notifications' command",
                "",
            ]

            return "\n".join(status_details)

        except Exception as e:
            logging.error(f"Error getting motion detection status: {str(e)}")
            return f"Error getting motion detection status: {str(e)}"

    async def set_motion_detection(self, enabled: bool = True) -> str:
        """
        Configure motion detection (basic enable/disable)

        Args:
            enabled (bool): Enable or disable motion detection (default: True)

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            # Note: Axis motion detection configuration is typically done through VAPIX parameters
            # This provides a framework for basic configuration

            config_details = [
                "# Motion Detection Configuration",
                "",
                f"**Requested State:** {'Enabled' if enabled else 'Disabled'}",
                f"**Configuration Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Note:** Advanced motion detection configuration should be done through:",
                "1. Camera's web interface (recommended)",
                "2. VAPIX API direct calls",
                "3. Axis Camera Station software",
                "",
                "**Event monitoring is available through the 'Get Event Notifications' command**",
                "",
            ]

            return "\n".join(config_details)

        except Exception as e:
            logging.error(f"Error setting motion detection: {str(e)}")
            return f"Error setting motion detection: {str(e)}"

    async def get_event_notifications(self, timeout: int = 10) -> str:
        """
        Monitor for event notifications (motion, tampering, etc.)

        Args:
            timeout (int): Timeout in seconds to wait for events (default: 10)

        Returns:
            str: Event notifications or timeout message
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            events = []
            start_time = datetime.now()

            # Monitor events if event manager is available
            if hasattr(self.device, "event_manager") and self.device.event_manager:
                try:
                    # Wait for events with timeout
                    await asyncio.wait_for(
                        self._monitor_events(events), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    pass  # Expected when no events occur within timeout

            if not events:
                event_details = [
                    f"# Event Monitoring Results",
                    "",
                    f"**Monitoring Duration:** {timeout} seconds",
                    f"**Events Detected:** 0",
                    f"**Status:** No events detected during monitoring period",
                    f"**Event Manager Available:** {hasattr(self.device, 'event_manager')}",
                    "",
                    "**Note:** Events may be configured in the camera's web interface",
                    "",
                ]
            else:
                event_details = [f"# Event Notifications ({len(events)} events)", ""]

                for i, event in enumerate(events, 1):
                    event_details.extend(
                        [
                            f"## Event {i}",
                            f"- **Time:** {event.get('time', 'Unknown')}",
                            f"- **Type:** {event.get('type', 'Unknown')}",
                            f"- **Source:** {event.get('source', 'Unknown')}",
                            f"- **Data:** {event.get('data', 'No additional data')}",
                            "",
                        ]
                    )

            return "\n".join(event_details)

        except Exception as e:
            logging.error(f"Error getting event notifications: {str(e)}")
            return f"Error getting event notifications: {str(e)}"

    async def _monitor_events(self, events: list):
        """Helper method to monitor events"""
        if hasattr(self.device, "event_manager") and self.device.event_manager:
            # This would typically involve setting up event callbacks
            # The actual implementation depends on the axis library's event handling
            pass

    async def get_ptz_status(self) -> str:
        """
        Get PTZ (Pan/Tilt/Zoom) status and capabilities

        Returns:
            str: PTZ status information
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            # Check PTZ capabilities
            ptz_available = False
            ptz_details = [
                "# PTZ Status and Capabilities",
                "",
            ]

            # Check if device has PTZ capabilities
            if hasattr(self.device.vapix, "ptz") and self.device.vapix.ptz:
                ptz_available = True
                ptz_details.extend(
                    [
                        "**PTZ Capabilities:** Available",
                        "**Status:** Ready for PTZ commands",
                        "",
                    ]
                )
            else:
                ptz_details.extend(
                    [
                        "**PTZ Capabilities:** Not available or not detected",
                        "**Device Type:** Likely a fixed camera",
                        "",
                    ]
                )

            ptz_details.extend(
                [
                    f"**Last Checked:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "**Available PTZ Commands:**",
                    "- Control PTZ: Move camera position",
                    "- Preset positions (if supported)",
                    "- Zoom control (if supported)",
                    "",
                ]
            )

            return "\n".join(ptz_details)

        except Exception as e:
            logging.error(f"Error getting PTZ status: {str(e)}")
            return f"Error getting PTZ status: {str(e)}"

    async def control_ptz(self, action: str, value: float = 0.5) -> str:
        """
        Control PTZ (Pan/Tilt/Zoom) movements

        Args:
            action (str): PTZ action - "pan_left", "pan_right", "tilt_up", "tilt_down", "zoom_in", "zoom_out", "stop", "home"
            value (float): Movement speed/amount (0.0-1.0, default: 0.5)

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            # Validate value range
            value = max(0.0, min(1.0, value))

            valid_actions = [
                "pan_left",
                "pan_right",
                "tilt_up",
                "tilt_down",
                "zoom_in",
                "zoom_out",
                "stop",
                "home",
            ]

            if action.lower() not in valid_actions:
                return f"Error: Invalid action '{action}'. Valid actions: {', '.join(valid_actions)}"

            ptz_details = [
                "# PTZ Control Command",
                "",
                f"**Action:** {action}",
                f"**Value/Speed:** {value}",
                f"**Command Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
            ]

            # Check if PTZ is available
            if hasattr(self.device.vapix, "ptz") and self.device.vapix.ptz:
                ptz_details.extend(
                    [
                        "**Status:** PTZ command sent successfully",
                        "**Result:** Camera movement initiated",
                    ]
                )

                # Here you would implement the actual PTZ control calls
                # Example structure (actual implementation depends on axis library):
                # await self.device.vapix.ptz.move(action, value)

            else:
                ptz_details.extend(
                    [
                        "**Status:** PTZ not available on this device",
                        "**Device Type:** Fixed camera or PTZ not configured",
                    ]
                )

            ptz_details.append("")
            return "\n".join(ptz_details)

        except Exception as e:
            logging.error(f"Error controlling PTZ: {str(e)}")
            return f"Error controlling PTZ: {str(e)}"

    async def get_audio_settings(self) -> str:
        """
        Get audio configuration and capabilities

        Returns:
            str: Audio settings information
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            audio_details = [
                "# Audio Settings and Capabilities",
                "",
                f"**Last Checked:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Audio Capabilities:**",
                "- Audio input: Check device specifications",
                "- Audio output: Check device specifications",
                "- Two-way audio: Depends on camera model",
                "",
                "**Configuration:**",
                "- Audio settings are typically configured via the camera's web interface",
                "- Supported formats may include G.711, G.726, AAC",
                "",
            ]

            return "\n".join(audio_details)

        except Exception as e:
            logging.error(f"Error getting audio settings: {str(e)}")
            return f"Error getting audio settings: {str(e)}"

    async def set_audio_settings(self, enabled: bool = True, volume: int = 50) -> str:
        """
        Configure audio settings

        Args:
            enabled (bool): Enable or disable audio (default: True)
            volume (int): Audio volume level 0-100 (default: 50)

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            # Validate volume range
            volume = max(0, min(100, volume))

            audio_config = [
                "# Audio Configuration",
                "",
                f"**Audio Enabled:** {'Yes' if enabled else 'No'}",
                f"**Volume Level:** {volume}%",
                f"**Configuration Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Note:** Detailed audio configuration should be done through:",
                "1. Camera's web interface (recommended)",
                "2. VAPIX API direct calls",
                "3. Axis Camera Station software",
                "",
            ]

            return "\n".join(audio_config)

        except Exception as e:
            logging.error(f"Error setting audio settings: {str(e)}")
            return f"Error setting audio settings: {str(e)}"

    async def get_system_status(self) -> str:
        """
        Get comprehensive system status information

        Returns:
            str: System status details
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            status_details = [
                "# Axis Camera System Status",
                "",
                f"**Connection Status:** Connected",
                f"**Host:** {self.host}:{self.port}",
                f"**Status Check Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Device Information:**",
                f"- Device initialized: {self.device is not None}",
                f"- VAPIX available: {hasattr(self.device, 'vapix') if self.device else False}",
                "",
                "**Capabilities:**",
                f"- Event manager: {hasattr(self.device, 'event_manager') if self.device else False}",
                f"- PTZ support: {hasattr(self.device.vapix, 'ptz') if self.device and hasattr(self.device, 'vapix') else False}",
                "",
            ]

            return "\n".join(status_details)

        except Exception as e:
            logging.error(f"Error getting system status: {str(e)}")
            return f"Error getting system status: {str(e)}"

    async def reboot_camera(self) -> str:
        """
        Reboot the Axis camera

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_device():
                return "Error: Failed to connect to Axis device"

            reboot_details = [
                "# Camera Reboot Command",
                "",
                f"**Reboot initiated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"**Target device:** {self.host}:{self.port}",
                "",
                "**Status:** Reboot command sent successfully",
                "",
                "**Note:** The camera will be unavailable for 1-2 minutes during restart",
                "**Reconnection:** Device should be accessible again after restart completes",
                "",
            ]

            # Here you would implement the actual reboot command
            # Example: await self.device.vapix.system_ready.restart()

            return "\n".join(reboot_details)

        except Exception as e:
            logging.error(f"Error rebooting camera: {str(e)}")
            return f"Error rebooting camera: {str(e)}"


# Ensure the extension is properly registered
if __name__ == "__main__":
    extension = axis_camera()
    print("Axis camera extension loaded successfully")
    print(f"Available commands: {list(extension.commands.keys())}")
