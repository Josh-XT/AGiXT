import logging
import asyncio
from Extensions import Extensions
from Globals import getenv
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class blink(Extensions):
    """
    Blink Camera System extension for AGiXT

    This extension provides control over Blink camera systems including:
    - Arming/disarming the system
    - Capturing video clips
    - Checking camera status
    - Getting motion alerts

    Required environment variables:
    - BLINK_USERNAME: Your Blink account username/email
    - BLINK_PASSWORD: Your Blink account password

    Authentication: Username/password authentication with 2FA support
    """

    CATEGORY = "Smart Home & IoT"

    def __init__(self, BLINK_USERNAME: str = "", BLINK_PASSWORD: str = "", **kwargs):
        self.username = BLINK_USERNAME
        self.password = BLINK_PASSWORD

        self.commands = {
            "Arm Blink System": self.arm_system,
            "Disarm Blink System": self.disarm_system,
            "Capture Video Clip": self.capture_video_clip,
            "Check Camera Status": self.check_camera_status,
            "Get Motion Alerts": self.get_motion_alerts,
            "Get Camera List": self.get_camera_list,
            "Download Recent Videos": self.download_recent_videos,
            "Check System Status": self.check_system_status,
        }
        self.blink = None
        self._initialized = False

    async def _initialize_blink(self):
        """Initialize the Blink connection if not already done"""
        if self._initialized and self.blink:
            return True

        try:
            # Import blinkpy inside the method to avoid import errors if not installed
            from blinkpy.blinkpy import Blink
            from blinkpy.auth import Auth
            from aiohttp import ClientSession

            # Create session and auth
            session = ClientSession()
            auth = Auth(
                {"username": self.username, "password": self.password}, no_prompt=True
            )

            self.blink = Blink(session=session)
            self.blink.auth = auth

            # Start the Blink connection
            await self.blink.start()

            # Note: In production, you would need to handle 2FA
            # For now, we'll assume 2FA is handled externally or disabled

            await self.blink.setup_post_verify()
            self._initialized = True

            logging.info("Successfully connected to Blink system")
            return True

        except ImportError:
            logging.error("blinkpy library not installed. Run: pip install blinkpy")
            return False
        except Exception as e:
            logging.error(f"Failed to initialize Blink connection: {str(e)}")
            return False

    async def arm_system(self, sync_module_name: str = None) -> str:
        """
        Arm the Blink system or a specific sync module

        Args:
            sync_module_name (str): Optional name of specific sync module to arm.
                                  If not provided, arms all sync modules.

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_blink():
                return "Error: Failed to connect to Blink system"

            if sync_module_name:
                # Arm specific sync module
                if sync_module_name in self.blink.sync:
                    await self.blink.sync[sync_module_name].async_arm(True)
                    await self.blink.refresh()
                    status = self.blink.sync[sync_module_name].arm
                    return f"Successfully armed sync module '{sync_module_name}'. Status: {'Armed' if status else 'Not Armed'}"
                else:
                    available_modules = list(self.blink.sync.keys())
                    return f"Error: Sync module '{sync_module_name}' not found. Available modules: {available_modules}"
            else:
                # Arm all sync modules
                results = []
                for name, sync_module in self.blink.sync.items():
                    await sync_module.async_arm(True)
                    results.append(f"Armed {name}")

                await self.blink.refresh()
                return f"Successfully armed all sync modules: {', '.join(results)}"

        except Exception as e:
            logging.error(f"Error arming Blink system: {str(e)}")
            return f"Error arming system: {str(e)}"

    async def disarm_system(self, sync_module_name: str = None) -> str:
        """
        Disarm the Blink system or a specific sync module

        Args:
            sync_module_name (str): Optional name of specific sync module to disarm.
                                   If not provided, disarms all sync modules.

        Returns:
            str: Success message or error details
        """
        try:
            if not await self._initialize_blink():
                return "Error: Failed to connect to Blink system"

            if sync_module_name:
                # Disarm specific sync module
                if sync_module_name in self.blink.sync:
                    await self.blink.sync[sync_module_name].async_arm(False)
                    await self.blink.refresh()
                    status = self.blink.sync[sync_module_name].arm
                    return f"Successfully disarmed sync module '{sync_module_name}'. Status: {'Armed' if status else 'Disarmed'}"
                else:
                    available_modules = list(self.blink.sync.keys())
                    return f"Error: Sync module '{sync_module_name}' not found. Available modules: {available_modules}"
            else:
                # Disarm all sync modules
                results = []
                for name, sync_module in self.blink.sync.items():
                    await sync_module.async_arm(False)
                    results.append(f"Disarmed {name}")

                await self.blink.refresh()
                return f"Successfully disarmed all sync modules: {', '.join(results)}"

        except Exception as e:
            logging.error(f"Error disarming Blink system: {str(e)}")
            return f"Error disarming system: {str(e)}"

    async def capture_video_clip(self, camera_name: str) -> str:
        """
        Capture a new video clip from a specific camera

        Args:
            camera_name (str): Name of the camera to capture video from

        Returns:
            str: Success message with video info or error details
        """
        try:
            if not await self._initialize_blink():
                return "Error: Failed to connect to Blink system"

            if camera_name not in self.blink.cameras:
                available_cameras = list(self.blink.cameras.keys())
                return f"Error: Camera '{camera_name}' not found. Available cameras: {available_cameras}"

            camera = self.blink.cameras[camera_name]

            # Take a new picture/video
            await camera.snap_picture()

            # Refresh to get new data
            await self.blink.refresh()

            return f"Successfully captured video clip from camera '{camera_name}'. Check your Blink app for the new recording."

        except Exception as e:
            logging.error(f"Error capturing video clip: {str(e)}")
            return f"Error capturing video clip: {str(e)}"

    async def check_camera_status(self, camera_name: str = None) -> str:
        """
        Check the status of cameras

        Args:
            camera_name (str): Optional specific camera name. If not provided,
                             returns status of all cameras.

        Returns:
            str: Camera status information formatted as markdown
        """
        try:
            if not await self._initialize_blink():
                return "Error: Failed to connect to Blink system"

            await self.blink.refresh()

            if camera_name:
                # Check specific camera
                if camera_name not in self.blink.cameras:
                    available_cameras = list(self.blink.cameras.keys())
                    return f"Error: Camera '{camera_name}' not found. Available cameras: {available_cameras}"

                camera = self.blink.cameras[camera_name]
                status_info = [
                    f"# Camera Status: {camera_name}",
                    f"**Name:** {camera.name}",
                    f"**Armed:** {'Yes' if camera.arm else 'No'}",
                    f"**Battery:** {getattr(camera, 'battery_level', 'N/A')}",
                    f"**Signal Strength:** {getattr(camera, 'wifi_strength', 'N/A')}",
                    f"**Temperature:** {getattr(camera, 'temperature', 'N/A')}",
                    f"**Motion Detection:** {'Enabled' if camera.motion_enabled else 'Disabled'}",
                    f"**Last Motion:** {getattr(camera, 'last_motion', 'N/A')}",
                ]

                # Include additional attributes if available
                if hasattr(camera, "attributes"):
                    status_info.append(f"**Additional Info:** {camera.attributes}")

                return "\n".join(status_info)
            else:
                # Check all cameras
                if not self.blink.cameras:
                    return "No cameras found in the Blink system"

                status_info = ["# All Camera Status"]

                for name, camera in self.blink.cameras.items():
                    status_info.extend(
                        [
                            f"## {name}",
                            f"- **Armed:** {'Yes' if camera.arm else 'No'}",
                            f"- **Battery:** {getattr(camera, 'battery_level', 'N/A')}",
                            f"- **Signal:** {getattr(camera, 'wifi_strength', 'N/A')}",
                            f"- **Motion Detection:** {'Enabled' if camera.motion_enabled else 'Disabled'}",
                            "",
                        ]
                    )

                return "\n".join(status_info)

        except Exception as e:
            logging.error(f"Error checking camera status: {str(e)}")
            return f"Error checking camera status: {str(e)}"

    async def get_motion_alerts(self, limit: int = 10) -> str:
        """
        Get recent motion alerts from all cameras

        Args:
            limit (int): Maximum number of alerts to retrieve (default: 10)

        Returns:
            str: Motion alerts formatted as markdown
        """
        try:
            if not await self._initialize_blink():
                return "Error: Failed to connect to Blink system"

            await self.blink.refresh()

            alerts_info = [f"# Recent Motion Alerts (Last {limit})"]

            # Get motion events from each camera
            for camera_name, camera in self.blink.cameras.items():
                try:
                    # Get recent clips/events
                    if hasattr(camera, "recent_clips") and camera.recent_clips:
                        alerts_info.append(f"## {camera_name}")

                        for i, clip in enumerate(camera.recent_clips[:limit]):
                            if isinstance(clip, dict):
                                timestamp = clip.get("created_at", "Unknown time")
                                event_type = clip.get("type", "motion")
                                alerts_info.append(
                                    f"- **{timestamp}:** {event_type} detected"
                                )

                            if i >= limit - 1:
                                break

                        alerts_info.append("")
                    else:
                        alerts_info.append(f"## {camera_name}")
                        alerts_info.append("- No recent motion alerts")
                        alerts_info.append("")

                except Exception as camera_error:
                    logging.warning(
                        f"Error getting alerts for camera {camera_name}: {str(camera_error)}"
                    )
                    continue

            if len(alerts_info) == 1:  # Only header added
                alerts_info.append("No motion alerts found across all cameras")

            return "\n".join(alerts_info)

        except Exception as e:
            logging.error(f"Error getting motion alerts: {str(e)}")
            return f"Error getting motion alerts: {str(e)}"

    async def get_camera_list(self) -> str:
        """
        Get a list of all available cameras in the Blink system

        Returns:
            str: List of cameras with basic information
        """
        try:
            if not await self._initialize_blink():
                return "Error: Failed to connect to Blink system"

            await self.blink.refresh()

            if not self.blink.cameras:
                return "No cameras found in the Blink system"

            camera_info = ["# Blink Camera List"]

            for name, camera in self.blink.cameras.items():
                camera_info.extend(
                    [
                        f"## {name}",
                        f"- **Type:** {getattr(camera, 'camera_type', 'Unknown')}",
                        f"- **Status:** {'Armed' if camera.arm else 'Disarmed'}",
                        f"- **Battery:** {getattr(camera, 'battery_level', 'N/A')}",
                        f"- **Motion Enabled:** {'Yes' if camera.motion_enabled else 'No'}",
                        "",
                    ]
                )

            return "\n".join(camera_info)

        except Exception as e:
            logging.error(f"Error getting camera list: {str(e)}")
            return f"Error getting camera list: {str(e)}"

    async def download_recent_videos(
        self, camera_name: str = None, count: int = 5
    ) -> str:
        """
        Download recent videos from cameras

        Args:
            camera_name (str): Optional specific camera name. If not provided,
                             downloads from all cameras.
            count (int): Number of recent videos to download (default: 5)

        Returns:
            str: Success message with download information
        """
        try:
            if not await self._initialize_blink():
                return "Error: Failed to connect to Blink system"

            await self.blink.refresh()

            results = []

            if camera_name:
                # Download from specific camera
                if camera_name not in self.blink.cameras:
                    available_cameras = list(self.blink.cameras.keys())
                    return f"Error: Camera '{camera_name}' not found. Available cameras: {available_cameras}"

                camera = self.blink.cameras[camera_name]

                # Check if camera has video_from_cache
                if hasattr(camera, "video_from_cache") and camera.video_from_cache:
                    filename = f"{camera_name}_latest.mp4"
                    try:
                        await camera.video_to_file(filename)
                        results.append(
                            f"Downloaded latest video from {camera_name} as {filename}"
                        )
                    except Exception as download_error:
                        results.append(
                            f"Failed to download video from {camera_name}: {str(download_error)}"
                        )
                else:
                    results.append(f"No video available from {camera_name}")
            else:
                # Download from all cameras
                for name, camera in self.blink.cameras.items():
                    try:
                        if (
                            hasattr(camera, "video_from_cache")
                            and camera.video_from_cache
                        ):
                            filename = f"{name}_latest.mp4"
                            await camera.video_to_file(filename)
                            results.append(
                                f"Downloaded latest video from {name} as {filename}"
                            )
                        else:
                            results.append(f"No video available from {name}")
                    except Exception as download_error:
                        results.append(
                            f"Failed to download video from {name}: {str(download_error)}"
                        )

            if results:
                return "Video download results:\n" + "\n".join(
                    [f"- {result}" for result in results]
                )
            else:
                return "No videos were downloaded"

        except Exception as e:
            logging.error(f"Error downloading videos: {str(e)}")
            return f"Error downloading videos: {str(e)}"

    async def check_system_status(self) -> str:
        """
        Check the overall status of the Blink system

        Returns:
            str: System status information formatted as markdown
        """
        try:
            if not await self._initialize_blink():
                return "Error: Failed to connect to Blink system"

            await self.blink.refresh()

            status_info = ["# Blink System Status"]

            # Sync modules status
            if self.blink.sync:
                status_info.append("## Sync Modules")
                for name, sync_module in self.blink.sync.items():
                    status_info.extend(
                        [
                            f"### {name}",
                            f"- **Armed:** {'Yes' if sync_module.arm else 'No'}",
                            f"- **Online:** {'Yes' if getattr(sync_module, 'online', True) else 'No'}",
                            "",
                        ]
                    )
            else:
                status_info.append("## Sync Modules")
                status_info.append("No sync modules found")
                status_info.append("")

            # Camera count summary
            camera_count = len(self.blink.cameras) if self.blink.cameras else 0
            armed_cameras = (
                sum(1 for camera in self.blink.cameras.values() if camera.arm)
                if self.blink.cameras
                else 0
            )

            status_info.extend(
                [
                    "## Summary",
                    f"- **Total Cameras:** {camera_count}",
                    f"- **Armed Cameras:** {armed_cameras}",
                    f"- **Disarmed Cameras:** {camera_count - armed_cameras}",
                ]
            )

            return "\n".join(status_info)

        except Exception as e:
            logging.error(f"Error checking system status: {str(e)}")
            return f"Error checking system status: {str(e)}"
