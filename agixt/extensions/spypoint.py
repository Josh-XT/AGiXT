import os
import requests
import logging
from datetime import datetime
from Extensions import Extensions


class spypoint(Extensions):
    """
    The SpyPoint extension for AGiXT enables you to interact with SpyPoint trail cameras.

    To get a SpyPoint account:
    1. Visit https://www.spypoint.com/
    2. Create an account or sign in
    3. Use your SpyPoint username and password in the extension settings
    """

    CATEGORY = "Smart Home & IoT"

    def __init__(
        self,
        SPYPOINT_USERNAME: str = "",
        SPYPOINT_PASSWORD: str = "",
        **kwargs,
    ):
        self.SPYPOINT_USERNAME = SPYPOINT_USERNAME
        self.SPYPOINT_PASSWORD = SPYPOINT_PASSWORD
        self.spypoint_uri = "https://restapi.spypoint.com"
        self.spypoint_token = None
        self.spypoint_uuid = None
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.commands = {
            "Get SpyPoint Camera Status": self.get_camera_status,
            "Get SpyPoint Photos": self.get_photos,
        }

    def _format_timestamp(self, iso_timestamp: str) -> str:
        """
        Convert ISO timestamp to readable format: 2025-11-10 2:42:46pm

        Args:
        iso_timestamp (str): ISO format timestamp like "2025-11-10T14:42:46.000Z"

        Returns:
        str: Formatted timestamp like "2025-11-10 2:42:46pm"
        """
        try:
            # Parse ISO timestamp
            dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))

            # Format as 12-hour time with am/pm
            hour = dt.hour
            am_pm = "am" if hour < 12 else "pm"
            hour_12 = hour % 12
            if hour_12 == 0:
                hour_12 = 12

            return f"{dt.year}-{dt.month:02d}-{dt.day:02d} {hour_12}:{dt.minute:02d}:{dt.second:02d}{am_pm}"
        except Exception as e:
            logging.warning(f"Error formatting timestamp {iso_timestamp}: {str(e)}")
            return iso_timestamp

    def _ensure_authenticated(self):
        """
        Ensure user is authenticated. Login if not already authenticated.
        """
        if self.spypoint_token:
            return

        try:
            login_url = f"{self.spypoint_uri}/api/v3/user/login"
            res = requests.post(
                login_url,
                headers={"accept": "application/json"},
                json={
                    "username": self.SPYPOINT_USERNAME,
                    "password": self.SPYPOINT_PASSWORD,
                },
            )
            res.raise_for_status()
            data = res.json()
            self.spypoint_token = data.get("token")
            self.spypoint_uuid = data.get("uuid")
        except Exception as e:
            logging.error(f"Error authenticating with SpyPoint API: {str(e)}")
            raise

    async def get_camera_status(self) -> str:
        """
        Get status overview of all SpyPoint cameras including battery, signal, memory, and photo counts.

        Returns:
        str: Summary of all camera statuses with key metrics

        Notes: This provides a quick overview of camera health without downloading photos.
        """
        self._ensure_authenticated()

        try:
            camera_url = f"{self.spypoint_uri}/api/v3/camera/all"
            res = requests.get(
                camera_url,
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {self.spypoint_token}",
                },
            )
            res.raise_for_status()
            cameras = res.json()

            # Build simple status summary
            status_lines = [f"Found {len(cameras)} camera(s):\n"]

            for camera in cameras:
                status = camera.get("status", {})
                config = camera.get("config", {})
                subscriptions = camera.get("subscriptions", [])

                name = config.get("name", "Unknown")
                camera_id = camera.get("id")

                # Get key metrics
                power_sources = status.get("powerSources", [])
                battery = power_sources[0].get("percentage", 0) if power_sources else 0
                temp = status.get("temperature", {})
                signal = status.get("signal", {}).get("processed", {})

                photo_count = 0
                photo_limit = 0
                if subscriptions:
                    photo_count = subscriptions[0].get("photoCount", 0)
                    photo_limit = subscriptions[0].get("photoLimit", 0)

                status_lines.append(
                    f"📷 {name} ({camera_id}):\n"
                    f"  Battery: {battery}% | Temp: {temp.get('value', 'N/A')}°{temp.get('unit', 'F')} | "
                    f"Signal: {signal.get('bar', 0)}/5 bars\n"
                    f"  Photos: {photo_count}/{photo_limit} this month\n"
                )

            return "\n".join(status_lines)
        except Exception as e:
            logging.error(f"Error getting camera status from SpyPoint API: {str(e)}")
            return f"Error getting camera status: {str(e)}"

    async def get_photos(
        self,
        limit: int = 10,
    ) -> str:
        """
        Get recent photos from all SpyPoint cameras and download them to the agent's workspace.

        Args:
        limit (int): Maximum number of photos to download (default: 10)

        Returns:
        str: Summary of downloaded photos with camera names, timestamps, and file paths

        Notes: Photos are automatically downloaded to the workspace and named as {camera_id}-{timestamp}.jpg
        """
        self._ensure_authenticated()

        try:
            # First get camera details for mapping IDs to names
            camera_url = f"{self.spypoint_uri}/api/v3/camera/all"
            res = requests.get(
                camera_url,
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {self.spypoint_token}",
                },
            )
            res.raise_for_status()
            cameras = res.json()

            # Build camera ID to name mapping and status summary
            camera_map = {}
            status_lines = [f"📷 Camera Status ({len(cameras)} camera(s)):\n"]

            for camera in cameras:
                camera_id = camera.get("id")
                camera_name = camera.get("config", {}).get("name", "Unknown")
                camera_map[camera_id] = camera_name

                # Get status info
                status = camera.get("status", {})
                config = camera.get("config", {})
                subscriptions = camera.get("subscriptions", [])

                power_sources = status.get("powerSources", [])
                battery = power_sources[0].get("percentage", 0) if power_sources else 0
                temp = status.get("temperature", {})
                signal = status.get("signal", {}).get("processed", {})

                photo_count = 0
                photo_limit = 0
                if subscriptions:
                    photo_count = subscriptions[0].get("photoCount", 0)
                    photo_limit = subscriptions[0].get("photoLimit", 0)

                status_lines.append(
                    f"  {camera_name} ({camera_id}): "
                    f"🔋 {battery}% | 🌡️ {temp.get('value', 'N/A')}°{temp.get('unit', 'F')} | "
                    f"📶 {signal.get('bar', 0)}/5 | "
                    f"📸 {photo_count}/{photo_limit}\n"
                )

            # Get photos
            photo_url = f"{self.spypoint_uri}/api/v3/photo/all"
            res = requests.post(
                photo_url,
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {self.spypoint_token}",
                },
                json={
                    "camera": [],
                    "dateEnd": "2100-01-01T00:00:00.000Z",
                    "favorite": False,
                    "hd": False,
                    "limit": limit,
                    "tag": [],
                },
            )
            res.raise_for_status()
            data = res.json()

            photos = data.get("photos", [])
            total_count = data.get("countPhotos", len(photos))

            if not photos:
                return "\n".join(status_lines) + "\nNo photos found."

            # Download photos and build summary
            summary_lines = status_lines + [
                f"\n📥 Downloaded {len(photos)} of {total_count} total photos:\n"
            ]

            for photo in photos:
                camera_id = photo.get("camera")
                camera_name = camera_map.get(camera_id, "Unknown")
                timestamp = photo.get("originDate", "unknown")
                formatted_time = self._format_timestamp(timestamp)
                photo_id = photo.get("id")

                # Log the photo structure for debugging
                logging.info(f"Processing photo {photo_id}: {list(photo.keys())}")

                # Try to get image URL - prefer large, fall back to medium or small
                photo_url = None
                size_used = None

                for size_name in ["large", "medium", "small"]:
                    size_data = photo.get(size_name, {})
                    if size_data and "host" in size_data and "path" in size_data:
                        photo_url = f"https://{size_data['host']}/{size_data['path']}"
                        size_used = size_name
                        break

                if not photo_url:
                    logging.warning(
                        f"Photo {photo_id} has no downloadable image URL. Available sizes: {[k for k in photo.keys() if k in ['small', 'medium', 'large']]}"
                    )
                    summary_lines.append(
                        f"⚠️  Photo from {camera_name} ({camera_id}) at {formatted_time} has no downloadable URL"
                    )
                    continue

                logging.info(f"Using {size_used} size image for photo {photo_id}")

                # Create filename: camera_id-timestamp.jpg
                # Clean timestamp for filename (remove special chars)
                clean_timestamp = (
                    timestamp.replace(":", "-")
                    .replace(".", "-")
                    .replace("T", "_")
                    .replace("Z", "")
                )
                filename = f"{camera_id}-{clean_timestamp}.jpg"
                filepath = os.path.join(self.WORKING_DIRECTORY, filename)

                # Ensure the directory exists
                os.makedirs(os.path.dirname(filepath), exist_ok=True)

                # Download the image
                try:
                    logging.info(f"Downloading photo from URL: {photo_url}")
                    img_response = requests.get(photo_url, timeout=30)
                    img_response.raise_for_status()

                    with open(filepath, "wb") as f:
                        f.write(img_response.content)

                    summary_lines.append(
                        f"📸 {camera_name} ({camera_id}) took picture `{filename}` at {formatted_time}"
                    )
                except Exception as e:
                    error_msg = str(e)
                    if hasattr(e, "response") and hasattr(e.response, "status_code"):
                        error_msg = f"HTTP {e.response.status_code}: {error_msg}"
                    logging.error(f"Error downloading photo {photo_id}: {error_msg}")
                    logging.error(f"Photo URL was: {photo_url}")
                    summary_lines.append(
                        f"⚠️  Failed to download photo from {camera_name} ({camera_id}) at {formatted_time}: {error_msg}"
                    )

            return "\n".join(summary_lines)
        except Exception as e:
            logging.error(f"Error getting photos from SpyPoint API: {str(e)}")
            return f"Error getting photos: {str(e)}"
