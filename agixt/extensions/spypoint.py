import requests
import logging
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
        self.commands = {
            "Get SpyPoint Cameras": self.get_cameras,
            "Get SpyPoint Photos": self.get_photos,
        }

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

    async def get_cameras(self) -> str:
        """
        Get all cameras associated with the account.

        Returns:
        str: JSON string of simplified camera list with essential status and usage data
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

            # Process cameras to extract only relevant information
            processed_cameras = []

            for camera in cameras:
                status = camera.get("status", {})
                config = camera.get("config", {})

                # Get subscription info for photo counts
                subscriptions = camera.get("subscriptions", [])
                photo_count = 0
                photo_limit = 0
                plan_name = "Unknown"

                if subscriptions:
                    sub = subscriptions[0]
                    photo_count = sub.get("photoCount", 0)
                    photo_limit = sub.get("photoLimit", 0)
                    plan_name = sub.get("plan", {}).get("name", "Unknown")

                # Get battery percentage (use first active power source)
                power_sources = status.get("powerSources", [])
                battery_percentage = 0
                battery_voltage = 0
                if power_sources:
                    battery_percentage = power_sources[0].get("percentage", 0)
                    battery_voltage = power_sources[0].get("voltage", 0)

                # Get signal strength
                signal = status.get("signal", {}).get("processed", {})

                # Get memory usage
                memory = status.get("memory", {})
                memory_used_percent = 0
                if memory.get("size", 0) > 0:
                    memory_used_percent = round(
                        (memory.get("used", 0) / memory.get("size", 1)) * 100, 2
                    )

                camera_data = {
                    "id": camera.get("id"),
                    "name": config.get("name", "Unknown"),
                    "model": status.get("model"),
                    "data_matrix_key": camera.get("dataMatrixKey"),
                    "activation_date": camera.get("activationDate"),
                    "location": {
                        "gps_enabled": config.get("gps", False),
                    },
                    "status": {
                        "battery_percent": battery_percentage,
                        "battery_voltage": battery_voltage,
                        "battery_type": status.get("batteryType"),
                        "temperature": status.get("temperature", {}),
                        "signal_bars": signal.get("bar", 0),
                        "signal_percent": signal.get("percentage", 0),
                        "low_signal": signal.get("lowSignal", False),
                        "last_update": status.get("lastUpdate"),
                        "install_date": status.get("installDate"),
                    },
                    "memory": {
                        "size_mb": memory.get("size", 0),
                        "used_mb": memory.get("used", 0),
                        "used_percent": memory_used_percent,
                    },
                    "photos": {
                        "count_this_month": photo_count,
                        "limit": photo_limit,
                        "plan": plan_name,
                        "hd_since": camera.get("hdSince"),
                    },
                    "settings": {
                        "motion_delay": config.get("motionDelay"),
                        "sensitivity_level": config.get("sensibility", {}).get("level"),
                        "operation_mode": config.get("operationMode"),
                        "multi_shot": config.get("multiShot"),
                    },
                    "firmware": {
                        "version": status.get("version"),
                        "modem_firmware": status.get("modemFirmware"),
                    },
                }

                processed_cameras.append(camera_data)

            result = {"count": len(processed_cameras), "cameras": processed_cameras}
            return str(result)
        except Exception as e:
            logging.error(f"Error getting cameras from SpyPoint API: {str(e)}")
            return f"Error getting cameras: {str(e)}"

    async def get_photos(
        self,
        date_end: str = "2100-01-01T00:00:00.000Z",
        limit: int = 100,
    ) -> str:
        """
        Get photos from specified cameras.

        Args:
        date_end (str): End date for photo search in ISO format (default: 2100-01-01T00:00:00.000Z)
        limit (int): Maximum number of photos to return (default: 100)

        Returns:
        str: JSON string containing simplified photo data with URL, camera ID, timestamp, and total count
        """
        if date_end == "None":
            date_end = "2100-01-01T00:00:00.000Z"
        self._ensure_authenticated()
        size = "large"

        try:

            photo_url = f"{self.spypoint_uri}/api/v3/photo/all"
            res = requests.post(
                photo_url,
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {self.spypoint_token}",
                },
                json={
                    "camera": [],
                    "dateEnd": date_end,
                    "favorite": False,
                    "hd": False,
                    "limit": limit,
                    "tag": [],
                },
            )
            res.raise_for_status()
            data = res.json()

            # Process photos to construct URLs and simplify data
            photos = data.get("photos", [])
            processed_photos = []

            for photo in photos:
                photo_data = {
                    "id": photo.get("id"),
                    "camera_id": photo.get("camera"),
                    "timestamp": photo.get("originDate"),
                }

                # Construct full URL like the spypoint library does
                size_data = photo.get(size, {})
                if size_data and "host" in size_data and "path" in size_data:
                    photo_data["url"] = (
                        f"https://{size_data['host']}/{size_data['path']}"
                    )

                processed_photos.append(photo_data)

            result = {
                "count": data.get("countPhotos", len(processed_photos)),
                "photos": processed_photos,
            }
            return str(result)
        except Exception as e:
            logging.error(f"Error getting photos from SpyPoint API: {str(e)}")
            return f"Error getting photos: {str(e)}"
