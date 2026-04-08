import logging
import json
from Extensions import Extensions
from Globals import getenv

try:
    import tinytuya
except ImportError:
    tinytuya = None

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Tuya Smart Home Extension for AGiXT

This extension enables interaction with Tuya-compatible smart home devices through
the Tuya Cloud API via the TinyTuya library. It supports controlling a wide range
of devices including bulbs, switches, plugs, sensors, thermostats, cameras,
light strips, vacuum cleaners, doorbells, and more.

Required configuration:

- TUYA_API_KEY: Your Tuya IoT Platform Access ID / Client ID
- TUYA_API_SECRET: Your Tuya IoT Platform Access Secret / Client Secret
- TUYA_API_REGION: The Tuya data center region (us, eu, eu-w, cn, in, sg, us-e)
- TUYA_DEVICE_ID: Any one of your Tuya device IDs (used for initial cloud connection)

How to get your Tuya API credentials:

1. Download the Tuya Smart or Smart Life app and pair your devices
2. Create a Tuya Developer account at https://iot.tuya.com/
3. Click "Cloud" -> "Create Cloud Project"
4. Select your data center region and note the API Key and Secret
5. Under "Service API", subscribe to "IoT Core" and "Authorization"
6. Link your Tuya app account by scanning the QR code under Devices -> Link Tuya App Account
7. Use any Device ID from your linked devices for TUYA_DEVICE_ID
"""


class tuya(Extensions):
    """
    The Tuya Smart Home extension for AGiXT enables smart home device control
    through the Tuya Cloud API. It supports a wide range of Tuya-compatible
    WiFi smart devices including bulbs, switches, plugs, sensors, thermostats,
    cameras, light strips, covers, vacuum cleaners, doorbells, and more.

    Requires a Tuya IoT Platform developer account with API credentials.

    To set up:
    1. Create a Tuya IoT developer account at https://iot.tuya.com/
    2. Create a Cloud Project and subscribe to IoT Core API
    3. Link your Tuya Smart / Smart Life app account
    4. Set TUYA_API_KEY, TUYA_API_SECRET, TUYA_API_REGION, and TUYA_DEVICE_ID
    """

    CATEGORY = "Smart Home & IoT"
    friendly_name = "Tuya Smart Home"

    def __init__(
        self,
        TUYA_API_KEY: str = "",
        TUYA_API_SECRET: str = "",
        TUYA_API_REGION: str = "us",
        TUYA_DEVICE_ID: str = "",
        **kwargs,
    ):
        self.api_key = TUYA_API_KEY
        self.api_secret = TUYA_API_SECRET
        self.api_region = TUYA_API_REGION or "us"
        self.device_id = TUYA_DEVICE_ID
        self.commands = {}
        self._cloud = None
        self._devices_cache = None

        if tinytuya and self.api_key and self.api_secret and self.device_id:
            self.commands = {
                "Tuya - List Devices": self.list_devices,
                "Tuya - Get Device Status": self.get_device_status,
                "Tuya - Turn On Device": self.turn_on_device,
                "Tuya - Turn Off Device": self.turn_off_device,
                "Tuya - Set Device Value": self.set_device_value,
                "Tuya - Send Device Command": self.send_device_command,
                "Tuya - Get Device Properties": self.get_device_properties,
                "Tuya - Get Device Functions": self.get_device_functions,
                "Tuya - Set Light Color": self.set_light_color,
                "Tuya - Set Light Brightness": self.set_light_brightness,
                "Tuya - Set Thermostat Temperature": self.set_thermostat_temperature,
                "Tuya - Get Device Logs": self.get_device_logs,
            }

    def _get_cloud(self):
        """Get or create the TinyTuya Cloud connection."""
        if self._cloud is None:
            self._cloud = tinytuya.Cloud(
                apiRegion=self.api_region,
                apiKey=self.api_key,
                apiSecret=self.api_secret,
                apiDeviceID=self.device_id,
            )
        return self._cloud

    def _find_device_id(self, device_identifier: str) -> str:
        """
        Resolve a device name or ID to an actual device ID.
        If the identifier matches a known device name, returns its ID.
        Otherwise assumes it's already a device ID.
        """
        if not self._devices_cache:
            try:
                cloud = self._get_cloud()
                self._devices_cache = cloud.getdevices()
            except Exception:
                return device_identifier

        if isinstance(self._devices_cache, list):
            for device in self._devices_cache:
                if isinstance(device, dict):
                    name = device.get("name", "")
                    if name and name.lower() == device_identifier.lower():
                        return device.get("id", device_identifier)
        return device_identifier

    def _format_device(self, device: dict) -> str:
        """Format a device dict into readable text."""
        name = device.get("name", "Unknown")
        dev_id = device.get("id", "N/A")
        category = device.get("category", "N/A")
        online = device.get("online", False)
        product_name = device.get("product_name", "N/A")
        status = "Online" if online else "Offline"
        return f"- **{name}** (ID: `{dev_id}`): {product_name} [{category}] - {status}"

    def _format_status(self, status_list) -> str:
        """Format device status data points into readable text."""
        if not status_list:
            return "No status data available."
        if isinstance(status_list, dict) and "result" in status_list:
            status_list = status_list["result"]
        if not isinstance(status_list, list):
            return f"Status: {status_list}"
        lines = []
        for item in status_list:
            if isinstance(item, dict):
                code = item.get("code", "unknown")
                value = item.get("value", "N/A")
                lines.append(f"- **{code}**: {value}")
            else:
                lines.append(f"- {item}")
        return "\n".join(lines) if lines else "No status data available."

    async def list_devices(self):
        """
        List all Tuya devices registered to your account.

        Returns:
            str: Formatted list of all devices with their names, IDs, categories, and online status.
        """
        try:
            cloud = self._get_cloud()
            devices = cloud.getdevices()
            self._devices_cache = devices

            if not devices or (isinstance(devices, dict) and "Error" in devices):
                error_msg = (
                    devices.get("Error", "Unknown error")
                    if isinstance(devices, dict)
                    else "No devices found"
                )
                return f"Error listing devices: {error_msg}"

            if not isinstance(devices, list) or len(devices) == 0:
                return "No devices found on your Tuya account."

            # Group by category
            grouped = {}
            for device in devices:
                if isinstance(device, dict):
                    cat = device.get("category", "other")
                    if cat not in grouped:
                        grouped[cat] = []
                    grouped[cat].append(device)

            result = f"**Tuya Devices ({len(devices)} total):**\n\n"
            for cat in sorted(grouped.keys()):
                result += f"### {cat}\n"
                for device in sorted(grouped[cat], key=lambda d: d.get("name", "")):
                    result += f"{self._format_device(device)}\n"
                result += "\n"

            return result
        except Exception as e:
            return f"Error listing devices: {str(e)}"

    async def get_device_status(self, device: str):
        """
        Get the current status of a Tuya device.

        Args:
            device (str): The device name or device ID to query.

        Returns:
            str: Formatted device status with all data points.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)
            result = cloud.getstatus(device_id)

            if isinstance(result, dict) and "Error" in result:
                return f"Error getting status for '{device}': {result.get('Error')}"

            status_data = result
            if isinstance(result, dict) and "result" in result:
                status_data = result["result"]

            formatted = self._format_status(status_data)
            return f"**Status for '{device}' (ID: {device_id}):**\n\n{formatted}"
        except Exception as e:
            return f"Error getting device status: {str(e)}"

    async def turn_on_device(self, device: str, switch_number: int = 1):
        """
        Turn on a Tuya device or a specific switch on the device.

        Args:
            device (str): The device name or device ID to turn on.
            switch_number (int, optional): The switch number for multi-switch devices. Defaults to 1.

        Returns:
            str: Confirmation message or error.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)
            code = f"switch_{switch_number}" if switch_number > 1 else "switch_1"
            commands = {"commands": [{"code": code, "value": True}]}
            result = cloud.sendcommand(device_id, commands)

            if isinstance(result, dict) and "Error" in result:
                # Try alternate command code "switch" without number
                commands = {"commands": [{"code": "switch", "value": True}]}
                result = cloud.sendcommand(device_id, commands)
                if isinstance(result, dict) and "Error" in result:
                    return f"Error turning on '{device}': {result.get('Error')}"

            return f"Successfully turned on '{device}' (switch {switch_number})."
        except Exception as e:
            return f"Error turning on device: {str(e)}"

    async def turn_off_device(self, device: str, switch_number: int = 1):
        """
        Turn off a Tuya device or a specific switch on the device.

        Args:
            device (str): The device name or device ID to turn off.
            switch_number (int, optional): The switch number for multi-switch devices. Defaults to 1.

        Returns:
            str: Confirmation message or error.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)
            code = f"switch_{switch_number}" if switch_number > 1 else "switch_1"
            commands = {"commands": [{"code": code, "value": False}]}
            result = cloud.sendcommand(device_id, commands)

            if isinstance(result, dict) and "Error" in result:
                commands = {"commands": [{"code": "switch", "value": False}]}
                result = cloud.sendcommand(device_id, commands)
                if isinstance(result, dict) and "Error" in result:
                    return f"Error turning off '{device}': {result.get('Error')}"

            return f"Successfully turned off '{device}' (switch {switch_number})."
        except Exception as e:
            return f"Error turning off device: {str(e)}"

    async def set_device_value(self, device: str, code: str, value: str):
        """
        Set a specific data point value on a Tuya device.

        Args:
            device (str): The device name or device ID.
            code (str): The data point code to set (e.g., 'switch_1', 'bright_value', 'temp_set').
            value (str): The value to set. Will be auto-converted to bool/int if applicable.

        Returns:
            str: Confirmation message or error.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)

            # Auto-convert value types
            parsed_value = value
            if value.lower() in ("true", "false"):
                parsed_value = value.lower() == "true"
            else:
                try:
                    parsed_value = int(value)
                except ValueError:
                    try:
                        parsed_value = float(value)
                    except ValueError:
                        pass

            commands = {"commands": [{"code": code, "value": parsed_value}]}
            result = cloud.sendcommand(device_id, commands)

            if isinstance(result, dict) and "Error" in result:
                return (
                    f"Error setting {code}={value} on '{device}': {result.get('Error')}"
                )

            return f"Successfully set '{code}' to '{value}' on '{device}'."
        except Exception as e:
            return f"Error setting device value: {str(e)}"

    async def send_device_command(self, device: str, commands_json: str):
        """
        Send a raw command payload to a Tuya device. Useful for advanced control
        when you know the exact command codes and values.

        Args:
            device (str): The device name or device ID.
            commands_json (str): JSON string of commands, e.g. '[{"code": "switch_1", "value": true}]'

        Returns:
            str: Confirmation message or error.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)

            try:
                cmd_list = json.loads(commands_json)
            except json.JSONDecodeError:
                return 'Error: Invalid JSON in commands_json. Expected format: \'[{"code": "switch_1", "value": true}]\''

            if isinstance(cmd_list, list):
                commands = {"commands": cmd_list}
            elif isinstance(cmd_list, dict) and "commands" in cmd_list:
                commands = cmd_list
            else:
                return "Error: commands_json must be a JSON array of command objects or a dict with 'commands' key."

            result = cloud.sendcommand(device_id, commands)

            if isinstance(result, dict) and "Error" in result:
                return f"Error sending command to '{device}': {result.get('Error')}"

            return f"Successfully sent commands to '{device}'."
        except Exception as e:
            return f"Error sending device command: {str(e)}"

    async def get_device_properties(self, device: str):
        """
        Get the properties/specifications of a Tuya device, showing what
        data points it supports and their value ranges.

        Args:
            device (str): The device name or device ID.

        Returns:
            str: Formatted device properties or error message.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)
            result = cloud.getproperties(device_id)

            if isinstance(result, dict) and "Error" in result:
                return f"Error getting properties for '{device}': {result.get('Error')}"

            props = result
            if isinstance(result, dict) and "result" in result:
                props = result["result"]

            if isinstance(props, dict) and "properties" in props:
                prop_list = props["properties"]
                if not prop_list:
                    return f"No properties found for '{device}'."

                lines = [f"**Properties for '{device}' (ID: {device_id}):**\n"]
                for prop in prop_list:
                    if isinstance(prop, dict):
                        code = prop.get("code", "unknown")
                        dp_id = prop.get("dp_id", "N/A")
                        ptype = prop.get("type", "N/A")
                        values = prop.get("value", "")
                        lines.append(
                            f"- **{code}** (DP {dp_id}): type={ptype}, values={values}"
                        )
                return "\n".join(lines)

            return f"Properties for '{device}':\n```json\n{json.dumps(props, indent=2)}\n```"
        except Exception as e:
            return f"Error getting device properties: {str(e)}"

    async def get_device_functions(self, device: str):
        """
        Get the available control functions for a Tuya device, showing what
        commands can be sent and their allowed values.

        Args:
            device (str): The device name or device ID.

        Returns:
            str: Formatted device functions or error message.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)
            result = cloud.getfunctions(device_id)

            if isinstance(result, dict) and "Error" in result:
                return f"Error getting functions for '{device}': {result.get('Error')}"

            funcs = result
            if isinstance(result, dict) and "result" in result:
                funcs = result["result"]

            if isinstance(funcs, dict) and "functions" in funcs:
                func_list = funcs["functions"]
                if not func_list:
                    return f"No control functions found for '{device}'."

                lines = [f"**Control Functions for '{device}' (ID: {device_id}):**\n"]
                for func in func_list:
                    if isinstance(func, dict):
                        code = func.get("code", "unknown")
                        fname = func.get("name", code)
                        ftype = func.get("type", "N/A")
                        values = func.get("values", "")
                        lines.append(
                            f"- **{fname}** (`{code}`): type={ftype}, values={values}"
                        )
                return "\n".join(lines)

            return f"Functions for '{device}':\n```json\n{json.dumps(funcs, indent=2)}\n```"
        except Exception as e:
            return f"Error getting device functions: {str(e)}"

    async def set_light_color(
        self, device: str, r: int = 255, g: int = 255, b: int = 255
    ):
        """
        Set the color of a Tuya smart light/bulb using RGB values.

        Args:
            device (str): The device name or device ID of the light.
            r (int): Red value (0-255). Defaults to 255.
            g (int): Green value (0-255). Defaults to 255.
            b (int): Blue value (0-255). Defaults to 255.

        Returns:
            str: Confirmation message or error.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)

            r = max(0, min(255, int(r)))
            g = max(0, min(255, int(g)))
            b = max(0, min(255, int(b)))

            # Convert RGB to HSV for Tuya format
            r_norm, g_norm, b_norm = r / 255.0, g / 255.0, b / 255.0
            max_c = max(r_norm, g_norm, b_norm)
            min_c = min(r_norm, g_norm, b_norm)
            diff = max_c - min_c

            if diff == 0:
                h = 0
            elif max_c == r_norm:
                h = (60 * ((g_norm - b_norm) / diff) + 360) % 360
            elif max_c == g_norm:
                h = (60 * ((b_norm - r_norm) / diff) + 120) % 360
            else:
                h = (60 * ((r_norm - g_norm) / diff) + 240) % 360

            s = 0 if max_c == 0 else (diff / max_c) * 1000
            v = max_c * 1000

            colour_data = json.dumps({"h": int(h), "s": int(s), "v": int(v)})

            commands = {
                "commands": [
                    {"code": "work_mode", "value": "colour"},
                    {"code": "colour_data_v2", "value": colour_data},
                ]
            }
            result = cloud.sendcommand(device_id, commands)

            if isinstance(result, dict) and "Error" in result:
                # Try v1 format
                commands = {
                    "commands": [
                        {"code": "work_mode", "value": "colour"},
                        {"code": "colour_data", "value": colour_data},
                    ]
                }
                result = cloud.sendcommand(device_id, commands)
                if isinstance(result, dict) and "Error" in result:
                    return f"Error setting color on '{device}': {result.get('Error')}"

            return f"Successfully set color to RGB({r}, {g}, {b}) on '{device}'."
        except Exception as e:
            return f"Error setting light color: {str(e)}"

    async def set_light_brightness(self, device: str, brightness: int = 100):
        """
        Set the brightness of a Tuya smart light/bulb.

        Args:
            device (str): The device name or device ID of the light.
            brightness (int): Brightness percentage (0-100). Defaults to 100.

        Returns:
            str: Confirmation message or error.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)

            brightness = max(0, min(100, int(brightness)))
            # Tuya brightness range is typically 10-1000
            tuya_brightness = max(10, int(brightness * 10))

            commands = {
                "commands": [{"code": "bright_value_v2", "value": tuya_brightness}]
            }
            result = cloud.sendcommand(device_id, commands)

            if isinstance(result, dict) and "Error" in result:
                # Try v1 format
                commands = {
                    "commands": [{"code": "bright_value", "value": tuya_brightness}]
                }
                result = cloud.sendcommand(device_id, commands)
                if isinstance(result, dict) and "Error" in result:
                    return (
                        f"Error setting brightness on '{device}': {result.get('Error')}"
                    )

            return f"Successfully set brightness to {brightness}% on '{device}'."
        except Exception as e:
            return f"Error setting light brightness: {str(e)}"

    async def set_thermostat_temperature(
        self, device: str, temperature: float, unit: str = "c"
    ):
        """
        Set the target temperature on a Tuya thermostat.

        Args:
            device (str): The device name or device ID of the thermostat.
            temperature (float): The target temperature to set.
            unit (str, optional): Temperature unit - 'c' for Celsius or 'f' for Fahrenheit. Defaults to 'c'.

        Returns:
            str: Confirmation message or error.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)

            # Tuya thermostats typically expect temperature * 10 or * 100
            temp_value = int(float(temperature) * 10)

            code = "temp_set" if unit.lower() == "c" else "temp_set_f"
            commands = {"commands": [{"code": code, "value": temp_value}]}
            result = cloud.sendcommand(device_id, commands)

            if isinstance(result, dict) and "Error" in result:
                # Try without multiplier
                commands = {
                    "commands": [{"code": code, "value": int(float(temperature))}]
                }
                result = cloud.sendcommand(device_id, commands)
                if isinstance(result, dict) and "Error" in result:
                    return f"Error setting temperature on '{device}': {result.get('Error')}"

            unit_label = "°C" if unit.lower() == "c" else "°F"
            return f"Successfully set temperature to {temperature}{unit_label} on '{device}'."
        except Exception as e:
            return f"Error setting thermostat temperature: {str(e)}"

    async def get_device_logs(self, device: str, days: int = 1):
        """
        Get recent activity logs for a Tuya device.

        Args:
            device (str): The device name or device ID.
            days (int, optional): Number of days of logs to retrieve (1-7). Defaults to 1.

        Returns:
            str: Formatted device logs or error message.
        """
        try:
            cloud = self._get_cloud()
            device_id = self._find_device_id(device)

            days = max(1, min(7, int(days)))
            result = cloud.getdevicelog(device_id, start=-days)

            if isinstance(result, dict) and "Error" in result:
                return f"Error getting logs for '{device}': {result.get('Error')}"

            logs = result
            if isinstance(result, dict) and "result" in result:
                logs = result["result"]

            if isinstance(logs, dict) and "logs" in logs:
                log_entries = logs["logs"]
                if not log_entries:
                    return f"No logs found for '{device}' in the last {days} day(s)."

                lines = [
                    f"**Logs for '{device}' (last {days} day(s), {len(log_entries)} entries):**\n"
                ]
                for entry in log_entries[:50]:  # Limit to 50 entries
                    if isinstance(entry, dict):
                        event_time = entry.get("event_time", "N/A")
                        code = entry.get("code", "N/A")
                        value = entry.get("value", "N/A")
                        lines.append(f"- [{event_time}] **{code}**: {value}")
                if len(log_entries) > 50:
                    lines.append(f"\n... and {len(log_entries) - 50} more entries.")
                return "\n".join(lines)

            return f"Logs for '{device}':\n```json\n{json.dumps(logs, indent=2)}\n```"
        except Exception as e:
            return f"Error getting device logs: {str(e)}"
