import logging
import json
import requests
from Extensions import Extensions
from Globals import getenv
from typing import Optional, List

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Home Assistant Extension for AGiXT

This extension enables interaction with Home Assistant for controlling smart home
devices, checking sensor states, triggering automations, and managing scenes.

Required environment variables:

- HOME_ASSISTANT_URL: The URL of your Home Assistant instance (e.g., http://homeassistant.local:8123)
- HOME_ASSISTANT_TOKEN: A Long-Lived Access Token from Home Assistant

How to get a Long-Lived Access Token:

1. Log in to your Home Assistant instance
2. Click your profile icon in the bottom left
3. Scroll down to "Long-Lived Access Tokens"
4. Click "Create Token"
5. Give it a name and copy the token
6. Set it as the HOME_ASSISTANT_TOKEN environment variable
"""


class home_assistant(Extensions):
    """
    The Home Assistant extension for AGiXT enables smart home control through
    the Home Assistant REST API. It supports controlling devices (lights, switches,
    climate, covers, etc.), checking sensor states, triggering automations and scripts,
    activating scenes, and querying the state of all entities.

    Requires a Home Assistant instance with a Long-Lived Access Token.

    To set up:
    1. Get a Long-Lived Access Token from your HA profile
    2. Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN environment variables
    """

    CATEGORY = "Smart Home & IoT"
    friendly_name = "Home Assistant"

    def __init__(self, **kwargs):
        self.base_url = kwargs.get("HOME_ASSISTANT_URL", getenv("HOME_ASSISTANT_URL", ""))
        self.token = kwargs.get("HOME_ASSISTANT_TOKEN", getenv("HOME_ASSISTANT_TOKEN", ""))
        self.commands = {}

        if self.base_url and self.token:
            self.base_url = self.base_url.rstrip("/")
            self.commands = {
                "Home Assistant - Get States": self.get_states,
                "Home Assistant - Get Entity State": self.get_entity_state,
                "Home Assistant - Turn On": self.turn_on,
                "Home Assistant - Turn Off": self.turn_off,
                "Home Assistant - Toggle": self.toggle,
                "Home Assistant - Set Light": self.set_light,
                "Home Assistant - Set Climate": self.set_climate,
                "Home Assistant - Get Services": self.get_services,
                "Home Assistant - Call Service": self.call_service,
                "Home Assistant - Fire Event": self.fire_event,
                "Home Assistant - Trigger Automation": self.trigger_automation,
                "Home Assistant - Get Automations": self.get_automations,
                "Home Assistant - Get Scenes": self.get_scenes,
                "Home Assistant - Activate Scene": self.activate_scene,
                "Home Assistant - Get History": self.get_history,
                "Home Assistant - Get Logbook": self.get_logbook,
            }

    def _get_headers(self):
        """Returns authorization headers for Home Assistant API requests."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _make_request(self, method, endpoint, **kwargs):
        """Make an authenticated request to the Home Assistant API."""
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        try:
            response = requests.request(
                method, url, headers=self._get_headers(), **kwargs
            )

            if response.status_code == 401:
                return None, "Authentication failed. Check your HOME_ASSISTANT_TOKEN."
            if response.status_code == 404:
                return None, "Endpoint or entity not found."
            if response.status_code >= 400:
                return None, f"API error (HTTP {response.status_code}): {response.text}"

            if not response.text:
                return {"success": True}, None

            return response.json(), None
        except requests.exceptions.ConnectionError:
            return None, "Cannot connect to Home Assistant. Check HOME_ASSISTANT_URL."
        except Exception as e:
            return None, f"Request error: {str(e)}"

    def _format_state(self, entity):
        """Format an entity state object into readable text."""
        entity_id = entity.get("entity_id", "")
        state = entity.get("state", "unknown")
        friendly_name = entity.get("attributes", {}).get("friendly_name", entity_id)
        domain = entity_id.split(".")[0] if "." in entity_id else "unknown"

        attrs = entity.get("attributes", {})
        extra = ""

        if domain == "light" and state == "on":
            brightness = attrs.get("brightness")
            color_temp = attrs.get("color_temp")
            if brightness:
                extra += f", Brightness: {round(brightness / 255 * 100)}%"
            if color_temp:
                extra += f", Color Temp: {color_temp}"
        elif domain == "climate":
            current_temp = attrs.get("current_temperature")
            target_temp = attrs.get("temperature")
            hvac_action = attrs.get("hvac_action", "")
            if current_temp:
                extra += f", Current: {current_temp}°"
            if target_temp:
                extra += f", Target: {target_temp}°"
            if hvac_action:
                extra += f", Action: {hvac_action}"
        elif domain == "sensor":
            unit = attrs.get("unit_of_measurement", "")
            if unit:
                extra += f" {unit}"
        elif domain == "cover":
            position = attrs.get("current_position")
            if position is not None:
                extra += f", Position: {position}%"

        return f"**{friendly_name}** (`{entity_id}`): {state}{extra}"

    async def get_states(self, domain: str = None):
        """
        Get states of all entities, optionally filtered by domain.

        Args:
            domain (str, optional): Filter by domain (e.g., 'light', 'switch', 'sensor', 'climate', 'cover', 'automation').

        Returns:
            str: Formatted list of entity states or error message.
        """
        try:
            data, error = self._make_request("GET", "states")
            if error:
                return f"Error getting states: {error}"

            entities = data if isinstance(data, list) else []

            if domain:
                entities = [e for e in entities if e.get("entity_id", "").startswith(f"{domain}.")]

            if not entities:
                return f"No entities found{f' for domain: {domain}' if domain else ''}."

            # Group by domain
            grouped = {}
            for entity in entities:
                eid = entity.get("entity_id", "")
                d = eid.split(".")[0] if "." in eid else "other"
                if d not in grouped:
                    grouped[d] = []
                grouped[d].append(entity)

            result = "**Home Assistant Entities:**\n\n"
            for d in sorted(grouped.keys()):
                result += f"### {d.replace('_', ' ').title()}\n"
                for entity in sorted(grouped[d], key=lambda e: e.get("entity_id", "")):
                    result += f"- {self._format_state(entity)}\n"
                result += "\n"

            return result
        except Exception as e:
            return f"Error getting states: {str(e)}"

    async def get_entity_state(self, entity_id: str):
        """
        Get the state and attributes of a specific entity.

        Args:
            entity_id (str): The entity ID (e.g., 'light.living_room', 'sensor.temperature').

        Returns:
            str: Entity state details or error message.
        """
        try:
            data, error = self._make_request("GET", f"states/{entity_id}")
            if error:
                return f"Error getting entity state: {error}"

            attrs = data.get("attributes", {})
            result = f"**Entity: {entity_id}**\n\n"
            result += f"- **State:** {data.get('state', 'unknown')}\n"
            result += f"- **Friendly Name:** {attrs.get('friendly_name', 'N/A')}\n"
            result += f"- **Last Changed:** {data.get('last_changed', 'N/A')}\n"
            result += f"- **Last Updated:** {data.get('last_updated', 'N/A')}\n"

            if attrs:
                result += "\n**Attributes:**\n"
                for key, value in sorted(attrs.items()):
                    if key != "friendly_name":
                        result += f"- {key}: {value}\n"

            return result
        except Exception as e:
            return f"Error getting entity state: {str(e)}"

    async def turn_on(self, entity_id: str):
        """
        Turn on a device/entity in Home Assistant.

        Args:
            entity_id (str): The entity ID to turn on (e.g., 'light.living_room', 'switch.fan').

        Returns:
            str: Confirmation message or error.
        """
        try:
            domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
            data, error = self._make_request(
                "POST",
                f"services/{domain}/turn_on",
                json={"entity_id": entity_id},
            )
            if error:
                return f"Error turning on {entity_id}: {error}"
            return f"Successfully turned on: {entity_id}"
        except Exception as e:
            return f"Error turning on device: {str(e)}"

    async def turn_off(self, entity_id: str):
        """
        Turn off a device/entity in Home Assistant.

        Args:
            entity_id (str): The entity ID to turn off (e.g., 'light.living_room', 'switch.fan').

        Returns:
            str: Confirmation message or error.
        """
        try:
            domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
            data, error = self._make_request(
                "POST",
                f"services/{domain}/turn_off",
                json={"entity_id": entity_id},
            )
            if error:
                return f"Error turning off {entity_id}: {error}"
            return f"Successfully turned off: {entity_id}"
        except Exception as e:
            return f"Error turning off device: {str(e)}"

    async def toggle(self, entity_id: str):
        """
        Toggle a device/entity in Home Assistant.

        Args:
            entity_id (str): The entity ID to toggle (e.g., 'light.living_room', 'switch.fan').

        Returns:
            str: Confirmation message or error.
        """
        try:
            domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
            data, error = self._make_request(
                "POST",
                f"services/{domain}/toggle",
                json={"entity_id": entity_id},
            )
            if error:
                return f"Error toggling {entity_id}: {error}"
            return f"Successfully toggled: {entity_id}"
        except Exception as e:
            return f"Error toggling device: {str(e)}"

    async def set_light(
        self,
        entity_id: str,
        brightness_pct: int = None,
        color_name: str = None,
        color_temp: int = None,
    ):
        """
        Set light attributes (brightness, color, temperature).

        Args:
            entity_id (str): The light entity ID (e.g., 'light.living_room').
            brightness_pct (int, optional): Brightness percentage (0-100).
            color_name (str, optional): Color name (e.g., 'red', 'blue', 'warm_white').
            color_temp (int, optional): Color temperature in mireds (150-500).

        Returns:
            str: Confirmation message or error.
        """
        try:
            service_data = {"entity_id": entity_id}

            if brightness_pct is not None:
                service_data["brightness_pct"] = max(0, min(100, int(brightness_pct)))
            if color_name:
                service_data["color_name"] = color_name
            if color_temp is not None:
                service_data["color_temp"] = int(color_temp)

            data, error = self._make_request(
                "POST",
                "services/light/turn_on",
                json=service_data,
            )
            if error:
                return f"Error setting light {entity_id}: {error}"

            settings = []
            if brightness_pct is not None:
                settings.append(f"brightness: {brightness_pct}%")
            if color_name:
                settings.append(f"color: {color_name}")
            if color_temp is not None:
                settings.append(f"color temp: {color_temp}")

            return f"Light {entity_id} set to: {', '.join(settings)}"
        except Exception as e:
            return f"Error setting light: {str(e)}"

    async def set_climate(
        self,
        entity_id: str,
        temperature: float = None,
        hvac_mode: str = None,
        target_temp_high: float = None,
        target_temp_low: float = None,
    ):
        """
        Set climate/thermostat settings.

        Args:
            entity_id (str): The climate entity ID (e.g., 'climate.living_room').
            temperature (float, optional): Target temperature.
            hvac_mode (str, optional): HVAC mode ('heat', 'cool', 'auto', 'off', 'fan_only', 'dry').
            target_temp_high (float, optional): High target for auto mode.
            target_temp_low (float, optional): Low target for auto mode.

        Returns:
            str: Confirmation message or error.
        """
        try:
            if hvac_mode:
                data, error = self._make_request(
                    "POST",
                    "services/climate/set_hvac_mode",
                    json={"entity_id": entity_id, "hvac_mode": hvac_mode},
                )
                if error:
                    return f"Error setting HVAC mode: {error}"

            if temperature is not None:
                service_data = {"entity_id": entity_id, "temperature": float(temperature)}
                if target_temp_high is not None:
                    service_data["target_temp_high"] = float(target_temp_high)
                if target_temp_low is not None:
                    service_data["target_temp_low"] = float(target_temp_low)

                data, error = self._make_request(
                    "POST",
                    "services/climate/set_temperature",
                    json=service_data,
                )
                if error:
                    return f"Error setting temperature: {error}"

            settings = []
            if hvac_mode:
                settings.append(f"mode: {hvac_mode}")
            if temperature is not None:
                settings.append(f"temperature: {temperature}°")

            return f"Climate {entity_id} set to: {', '.join(settings) if settings else 'updated'}"
        except Exception as e:
            return f"Error setting climate: {str(e)}"

    async def get_services(self, domain: str = None):
        """
        Get available services, optionally filtered by domain.

        Args:
            domain (str, optional): Filter by domain (e.g., 'light', 'switch', 'automation').

        Returns:
            str: List of available services or error message.
        """
        try:
            data, error = self._make_request("GET", "services")
            if error:
                return f"Error getting services: {error}"

            if domain:
                data = [d for d in data if d.get("domain") == domain]

            if not data:
                return f"No services found{f' for domain: {domain}' if domain else ''}."

            result = "**Available Services:**\n\n"
            for domain_obj in data:
                d = domain_obj.get("domain", "")
                services = domain_obj.get("services", {})
                result += f"### {d}\n"
                for svc_name, svc_info in sorted(services.items()):
                    desc = svc_info.get("description", "")
                    result += f"- `{d}.{svc_name}`{f': {desc}' if desc else ''}\n"
                result += "\n"

            return result
        except Exception as e:
            return f"Error getting services: {str(e)}"

    async def call_service(self, domain: str, service: str, entity_id: str = None, data: str = None):
        """
        Call any Home Assistant service with custom data.

        Args:
            domain (str): The service domain (e.g., 'light', 'switch', 'media_player').
            service (str): The service name (e.g., 'turn_on', 'toggle', 'play_media').
            entity_id (str, optional): The entity ID to target.
            data (str, optional): JSON string of additional service data.

        Returns:
            str: Confirmation message or error.
        """
        try:
            service_data = {}
            if entity_id:
                service_data["entity_id"] = entity_id
            if data:
                try:
                    extra = json.loads(data)
                    service_data.update(extra)
                except json.JSONDecodeError:
                    return "Error: 'data' must be a valid JSON string."

            result, error = self._make_request(
                "POST",
                f"services/{domain}/{service}",
                json=service_data,
            )
            if error:
                return f"Error calling service {domain}.{service}: {error}"

            return f"Successfully called service: {domain}.{service}"
        except Exception as e:
            return f"Error calling service: {str(e)}"

    async def fire_event(self, event_type: str, event_data: str = None):
        """
        Fire a custom event in Home Assistant.

        Args:
            event_type (str): The event type to fire.
            event_data (str, optional): JSON string of event data.

        Returns:
            str: Confirmation message or error.
        """
        try:
            payload = {}
            if event_data:
                try:
                    payload = json.loads(event_data)
                except json.JSONDecodeError:
                    return "Error: 'event_data' must be a valid JSON string."

            data, error = self._make_request(
                "POST",
                f"events/{event_type}",
                json=payload,
            )
            if error:
                return f"Error firing event: {error}"

            return f"Successfully fired event: {event_type}"
        except Exception as e:
            return f"Error firing event: {str(e)}"

    async def trigger_automation(self, entity_id: str):
        """
        Trigger a specific automation.

        Args:
            entity_id (str): The automation entity ID (e.g., 'automation.morning_routine').

        Returns:
            str: Confirmation message or error.
        """
        try:
            data, error = self._make_request(
                "POST",
                "services/automation/trigger",
                json={"entity_id": entity_id},
            )
            if error:
                return f"Error triggering automation: {error}"

            return f"Successfully triggered automation: {entity_id}"
        except Exception as e:
            return f"Error triggering automation: {str(e)}"

    async def get_automations(self):
        """
        Get all automations and their states.

        Returns:
            str: List of automations or error message.
        """
        try:
            data, error = self._make_request("GET", "states")
            if error:
                return f"Error getting automations: {error}"

            automations = [e for e in data if e.get("entity_id", "").startswith("automation.")]

            if not automations:
                return "No automations found."

            result = "**Automations:**\n\n"
            for auto in sorted(automations, key=lambda e: e.get("entity_id", "")):
                name = auto.get("attributes", {}).get("friendly_name", auto.get("entity_id"))
                state = auto.get("state", "unknown")
                last_triggered = auto.get("attributes", {}).get("last_triggered", "Never")
                icon = "🟢" if state == "on" else "🔴"
                result += f"- {icon} **{name}** (`{auto.get('entity_id', '')}`) - Last triggered: {last_triggered}\n"

            return result
        except Exception as e:
            return f"Error getting automations: {str(e)}"

    async def get_scenes(self):
        """
        Get all scenes.

        Returns:
            str: List of scenes or error message.
        """
        try:
            data, error = self._make_request("GET", "states")
            if error:
                return f"Error getting scenes: {error}"

            scenes = [e for e in data if e.get("entity_id", "").startswith("scene.")]

            if not scenes:
                return "No scenes found."

            result = "**Scenes:**\n\n"
            for scene in sorted(scenes, key=lambda e: e.get("entity_id", "")):
                name = scene.get("attributes", {}).get("friendly_name", scene.get("entity_id"))
                result += f"- 🎬 **{name}** (`{scene.get('entity_id', '')}`)\n"

            return result
        except Exception as e:
            return f"Error getting scenes: {str(e)}"

    async def activate_scene(self, entity_id: str):
        """
        Activate a scene.

        Args:
            entity_id (str): The scene entity ID (e.g., 'scene.movie_time').

        Returns:
            str: Confirmation message or error.
        """
        try:
            data, error = self._make_request(
                "POST",
                "services/scene/turn_on",
                json={"entity_id": entity_id},
            )
            if error:
                return f"Error activating scene: {error}"

            return f"Successfully activated scene: {entity_id}"
        except Exception as e:
            return f"Error activating scene: {str(e)}"

    async def get_history(self, entity_id: str, hours: int = 24):
        """
        Get state history for an entity.

        Args:
            entity_id (str): The entity ID to get history for.
            hours (int): Number of hours of history to retrieve. Default 24.

        Returns:
            str: State history or error message.
        """
        try:
            from datetime import datetime, timedelta, timezone

            start_time = (datetime.now(timezone.utc) - timedelta(hours=int(hours))).isoformat()

            data, error = self._make_request(
                "GET",
                f"history/period/{start_time}?filter_entity_id={entity_id}&minimal_response",
            )
            if error:
                return f"Error getting history: {error}"

            if not data or not data[0]:
                return f"No history found for {entity_id} in the last {hours} hours."

            states = data[0]
            result = f"**History for {entity_id} (last {hours} hours):**\n\n"
            for state in states[-30:]:  # Last 30 state changes
                result += f"- {state.get('state', '?')} at {state.get('last_changed', '?')}\n"

            if len(states) > 30:
                result += f"\n_({len(states)} total state changes, showing last 30)_"

            return result
        except Exception as e:
            return f"Error getting history: {str(e)}"

    async def get_logbook(self, hours: int = 24, entity_id: str = None):
        """
        Get logbook entries.

        Args:
            hours (int): Number of hours of log entries to retrieve. Default 24.
            entity_id (str, optional): Filter by entity ID.

        Returns:
            str: Logbook entries or error message.
        """
        try:
            from datetime import datetime, timedelta, timezone

            start_time = (datetime.now(timezone.utc) - timedelta(hours=int(hours))).isoformat()
            endpoint = f"logbook/{start_time}"
            if entity_id:
                endpoint += f"?entity={entity_id}"

            data, error = self._make_request("GET", endpoint)
            if error:
                return f"Error getting logbook: {error}"

            if not data:
                return f"No logbook entries found in the last {hours} hours."

            result = f"**Logbook (last {hours} hours):**\n\n"
            for entry in data[-50:]:  # Last 50 entries
                name = entry.get("name", "")
                message = entry.get("message", "")
                when = entry.get("when", "")
                result += f"- **{name}** {message} _{when}_\n"

            if len(data) > 50:
                result += f"\n_({len(data)} total entries, showing last 50)_"

            return result
        except Exception as e:
            return f"Error getting logbook: {str(e)}"
