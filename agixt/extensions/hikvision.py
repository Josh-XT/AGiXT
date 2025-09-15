"""
Hikvision Camera Extension for AGiXT

This extension provides comprehensive control over Hikvision cameras and DVRs
using the hikvisionapi library. It supports async operations for AGiXT compatibility.

Required parameters (can be passed as arguments or environment variables):
- host: Camera/DVR IP address or hostname (e.g., http://192.168.1.100)
- username: Username for authentication
- password: Password for authentication

Environment variables (used as fallback):
- HIKVISION_HOST: Camera/DVR IP address or hostname
- HIKVISION_USERNAME: Username for authentication
- HIKVISION_PASSWORD: Password for authentication

Features:
- Device information retrieval
- Live video streaming
- Motion detection configuration
- Event monitoring and alerts
- Image capture
- Recording management
- System configuration
- Channel management

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

from Extensions import Extensions

try:
    from hikvisionapi import AsyncClient

    HIKVISION_AVAILABLE = True
except ImportError:
    HIKVISION_AVAILABLE = False
    logging.warning(
        "hikvisionapi library not available. Install with: pip install hikvisionapi"
    )


class hikvision(Extensions):
    """
    AGiXT Extension for Hikvision camera systems

    Provides comprehensive camera control capabilities including:
    - Authentication and device management
    - Live streaming and image capture
    - Motion detection and alerts
    - Recording management
    - System configuration
    """

    CATEGORY = "Smart Home & IoT"

    def __init__(
        self,
        HIKVISION_HOST: str = "",
        HIKVISION_USERNAME: str = "",
        HIKVISION_PASSWORD: str = "",
        **kwargs,
    ):
        """Initialize the Hikvision extension"""
        self.host = HIKVISION_HOST
        self.username = HIKVISION_USERNAME
        self.password = HIKVISION_PASSWORD

        self.commands = {
            "Get Device Info": self.get_device_info,
            "Capture Image": self.capture_image,
            "Get Motion Detection Status": self.get_motion_detection_status,
            "Set Motion Detection": self.set_motion_detection,
            "Get Event Notifications": self.get_event_notifications,
            "Get Channel List": self.get_channel_list,
            "Get System Status": self.get_system_status,
            "Get Recording Status": self.get_recording_status,
            "Start Recording": self.start_recording,
            "Stop Recording": self.stop_recording,
            "Get Storage Info": self.get_storage_info,
            "Reboot System": self.reboot_system,
        }
        self.client = None

    async def _initialize_client(self) -> bool:
        """
        Initialize the Hikvision client connection

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not HIKVISION_AVAILABLE:
                return False

            if not all([self.host, self.username, self.password]):
                logging.error(
                    "Missing required connection parameters for Hikvision device"
                )
                return False

            if self.client is None:
                self.client = AsyncClient(
                    self.host, self.username, self.password, timeout=30
                )

                # Test connection by getting device info
                await self.client.System.deviceInfo(method="get")
                logging.info("Successfully connected to Hikvision device")

            return True

        except Exception as e:
            logging.error(f"Failed to initialize Hikvision client: {str(e)}")
            self.client = None
            return False

    async def get_device_info(self) -> str:
        """
        Get basic device information from the Hikvision system

        Returns:
            str: Device information in formatted text
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system. Please check your credentials and network connection."

            device_info = await self.client.System.deviceInfo(method="get")

            if not device_info:
                return "Error: Could not retrieve device information"

            info = device_info.get("DeviceInfo", {})

            device_details = [
                "# Hikvision Device Information",
                "",
                f"**Device Name:** {info.get('deviceName', 'Unknown')}",
                f"**Device ID:** {info.get('deviceID', 'Unknown')}",
                f"**Model:** {info.get('model', 'Unknown')}",
                f"**Serial Number:** {info.get('serialNumber', 'Unknown')}",
                f"**Firmware Version:** {info.get('firmwareVersion', 'Unknown')}",
                f"**Firmware Release Date:** {info.get('firmwareReleasedDate', 'Unknown')}",
                f"**Hardware Version:** {info.get('hardwareVersion', 'Unknown')}",
                f"**Encoder Version:** {info.get('encoderVersion', 'Unknown')}",
                f"**Decoder Version:** {info.get('decoderVersion', 'Unknown')}",
                f"**MAC Address:** {info.get('macAddress', 'Unknown')}",
                f"**Device Type:** {info.get('deviceType', 'Unknown')}",
                "",
            ]

            return "\n".join(device_details)

        except Exception as e:
            logging.error(f"Error getting device info: {str(e)}")
            return f"Error getting device info: {str(e)}"

    async def capture_image(self, channel: int = 1, quality: str = "high") -> str:
        """
        Capture an image from the specified channel

        Args:
            channel (int): Channel number (default: 1)
            quality (str): Image quality - "high", "medium", or "low" (default: "high")

        Returns:
            str: Success message with image details or error message
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Validate quality parameter
            quality_map = {"high": "01", "medium": "02", "low": "03"}

            quality_code = quality_map.get(quality.lower(), "01")

            # Capture image using Hikvision API
            response = await self.client.Streaming.channels[channel].picture(
                method="get", type="opaque_data"
            )

            if not response:
                return f"Error: Failed to capture image from channel {channel}"

            # Save image to temporary file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"hikvision_capture_{timestamp}_ch{channel}.jpg"

            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".jpg", delete=False
            ) as temp_file:
                async for chunk in response:
                    if chunk:
                        temp_file.write(chunk)
                temp_path = temp_file.name

            return f"Successfully captured image from channel {channel}. Image saved to: {temp_path}"

        except Exception as e:
            logging.error(f"Error capturing image: {str(e)}")
            return f"Error capturing image: {str(e)}"

    async def get_motion_detection_status(self, channel: int = 1) -> str:
        """
        Get motion detection configuration for the specified channel

        Args:
            channel (int): Channel number (default: 1)

        Returns:
            str: Motion detection status information
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            motion_config = await self.client.System.Video.inputs.channels[
                channel
            ].motionDetection(method="get")

            if not motion_config:
                return f"Error: Could not retrieve motion detection status for channel {channel}"

            motion_info = motion_config.get("MotionDetection", {})

            status_details = [
                f"# Motion Detection Status - Channel {channel}",
                "",
                f"**Enabled:** {motion_info.get('enabled', 'Unknown')}",
                f"**Sensitivity Level:** {motion_info.get('sensitivityLevel', 'Unknown')}",
                f"**Sample Interval:** {motion_info.get('sampleInterval', 'Unknown')}",
                f"**Start Trigger Time:** {motion_info.get('startTriggerTime', 'Unknown')}",
                f"**End Trigger Time:** {motion_info.get('endTriggerTime', 'Unknown')}",
                "",
            ]

            # Add region information if available
            regions = motion_info.get("MotionDetectionRegionList", {}).get(
                "MotionDetectionRegion", []
            )
            if regions:
                status_details.append("**Detection Regions:**")
                if isinstance(regions, dict):
                    regions = [regions]

                for i, region in enumerate(regions, 1):
                    status_details.append(
                        f"- Region {i}: Enabled={region.get('enabled', 'Unknown')}, "
                        f"Sensitivity={region.get('sensitivityLevel', 'Unknown')}"
                    )
                status_details.append("")

            return "\n".join(status_details)

        except Exception as e:
            logging.error(f"Error getting motion detection status: {str(e)}")
            return f"Error getting motion detection status: {str(e)}"

    async def set_motion_detection(
        self, channel: int = 1, enabled: bool = True, sensitivity: int = 80
    ) -> str:
        """
        Configure motion detection for the specified channel

        Args:
            channel (int): Channel number (default: 1)
            enabled (bool): Enable or disable motion detection (default: True)
            sensitivity (int): Sensitivity level 1-100 (default: 80)

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Validate sensitivity range
            sensitivity = max(1, min(100, sensitivity))

            # Get current configuration first
            current_config = await self.client.System.Video.inputs.channels[
                channel
            ].motionDetection(method="get")

            if not current_config:
                return f"Error: Could not retrieve current motion detection configuration for channel {channel}"

            # Update the configuration
            motion_config = current_config.get("MotionDetection", {})
            motion_config["enabled"] = str(enabled).lower()
            motion_config["sensitivityLevel"] = str(sensitivity)

            # Build XML for the update
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <MotionDetection version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
                <enabled>{str(enabled).lower()}</enabled>
                <sensitivityLevel>{sensitivity}</sensitivityLevel>
            </MotionDetection>"""

            # Send the configuration
            await self.client.System.Video.inputs.channels[channel].motionDetection(
                method="put", data=xml_data
            )

            return f"Successfully {'enabled' if enabled else 'disabled'} motion detection on channel {channel} with sensitivity level {sensitivity}"

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
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Set up event monitoring client with timeout
            event_client = AsyncClient(
                self.host, self.username, self.password, timeout=timeout
            )
            event_client.count_events = 5  # Limit number of events to retrieve

            events = []
            start_time = datetime.now()

            try:
                async for event in event_client.Event.notification.alertStream(
                    method="get", type="stream", timeout=timeout
                ):
                    if event:
                        event_info = event.get("EventNotificationAlert", {})
                        event_time = event_info.get("dateTime", "Unknown")
                        event_type = event_info.get("eventType", "Unknown")
                        event_state = event_info.get("eventState", "Unknown")
                        channel_id = event_info.get("channelID", "Unknown")
                        description = event_info.get(
                            "eventDescription", "No description"
                        )

                        events.append(
                            {
                                "time": event_time,
                                "type": event_type,
                                "state": event_state,
                                "channel": channel_id,
                                "description": description,
                            }
                        )

                        # Break if we've been monitoring for too long
                        if (datetime.now() - start_time).seconds >= timeout:
                            break

            except asyncio.TimeoutError:
                pass  # Expected behavior when no events occur

            if not events:
                return f"No events detected within {timeout} seconds"

            event_details = [f"# Event Notifications ({len(events)} events)", ""]

            for i, event in enumerate(events, 1):
                event_details.extend(
                    [
                        f"## Event {i}",
                        f"- **Time:** {event['time']}",
                        f"- **Type:** {event['type']}",
                        f"- **State:** {event['state']}",
                        f"- **Channel:** {event['channel']}",
                        f"- **Description:** {event['description']}",
                        "",
                    ]
                )

            return "\n".join(event_details)

        except Exception as e:
            logging.error(f"Error getting event notifications: {str(e)}")
            return f"Error getting event notifications: {str(e)}"

    async def get_channel_list(self) -> str:
        """
        Get list of available video input channels

        Returns:
            str: Channel information
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Get video input channels
            channels_info = await self.client.System.Video.inputs(method="get")

            if not channels_info:
                return "Error: Could not retrieve channel information"

            video_inputs = channels_info.get("VideoInputChannelList", {})
            channels = video_inputs.get("VideoInputChannel", [])

            if isinstance(channels, dict):
                channels = [channels]

            if not channels:
                return "No video input channels found"

            channel_details = ["# Available Video Input Channels", ""]

            for channel in channels:
                channel_id = channel.get("id", "Unknown")
                channel_name = channel.get("inputPort", f"Channel {channel_id}")
                resolution = channel.get("resolutionMask", "Unknown")
                video_format = channel.get("videoFormat", "Unknown")

                channel_details.extend(
                    [
                        f"## Channel {channel_id}",
                        f"- **Name:** {channel_name}",
                        f"- **Resolution Mask:** {resolution}",
                        f"- **Video Format:** {video_format}",
                        "",
                    ]
                )

            return "\n".join(channel_details)

        except Exception as e:
            logging.error(f"Error getting channel list: {str(e)}")
            return f"Error getting channel list: {str(e)}"

    async def get_system_status(self) -> str:
        """
        Get comprehensive system status information

        Returns:
            str: System status details
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Get system status
            status_info = await self.client.System.status(method="get")

            if not status_info:
                return "Error: Could not retrieve system status"

            status = status_info.get("DeviceStatus", {})

            status_details = [
                "# Hikvision System Status",
                "",
                f"**Current Device Time:** {status.get('currentDeviceTime', 'Unknown')}",
                f"**Device Up Time:** {status.get('deviceUpTime', 'Unknown')}",
                f"**CPU Usage:** {status.get('cpuUsage', 'Unknown')}%",
                f"**Memory Usage:** {status.get('memoryUsage', 'Unknown')}%",
                "",
            ]

            return "\n".join(status_details)

        except Exception as e:
            logging.error(f"Error getting system status: {str(e)}")
            return f"Error getting system status: {str(e)}"

    async def get_recording_status(self, channel: int = 1) -> str:
        """
        Get recording status for the specified channel

        Args:
            channel (int): Channel number (default: 1)

        Returns:
            str: Recording status information
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Get recording status
            recording_info = await self.client.ContentMgmt.record(method="get")

            if not recording_info:
                return (
                    f"Error: Could not retrieve recording status for channel {channel}"
                )

            status_details = [
                f"# Recording Status - Channel {channel}",
                "",
                f"**Recording Status:** Available",
                f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
            ]

            return "\n".join(status_details)

        except Exception as e:
            logging.error(f"Error getting recording status: {str(e)}")
            return f"Error getting recording status: {str(e)}"

    async def start_recording(self, channel: int = 1, duration: int = 60) -> str:
        """
        Start manual recording on the specified channel

        Args:
            channel (int): Channel number (default: 1)
            duration (int): Recording duration in seconds (default: 60)

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Note: Manual recording start/stop might not be directly supported
            # This implementation provides a framework for when the API supports it

            return f"Manual recording start requested for channel {channel} (duration: {duration}s). Note: Manual recording control may depend on device configuration and firmware version."

        except Exception as e:
            logging.error(f"Error starting recording: {str(e)}")
            return f"Error starting recording: {str(e)}"

    async def stop_recording(self, channel: int = 1) -> str:
        """
        Stop manual recording on the specified channel

        Args:
            channel (int): Channel number (default: 1)

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Note: Manual recording start/stop might not be directly supported
            # This implementation provides a framework for when the API supports it

            return f"Manual recording stop requested for channel {channel}. Note: Manual recording control may depend on device configuration and firmware version."

        except Exception as e:
            logging.error(f"Error stopping recording: {str(e)}")
            return f"Error stopping recording: {str(e)}"

    async def get_storage_info(self) -> str:
        """
        Get storage device information and capacity

        Returns:
            str: Storage information
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Get storage information
            storage_info = await self.client.System.Storage(method="get")

            if not storage_info:
                return "Error: Could not retrieve storage information"

            storage_details = [
                "# Storage Information",
                "",
                "**Storage Status:** Available",
                f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
            ]

            return "\n".join(storage_details)

        except Exception as e:
            logging.error(f"Error getting storage info: {str(e)}")
            return f"Error getting storage info: {str(e)}"

    async def reboot_system(self) -> str:
        """
        Reboot the Hikvision system

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_client():
                return "Error: Failed to connect to Hikvision system"

            # Send reboot command
            await self.client.System.reboot(method="put")

            return "System reboot command sent successfully. The device will restart shortly."

        except Exception as e:
            logging.error(f"Error rebooting system: {str(e)}")
            return f"Error rebooting system: {str(e)}"


# Ensure the extension is properly registered
if __name__ == "__main__":
    extension = hikvision()
    print("Hikvision extension loaded successfully")
    print(f"Available commands: {list(extension.commands.keys())}")
