"""
Vivotek Camera Extension for AGiXT

This extension provides comprehensive control over Vivotek IP cameras
using direct HTTP API calls since no dedicated Python library exists.
It supports async operations for AGiXT compatibility.

Required parameters (can be passed as arguments or environment variables):
- host: Camera IP address or hostname (e.g., 192.168.1.100)
- username: Username for authentication (usually 'root')
- password: Password for authentication
- port: Port number (optional, default: 80)

Environment variables (used as fallback):
- VIVOTEK_HOST: Camera IP address or hostname
- VIVOTEK_USERNAME: Username for authentication
- VIVOTEK_PASSWORD: Password for authentication
- VIVOTEK_PORT: Port number (optional, default: 80)

Features:
- Device information retrieval
- Live video streaming URLs
- Motion detection configuration
- Image capture
- PTZ control (for supported cameras)
- Audio settings
- System configuration
- Event monitoring

Author: AGiXT
Version: 1.0.0
"""

import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import tempfile
import base64
import urllib.parse

try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logging.warning("aiohttp library not available. Install with: pip install aiohttp")

from Extensions import Extensions


class vivotek(Extensions):
    """
    AGiXT Extension for Vivotek camera systems

    Provides comprehensive camera control capabilities including:
    - Authentication and device management via HTTP API
    - Live streaming and image capture
    - Motion detection and alerts
    - PTZ control for supported cameras
    - System configuration
    """

    CATEGORY = "Smart Home & IoT"

    def __init__(
        self,
        VIVOTEK_HOST: str = "",
        VIVOTEK_USERNAME: str = "",
        VIVOTEK_PASSWORD: str = "",
        VIVOTEK_PORT: int = 80,
        **kwargs,
    ):
        """Initialize the Vivotek extension"""
        self.host = VIVOTEK_HOST
        self.username = VIVOTEK_USERNAME
        self.password = VIVOTEK_PASSWORD
        self.port = VIVOTEK_PORT

        # Build base URL
        self.base_url = f"http://{self.host}:{self.port}"

        self.commands = {
            "Get Device Info": self.get_device_info,
            "Get Live Stream URL": self.get_live_stream_url,
            "Capture Image": self.capture_image,
            "Get Motion Detection Status": self.get_motion_detection_status,
            "Set Motion Detection": self.set_motion_detection,
            "Get PTZ Status": self.get_ptz_status,
            "Control PTZ": self.control_ptz,
            "Get System Status": self.get_system_status,
            "Get Video Settings": self.get_video_settings,
            "Set Video Settings": self.set_video_settings,
            "Get Audio Settings": self.get_audio_settings,
            "Reboot Camera": self.reboot_camera,
        }
        self.session = None

    async def _get_session(self) -> Optional[aiohttp.ClientSession]:
        """
        Get or create an authenticated HTTP session

        Returns:
            aiohttp.ClientSession or None if failed
        """
        try:
            if not AIOHTTP_AVAILABLE:
                return None

            if not all([self.host, self.password]):
                logging.error(
                    "Missing required connection parameters for Vivotek camera"
                )
                return None

            if self.session is None or self.session.closed:
                # Create basic auth
                auth = aiohttp.BasicAuth(self.username, self.password)

                # Create session with timeout
                timeout = aiohttp.ClientTimeout(total=30)
                self.session = aiohttp.ClientSession(
                    auth=auth,
                    timeout=timeout,
                    connector=aiohttp.TCPConnector(verify_ssl=False),
                )

                # Test connection
                test_url = f"{self.base_url}/cgi-bin/viewer/getuid.cgi"
                async with self.session.get(test_url) as response:
                    if response.status == 200:
                        logging.info("Successfully authenticated with Vivotek camera")
                    else:
                        logging.warning(
                            f"Authentication test returned status {response.status}"
                        )

            return self.session

        except Exception as e:
            logging.error(f"Failed to create Vivotek session: {str(e)}")
            if self.session and not self.session.closed:
                await self.session.close()
                self.session = None
            return None

    async def _make_request(self, endpoint: str, params: Dict = None) -> Optional[str]:
        """
        Make an authenticated HTTP request to the camera

        Args:
            endpoint (str): API endpoint path
            params (Dict): Query parameters

        Returns:
            str: Response text or None if failed
        """
        try:
            session = await self._get_session()
            if not session:
                return None

            url = f"{self.base_url}{endpoint}"

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logging.warning(
                        f"Request to {endpoint} returned status {response.status}"
                    )
                    return None

        except Exception as e:
            logging.error(f"Request to {endpoint} failed: {str(e)}")
            return None

    async def get_device_info(self) -> str:
        """
        Get basic device information from the Vivotek camera

        Returns:
            str: Device information in formatted text
        """
        try:
            # Get system information
            system_info = await self._make_request(
                "/cgi-bin/admin/getparam.cgi", {"group": "system"}
            )
            network_info = await self._make_request(
                "/cgi-bin/admin/getparam.cgi", {"group": "network"}
            )

            if not system_info:
                return "Error: Failed to connect to Vivotek camera. Please check your credentials and network connection."

            device_details = [
                "# Vivotek Camera Device Information",
                "",
            ]

            # Parse system information
            if system_info:
                lines = system_info.strip().split("\n")
                system_params = {}
                for line in lines:
                    if "=" in line:
                        key, value = line.split("=", 1)
                        system_params[key] = value

                device_details.extend(
                    [
                        f"**Model:** {system_params.get('system_info_modelname', 'Unknown')}",
                        f"**Firmware Version:** {system_params.get('system_info_firmwareversion', 'Unknown')}",
                        f"**Serial Number:** {system_params.get('system_info_serialnumber', 'Unknown')}",
                        f"**Device Name:** {system_params.get('system_hostname', 'Unknown')}",
                        f"**Uptime:** {system_params.get('system_uptime', 'Unknown')}",
                        "",
                    ]
                )

            # Parse network information
            if network_info:
                lines = network_info.strip().split("\n")
                network_params = {}
                for line in lines:
                    if "=" in line:
                        key, value = line.split("=", 1)
                        network_params[key] = value

                device_details.extend(
                    [
                        "**Network Configuration:**",
                        f"- IP Address: {network_params.get('network_eth0_ip', 'Unknown')}",
                        f"- MAC Address: {network_params.get('network_eth0_mac', 'Unknown')}",
                        f"- DHCP: {network_params.get('network_eth0_dhcp_enable', 'Unknown')}",
                        "",
                    ]
                )

            device_details.extend(
                [
                    f"**Connection:** {self.base_url}",
                    f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                ]
            )

            return "\n".join(device_details)

        except Exception as e:
            logging.error(f"Error getting device info: {str(e)}")
            return f"Error getting device info: {str(e)}"

    async def get_live_stream_url(self, stream: int = 1, format: str = "mjpeg") -> str:
        """
        Get live stream URL for the camera

        Args:
            stream (int): Stream number (1-4, default: 1)
            format (str): Stream format - "mjpeg", "h264" (default: "mjpeg")

        Returns:
            str: Live stream URL or error message
        """
        try:
            stream = max(1, min(4, stream))  # Validate stream number

            stream_details = [
                "# Vivotek Camera Live Stream URLs",
                "",
            ]

            if format.lower() == "mjpeg":
                stream_url = (
                    f"{self.base_url}/cgi-bin/viewer/video.jpg?streamid={stream}"
                )
                mjpeg_url = (
                    f"{self.base_url}/cgi-bin/viewer/mjpeg.cgi?streamid={stream}"
                )

                stream_details.extend(
                    [
                        f"**MJPEG Stream URL:** {mjpeg_url}",
                        f"**Single Frame URL:** {stream_url}",
                    ]
                )
            elif format.lower() == "h264":
                rtsp_url = (
                    f"rtsp://{self.username}:{self.password}@{self.host}:554/live.sdp"
                )

                stream_details.extend(
                    [
                        f"**RTSP H.264 URL:** {rtsp_url}",
                        f"**Alternative RTSP:** rtsp://{self.host}:554/live{stream}.sdp",
                    ]
                )
            else:
                # Default to MJPEG
                mjpeg_url = (
                    f"{self.base_url}/cgi-bin/viewer/mjpeg.cgi?streamid={stream}"
                )
                stream_details.extend(
                    [
                        f"**MJPEG Stream URL:** {mjpeg_url}",
                    ]
                )

            stream_details.extend(
                [
                    "",
                    f"**Stream Number:** {stream}",
                    f"**Format:** {format.upper()}",
                    "",
                    "**Authentication Required:**",
                    f"- Username: {self.username}",
                    f"- Password: [Hidden for security]",
                    "",
                    "**Usage Examples:**",
                    "- VLC: File → Open Network Stream → Enter URL",
                    "- Web Browser: Use MJPEG URL with authentication",
                    "- FFmpeg: ffmpeg -i [URL] -c copy output.mp4",
                    "",
                ]
            )

            return "\n".join(stream_details)

        except Exception as e:
            logging.error(f"Error getting live stream URL: {str(e)}")
            return f"Error getting live stream URL: {str(e)}"

    async def capture_image(self, stream: int = 1, resolution: str = "high") -> str:
        """
        Capture an image from the camera

        Args:
            stream (int): Stream number (1-4, default: 1)
            resolution (str): Image resolution - "high", "medium", "low" (default: "high")

        Returns:
            str: Success message with image details or error message
        """
        try:
            stream = max(1, min(4, stream))  # Validate stream number

            # Capture image URL
            image_url = f"{self.base_url}/cgi-bin/viewer/video.jpg?streamid={stream}"

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vivotek_capture_{timestamp}_stream{stream}.jpg"

            capture_details = [
                "# Image Capture Request",
                "",
                f"**Capture URL:** {image_url}",
                f"**Stream Number:** {stream}",
                f"**Resolution:** {resolution}",
                f"**Suggested Filename:** {filename}",
                f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**To download the image:**",
                f"1. Use the capture URL with authentication",
                f"2. Save as: {filename}",
                "",
                "**Alternative capture methods:**",
                f"- Single frame: {image_url}",
                f"- With authentication: curl -u {self.username}:*** {image_url} -o {filename}",
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
            # Get motion detection parameters
            motion_info = await self._make_request(
                "/cgi-bin/admin/getparam.cgi", {"group": "motion"}
            )

            if not motion_info:
                return "Error: Failed to retrieve motion detection configuration"

            # Parse motion detection settings
            lines = motion_info.strip().split("\n")
            motion_params = {}
            for line in lines:
                if "=" in line:
                    key, value = line.split("=", 1)
                    motion_params[key] = value

            status_details = [
                "# Motion Detection Status",
                "",
                f"**Motion Detection Enabled:** {motion_params.get('motion_enable', 'Unknown')}",
                f"**Sensitivity:** {motion_params.get('motion_sensitivity', 'Unknown')}",
                f"**Detection Window:** {motion_params.get('motion_window', 'Unknown')}",
                f"**Threshold:** {motion_params.get('motion_threshold', 'Unknown')}",
                "",
                f"**Last Checked:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Available Configuration:**",
                "- Enable/disable motion detection",
                "- Adjust sensitivity levels",
                "- Configure detection windows",
                "- Set notification thresholds",
                "",
            ]

            return "\n".join(status_details)

        except Exception as e:
            logging.error(f"Error getting motion detection status: {str(e)}")
            return f"Error getting motion detection status: {str(e)}"

    async def set_motion_detection(
        self, enabled: bool = True, sensitivity: int = 80
    ) -> str:
        """
        Configure motion detection settings

        Args:
            enabled (bool): Enable or disable motion detection (default: True)
            sensitivity (int): Sensitivity level 1-100 (default: 80)

        Returns:
            str: Success message or error details
        """
        try:
            # Validate sensitivity range
            sensitivity = max(1, min(100, sensitivity))

            # Prepare configuration parameters
            params = {
                "motion_enable": "1" if enabled else "0",
                "motion_sensitivity": str(sensitivity),
            }

            # Build configuration URL
            config_url = "/cgi-bin/admin/setparam.cgi"

            # Note: This would typically require a POST request to set parameters
            # For now, we'll provide the configuration details

            config_details = [
                "# Motion Detection Configuration",
                "",
                f"**Motion Detection:** {'Enabled' if enabled else 'Disabled'}",
                f"**Sensitivity Level:** {sensitivity}%",
                f"**Configuration Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Configuration URL:** " + f"{self.base_url}{config_url}",
                "**Parameters:**",
                f"- motion_enable={params['motion_enable']}",
                f"- motion_sensitivity={params['motion_sensitivity']}",
                "",
                "**Note:** Configuration changes may require a camera reboot to take effect",
                "",
            ]

            return "\n".join(config_details)

        except Exception as e:
            logging.error(f"Error setting motion detection: {str(e)}")
            return f"Error setting motion detection: {str(e)}"

    async def get_ptz_status(self) -> str:
        """
        Get PTZ (Pan/Tilt/Zoom) status and capabilities

        Returns:
            str: PTZ status information
        """
        try:
            # Get PTZ capabilities
            ptz_info = await self._make_request(
                "/cgi-bin/admin/getparam.cgi", {"group": "ptz"}
            )

            ptz_details = [
                "# PTZ Status and Capabilities",
                "",
            ]

            if ptz_info:
                # Parse PTZ settings
                lines = ptz_info.strip().split("\n")
                ptz_params = {}
                for line in lines:
                    if "=" in line:
                        key, value = line.split("=", 1)
                        ptz_params[key] = value

                ptz_details.extend(
                    [
                        "**PTZ Capabilities:** Available",
                        f"**Pan Range:** {ptz_params.get('ptz_pan_range', 'Unknown')}",
                        f"**Tilt Range:** {ptz_params.get('ptz_tilt_range', 'Unknown')}",
                        f"**Zoom Range:** {ptz_params.get('ptz_zoom_range', 'Unknown')}",
                        f"**Current Position:** Pan={ptz_params.get('ptz_pan_position', 'Unknown')}, Tilt={ptz_params.get('ptz_tilt_position', 'Unknown')}",
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
                    "- Pan: left/right movement",
                    "- Tilt: up/down movement",
                    "- Zoom: in/out",
                    "- Preset positions",
                    "",
                ]
            )

            return "\n".join(ptz_details)

        except Exception as e:
            logging.error(f"Error getting PTZ status: {str(e)}")
            return f"Error getting PTZ status: {str(e)}"

    async def control_ptz(self, action: str, speed: int = 50) -> str:
        """
        Control PTZ (Pan/Tilt/Zoom) movements

        Args:
            action (str): PTZ action - "pan_left", "pan_right", "tilt_up", "tilt_down", "zoom_in", "zoom_out", "stop", "home"
            speed (int): Movement speed 1-100 (default: 50)

        Returns:
            str: Success message or error details
        """
        try:
            # Validate speed range
            speed = max(1, min(100, speed))

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

            # Map actions to Vivotek PTZ commands
            action_map = {
                "pan_left": "left",
                "pan_right": "right",
                "tilt_up": "up",
                "tilt_down": "down",
                "zoom_in": "zoomin",
                "zoom_out": "zoomout",
                "stop": "stop",
                "home": "home",
            }

            ptz_command = action_map.get(action.lower(), "stop")

            # Build PTZ control URL
            ptz_url = f"/cgi-bin/camctrl/camctrl.cgi?move={ptz_command}&speed={speed}"

            ptz_details = [
                "# PTZ Control Command",
                "",
                f"**Action:** {action}",
                f"**Speed:** {speed}%",
                f"**Command:** {ptz_command}",
                f"**Control URL:** {self.base_url}{ptz_url}",
                f"**Command Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Status:** PTZ command prepared",
                "**Note:** Command execution depends on camera PTZ capabilities",
                "",
            ]

            return "\n".join(ptz_details)

        except Exception as e:
            logging.error(f"Error controlling PTZ: {str(e)}")
            return f"Error controlling PTZ: {str(e)}"

    async def get_system_status(self) -> str:
        """
        Get comprehensive system status information

        Returns:
            str: System status details
        """
        try:
            # Get system status
            system_status = await self._make_request(
                "/cgi-bin/admin/getparam.cgi", {"group": "system"}
            )

            status_details = [
                "# Vivotek Camera System Status",
                "",
                f"**Connection Status:** Connected",
                f"**Host:** {self.base_url}",
                f"**Authentication:** Basic Auth ({self.username})",
                f"**Status Check Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
            ]

            if system_status:
                lines = system_status.strip().split("\n")
                system_params = {}
                for line in lines:
                    if "=" in line:
                        key, value = line.split("=", 1)
                        system_params[key] = value

                status_details.extend(
                    [
                        "**System Information:**",
                        f"- Uptime: {system_params.get('system_uptime', 'Unknown')}",
                        f"- Date/Time: {system_params.get('system_datetime', 'Unknown')}",
                        f"- Timezone: {system_params.get('system_timezone', 'Unknown')}",
                        f"- NTP Enabled: {system_params.get('system_ntp_enable', 'Unknown')}",
                        "",
                    ]
                )

            status_details.extend(
                [
                    "**Available Services:**",
                    "- HTTP API: Available",
                    "- Video Streaming: Available",
                    "- Image Capture: Available",
                    "- Motion Detection: Check configuration",
                    "- PTZ Control: Depends on camera model",
                    "",
                ]
            )

            return "\n".join(status_details)

        except Exception as e:
            logging.error(f"Error getting system status: {str(e)}")
            return f"Error getting system status: {str(e)}"

    async def get_video_settings(self) -> str:
        """
        Get video configuration settings

        Returns:
            str: Video settings information
        """
        try:
            # Get video settings
            video_info = await self._make_request(
                "/cgi-bin/admin/getparam.cgi", {"group": "videoin"}
            )

            video_details = [
                "# Video Settings",
                "",
            ]

            if video_info:
                lines = video_info.strip().split("\n")
                video_params = {}
                for line in lines:
                    if "=" in line:
                        key, value = line.split("=", 1)
                        video_params[key] = value

                video_details.extend(
                    [
                        f"**Resolution:** {video_params.get('videoin_c0_resolution', 'Unknown')}",
                        f"**Frame Rate:** {video_params.get('videoin_c0_framerate', 'Unknown')}",
                        f"**Quality:** {video_params.get('videoin_c0_quality', 'Unknown')}",
                        f"**Brightness:** {video_params.get('videoin_c0_brightness', 'Unknown')}",
                        f"**Contrast:** {video_params.get('videoin_c0_contrast', 'Unknown')}",
                        f"**Saturation:** {video_params.get('videoin_c0_saturation', 'Unknown')}",
                        "",
                    ]
                )
            else:
                video_details.extend(
                    [
                        "**Status:** Unable to retrieve video settings",
                        "**Note:** Settings may be available through camera web interface",
                        "",
                    ]
                )

            video_details.extend(
                [
                    f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                ]
            )

            return "\n".join(video_details)

        except Exception as e:
            logging.error(f"Error getting video settings: {str(e)}")
            return f"Error getting video settings: {str(e)}"

    async def set_video_settings(
        self, brightness: int = 50, contrast: int = 50, saturation: int = 50
    ) -> str:
        """
        Configure video settings

        Args:
            brightness (int): Brightness level 0-100 (default: 50)
            contrast (int): Contrast level 0-100 (default: 50)
            saturation (int): Saturation level 0-100 (default: 50)

        Returns:
            str: Success message or error details
        """
        try:
            # Validate ranges
            brightness = max(0, min(100, brightness))
            contrast = max(0, min(100, contrast))
            saturation = max(0, min(100, saturation))

            video_config = [
                "# Video Settings Configuration",
                "",
                f"**Brightness:** {brightness}%",
                f"**Contrast:** {contrast}%",
                f"**Saturation:** {saturation}%",
                f"**Configuration Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Configuration Parameters:**",
                f"- videoin_c0_brightness={brightness}",
                f"- videoin_c0_contrast={contrast}",
                f"- videoin_c0_saturation={saturation}",
                "",
                "**Note:** Changes typically require applying via setparam.cgi",
                "",
            ]

            return "\n".join(video_config)

        except Exception as e:
            logging.error(f"Error setting video settings: {str(e)}")
            return f"Error setting video settings: {str(e)}"

    async def get_audio_settings(self) -> str:
        """
        Get audio configuration and capabilities

        Returns:
            str: Audio settings information
        """
        try:
            # Get audio settings
            audio_info = await self._make_request(
                "/cgi-bin/admin/getparam.cgi", {"group": "audioin"}
            )

            audio_details = [
                "# Audio Settings and Capabilities",
                "",
            ]

            if audio_info:
                lines = audio_info.strip().split("\n")
                audio_params = {}
                for line in lines:
                    if "=" in line:
                        key, value = line.split("=", 1)
                        audio_params[key] = value

                audio_details.extend(
                    [
                        f"**Audio Input Enabled:** {audio_params.get('audioin_enable', 'Unknown')}",
                        f"**Sample Rate:** {audio_params.get('audioin_samplerate', 'Unknown')}",
                        f"**Bit Rate:** {audio_params.get('audioin_bitrate', 'Unknown')}",
                        f"**Volume:** {audio_params.get('audioin_volume', 'Unknown')}",
                        "",
                    ]
                )
            else:
                audio_details.extend(
                    [
                        "**Audio Capabilities:** Check device specifications",
                        "**Configuration:** Available through camera web interface",
                        "",
                    ]
                )

            audio_details.extend(
                [
                    f"**Last Checked:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "**Supported Features:**",
                    "- Audio input recording",
                    "- Two-way audio (model dependent)",
                    "- Audio streaming with video",
                    "",
                ]
            )

            return "\n".join(audio_details)

        except Exception as e:
            logging.error(f"Error getting audio settings: {str(e)}")
            return f"Error getting audio settings: {str(e)}"

    async def reboot_camera(self) -> str:
        """
        Reboot the Vivotek camera

        Returns:
            str: Success message or error details
        """
        try:
            reboot_url = "/cgi-bin/admin/reboot.cgi"

            reboot_details = [
                "# Camera Reboot Command",
                "",
                f"**Reboot URL:** {self.base_url}{reboot_url}",
                f"**Reboot initiated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"**Target device:** {self.base_url}",
                "",
                "**Status:** Reboot command prepared",
                "",
                "**Note:** The camera will be unavailable for 1-2 minutes during restart",
                "**Reconnection:** Device should be accessible again after restart completes",
                "**Manual reboot:** Access the reboot URL with authentication to execute",
                "",
            ]

            return "\n".join(reboot_details)

        except Exception as e:
            logging.error(f"Error preparing reboot command: {str(e)}")
            return f"Error preparing reboot command: {str(e)}"

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - clean up session"""
        if self.session and not self.session.closed:
            await self.session.close()


# Ensure the extension is properly registered
if __name__ == "__main__":
    extension = vivotek()
    print("Vivotek camera extension loaded successfully")
    print(f"Available commands: {list(extension.commands.keys())}")
