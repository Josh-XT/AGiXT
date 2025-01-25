import os
import logging
import requests
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth


class tesla(Extensions):
    """
    The Tesla extension provides direct control of Tesla vehicles through the Fleet API.
    This extension allows AI agents to:
    - Control vehicle access (lock/unlock)
    - Control climate settings
    - Control trunk/charging port
    - Manage charging
    - Control media and volume
    - Send navigation commands
    - Control windows and sunroof
    - Manage vehicle settings

    The extension requires the user to be authenticated with Tesla through OAuth.
    """

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("TESLA_ACCESS_TOKEN", None)
        self.api_base_url = "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1"
        tesla_client_id = getenv("TESLA_CLIENT_ID")
        tesla_client_secret = getenv("TESLA_CLIENT_SECRET")
        self.auth = None

        if tesla_client_id and tesla_client_secret:
            self.commands = {
                # Basic Vehicle Controls
                "Tesla - Lock Doors": self.lock_doors,
                "Tesla - Unlock Doors": self.unlock_doors,
                "Tesla - Flash Lights": self.flash_lights,
                "Tesla - Honk Horn": self.honk_horn,
                "Tesla - Wake Vehicle": self.wake_vehicle,
                "Tesla - Remote Start": self.remote_start,
                # Trunk/Port Controls
                "Tesla - Actuate Trunk": self.actuate_trunk,
                "Tesla - Open Charge Port": self.open_charge_port,
                "Tesla - Close Charge Port": self.close_charge_port,
                # Climate Controls
                "Tesla - Set Temperature": self.set_temperature,
                "Tesla - Start Climate": self.start_climate,
                "Tesla - Stop Climate": self.stop_climate,
                "Tesla - Set Seat Heater": self.set_seat_heater,
                "Tesla - Set Seat Cooler": self.set_seat_cooler,
                "Tesla - Set Steering Wheel Heat": self.set_steering_wheel_heat,
                "Tesla - Set Climate Keeper": self.set_climate_keeper,
                "Tesla - Set Bioweapon Mode": self.set_bioweapon_mode,
                # Charging Controls
                "Tesla - Start Charging": self.start_charging,
                "Tesla - Stop Charging": self.stop_charging,
                "Tesla - Set Charge Limit": self.set_charge_limit,
                "Tesla - Set Charging Amps": self.set_charging_amps,
                "Tesla - Add Charge Schedule": self.add_charge_schedule,
                "Tesla - Remove Charge Schedule": self.remove_charge_schedule,
                # Media Controls
                "Tesla - Adjust Volume": self.adjust_volume,
                "Tesla - Toggle Playback": self.toggle_playback,
                "Tesla - Next Track": self.next_track,
                "Tesla - Previous Track": self.previous_track,
                "Tesla - Next Favorite": self.next_favorite,
                "Tesla - Previous Favorite": self.previous_favorite,
                # Windows/Sunroof
                "Tesla - Control Windows": self.control_windows,
                "Tesla - Control Sunroof": self.control_sunroof,
                # Navigation
                "Tesla - Navigate To": self.navigate_to,
                "Tesla - Navigate To Supercharger": self.navigate_to_supercharger,
                "Tesla - Set Waypoints": self.set_waypoints,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Tesla client: {str(e)}")

    def verify_user(self):
        """Verify user access token and refresh if needed"""
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="tesla")
        if not self.access_token:
            raise Exception("No valid Tesla access token found")

    async def send_command(self, vehicle_tag, command, data=None):
        """Send command to vehicle"""
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            url = f"{self.api_base_url}/vehicles/{vehicle_tag}/command/{command}"

            if data:
                response = requests.post(url, headers=headers, json=data)
            else:
                response = requests.post(url, headers=headers)

            if response.status_code != 200:
                raise Exception(f"Command failed: {response.text}")

            return response.json()

        except Exception as e:
            logging.error(f"Error sending command {command}: {str(e)}")
            return {"error": str(e)}

    # Basic Vehicle Controls
    async def lock_doors(self, vehicle_tag):
        """Lock the vehicle doors"""
        return await self.send_command(vehicle_tag, "door_lock")

    async def unlock_doors(self, vehicle_tag):
        """Unlock the vehicle doors"""
        return await self.send_command(vehicle_tag, "door_unlock")

    async def flash_lights(self, vehicle_tag):
        """Flash the vehicle lights"""
        return await self.send_command(vehicle_tag, "flash_lights")

    async def honk_horn(self, vehicle_tag):
        """Honk the vehicle horn"""
        return await self.send_command(vehicle_tag, "honk_horn")

    async def wake_vehicle(self, vehicle_tag):
        """Wake the vehicle from sleep"""
        return await self.send_command(vehicle_tag, "wake_up")

    async def remote_start(self, vehicle_tag):
        """Enable keyless driving"""
        return await self.send_command(vehicle_tag, "remote_start_drive")

    # Trunk/Port Controls
    async def actuate_trunk(self, vehicle_tag, which_trunk):
        """Control front or rear trunk"""
        return await self.send_command(
            vehicle_tag,
            "actuate_trunk",
            {"which_trunk": which_trunk},  # "front" or "rear"
        )

    async def open_charge_port(self, vehicle_tag):
        """Open the charge port"""
        return await self.send_command(vehicle_tag, "charge_port_door_open")

    async def close_charge_port(self, vehicle_tag):
        """Close the charge port"""
        return await self.send_command(vehicle_tag, "charge_port_door_close")

    # Climate Controls
    async def set_temperature(self, vehicle_tag, driver_temp, passenger_temp):
        """Set driver and passenger temperatures"""
        return await self.send_command(
            vehicle_tag,
            "set_temps",
            {"driver_temp": driver_temp, "passenger_temp": passenger_temp},
        )

    async def start_climate(self, vehicle_tag):
        """Start climate control"""
        return await self.send_command(vehicle_tag, "auto_conditioning_start")

    async def stop_climate(self, vehicle_tag):
        """Stop climate control"""
        return await self.send_command(vehicle_tag, "auto_conditioning_stop")

    async def set_seat_heater(self, vehicle_tag, seat_position, level):
        """Set seat heater level"""
        return await self.send_command(
            vehicle_tag,
            "remote_seat_heater_request",
            {"heater": seat_position, "level": level},  # 0-8  # 0-3
        )

    async def set_seat_cooler(self, vehicle_tag, seat_position, level):
        """Set seat cooling level"""
        return await self.send_command(
            vehicle_tag,
            "remote_seat_cooler_request",
            {"seat_position": seat_position, "seat_cooler_level": level},  # 1-2  # 0-3
        )

    async def set_steering_wheel_heat(self, vehicle_tag, enabled):
        """Set steering wheel heater"""
        return await self.send_command(
            vehicle_tag, "remote_steering_wheel_heater_request", {"on": enabled}
        )

    async def set_climate_keeper(self, vehicle_tag, mode):
        """Set climate keeper mode"""
        return await self.send_command(
            vehicle_tag,
            "set_climate_keeper_mode",
            {"climate_keeper_mode": mode},  # 0: Off, 1: Keep, 2: Dog, 3: Camp
        )

    async def set_bioweapon_mode(self, vehicle_tag, enabled, manual_override=False):
        """Set bioweapon defense mode"""
        return await self.send_command(
            vehicle_tag,
            "set_bioweapon_mode",
            {"on": enabled, "manual_override": manual_override},
        )

    # Charging Controls
    async def start_charging(self, vehicle_tag):
        """Start vehicle charging"""
        return await self.send_command(vehicle_tag, "charge_start")

    async def stop_charging(self, vehicle_tag):
        """Stop vehicle charging"""
        return await self.send_command(vehicle_tag, "charge_stop")

    async def set_charge_limit(self, vehicle_tag, percent):
        """Set charging limit percentage"""
        return await self.send_command(
            vehicle_tag, "set_charge_limit", {"percent": percent}
        )

    async def set_charging_amps(self, vehicle_tag, amps):
        """Set charging amperage"""
        return await self.send_command(
            vehicle_tag, "set_charging_amps", {"charging_amps": amps}
        )

    async def add_charge_schedule(self, vehicle_tag, schedule_data):
        """Add charging schedule"""
        return await self.send_command(
            vehicle_tag, "add_charge_schedule", schedule_data
        )

    async def remove_charge_schedule(self, vehicle_tag, schedule_id):
        """Remove charging schedule"""
        return await self.send_command(
            vehicle_tag, "remove_charge_schedule", {"id": schedule_id}
        )

    # Media Controls
    async def adjust_volume(self, vehicle_tag, volume):
        """Adjust media volume"""
        return await self.send_command(vehicle_tag, "adjust_volume", {"volume": volume})

    async def toggle_playback(self, vehicle_tag):
        """Toggle media playback"""
        return await self.send_command(vehicle_tag, "media_toggle_playback")

    async def next_track(self, vehicle_tag):
        """Next media track"""
        return await self.send_command(vehicle_tag, "media_next_track")

    async def previous_track(self, vehicle_tag):
        """Previous media track"""
        return await self.send_command(vehicle_tag, "media_prev_track")

    async def next_favorite(self, vehicle_tag):
        """Next favorite track"""
        return await self.send_command(vehicle_tag, "media_next_fav")

    async def previous_favorite(self, vehicle_tag):
        """Previous favorite track"""
        return await self.send_command(vehicle_tag, "media_prev_fav")

    # Windows/Sunroof
    async def control_windows(self, vehicle_tag, command, lat=None, lon=None):
        """Control windows (vent/close)"""
        data = {"command": command}
        if lat and lon:
            data.update({"lat": lat, "lon": lon})
        return await self.send_command(vehicle_tag, "window_control", data)

    async def control_sunroof(self, vehicle_tag, state):
        """Control sunroof (stop/close/vent)"""
        return await self.send_command(
            vehicle_tag, "sun_roof_control", {"state": state}
        )

    # Navigation
    async def navigate_to(self, vehicle_tag, lat, lon, order=0):
        """Navigate to coordinates"""
        return await self.send_command(
            vehicle_tag,
            "navigation_gps_request",
            {"lat": lat, "lon": lon, "order": order},
        )

    async def navigate_to_supercharger(self, vehicle_tag, supercharger_id, order=0):
        """Navigate to supercharger"""
        return await self.send_command(
            vehicle_tag,
            "navigation_sc_request",
            {"id": supercharger_id, "order": order},
        )

    async def set_waypoints(self, vehicle_tag, waypoints):
        """Set navigation waypoints"""
        return await self.send_command(
            vehicle_tag, "navigation_waypoints_request", {"waypoints": waypoints}
        )
