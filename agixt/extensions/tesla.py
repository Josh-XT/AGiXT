import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Dict, List, Any


class TeslaVINDecoder:
    """
    A class for decoding Tesla Vehicle Identification Numbers (VINs).

    Tesla VIN Structure:
    - Position 1-3: World Manufacturer Identifier (WMI)
    - Position 4: Vehicle Type/Line
    - Position 5: Body Type
    - Position 6: Restraint System
    - Position 7: Drivetrain
    - Position 8: Motor/Battery Config
    - Position 9: Check Digit
    - Position 10: Model Year
    - Position 11: Manufacturing Plant
    - Position 12-17: Production Sequence Number
    """

    # World Manufacturer Identifier
    WMI_CODES = {
        "5YJ": "Tesla USA",
        "7SA": "Tesla USA (Model Y)",
        "LRW": "Tesla China",
        "XP7": "Tesla Europe (Berlin)",
    }

    # Vehicle Type/Line (Position 4)
    MODEL_CODES = {
        "S": "Model S",
        "3": "Model 3",
        "X": "Model X",
        "Y": "Model Y",
        "E": "Model 3",
        "G": "Model Y",
        "R": "Roadster",
        "C": "Cybertruck",
    }

    # Body Type (Position 5)
    BODY_CODES = {
        "A": "Sedan or Hatchback",
        "B": "SUV or Crossover",
        "C": "Coupe",
        "E": "Sedan or Hatchback",
        "F": "SUV or Crossover",
        "P": "Performance",
        "R": "Roadster",
        "S": "Standard",
        "T": "Truck",
    }

    # Drivetrain (Position 7)
    DRIVETRAIN_CODES = {
        "1": "Dual Motor - AWD",  # Updated from RWD to AWD
        "2": "Dual Motor - AWD",
        "3": "Performance Dual Motor - AWD",
        "4": "Tri Motor - AWD (Plaid)",  # Added Plaid designation
        "5": "Dual Motor - AWD (Performance)",  # Updated from RWD to AWD
        "6": "Quad Motor - AWD",
        "A": "Dual Motor - AWD",  # Updated from RWD to AWD
        "B": "Dual Motor - AWD",
        "C": "Performance Dual Motor - AWD",
        "D": "Tri Motor - AWD (Plaid)",  # Added Plaid designation
        "E": "Tri Motor - AWD (Plaid)",  # Updated to Plaid based on your feedback
        "F": "Quad Motor - AWD",
    }

    # Motor/Battery Config (Position 8)
    BATTERY_CODES = {
        "1": "Standard Range",
        "2": "Mid Range",
        "3": "Long Range",
        "4": "Performance",
        "C": "Standard Range",
        "D": "Mid Range",
        "E": "Long Range",
        "F": "Performance",
        "P": "Performance",
    }

    # Model Year (Position 10)
    MODEL_YEARS = {
        "A": 2010,
        "B": 2011,
        "C": 2012,
        "D": 2013,
        "E": 2014,
        "F": 2015,
        "G": 2016,
        "H": 2017,
        "J": 2018,
        "K": 2019,
        "L": 2020,
        "M": 2021,
        "N": 2022,
        "P": 2023,
        "R": 2024,
        "S": 2025,
        "T": 2026,
        "V": 2027,
        "W": 2028,
        "X": 2029,
        "Y": 2030,
    }

    # Plant Codes (Position 11)
    PLANT_CODES = {
        "F": "Fremont, California, USA",
        "R": "Reno, Nevada, USA (Gigafactory 1)",
        "C": "Shanghai, China (Gigafactory 3)",
        "B": "Berlin, Germany (Gigafactory 4)",
        "A": "Austin, Texas, USA (Gigafactory 5)",
    }

    @staticmethod
    def validate_vin(vin: str) -> bool:
        """Validate if the VIN is properly formatted for Tesla."""
        if not vin or len(vin) != 17:
            return False

        # Check if the VIN starts with a known Tesla WMI
        for wmi in TeslaVINDecoder.WMI_CODES.keys():
            if vin.startswith(wmi):
                return True

        return False

    @staticmethod
    def decode_vin(vin: str) -> Dict[str, Any]:
        """
        Decode a Tesla VIN and return a dictionary with vehicle information.

        Args:
            vin: A 17-character Tesla Vehicle Identification Number

        Returns:
            A dictionary containing decoded vehicle information
        """
        if not TeslaVINDecoder.validate_vin(vin):
            return {"error": "Invalid Tesla VIN format", "vin": vin}

        # Initialize result dictionary
        result = {
            "vin": vin,
            "manufacturer": TeslaVINDecoder.WMI_CODES.get(
                vin[0:3], "Unknown Manufacturer"
            ),
            "model_code": vin[3],
            "model": TeslaVINDecoder.MODEL_CODES.get(vin[3], "Unknown Model"),
            "body_type": TeslaVINDecoder.BODY_CODES.get(vin[4], "Unknown Body Type"),
            "restraint_system": vin[5],  # Typically safety/restraint system info
            "drivetrain_code": vin[6],
            "battery_config_code": vin[7],
            "check_digit": vin[8],
            "model_year_code": vin[9],
            "model_year": TeslaVINDecoder.MODEL_YEARS.get(vin[9], "Unknown Year"),
            "plant_code": vin[10],
            "manufacturing_plant": TeslaVINDecoder.PLANT_CODES.get(
                vin[10], "Unknown Plant"
            ),
            "production_sequence": vin[11:17],
        }

        # Determine drivetrain and trim based on model-specific rules
        model_code = vin[3]
        drivetrain_code = vin[6]
        battery_code = vin[7]

        # Model S specific interpretations
        if model_code == "S":
            if drivetrain_code == "E":
                result["drivetrain"] = "Tri Motor - AWD (Plaid)"
                result["trim"] = "Plaid"
            else:
                result["drivetrain"] = TeslaVINDecoder.DRIVETRAIN_CODES.get(
                    drivetrain_code, "Unknown Drivetrain"
                )
                if "Plaid" in result["drivetrain"]:
                    result["trim"] = "Plaid"
                elif "Performance" in result["drivetrain"]:
                    result["trim"] = "Performance"
                else:
                    result["trim"] = TeslaVINDecoder.BATTERY_CODES.get(battery_code, "")

            result["battery_config"] = TeslaVINDecoder.BATTERY_CODES.get(
                battery_code, "Unknown Battery Config"
            )

        # Model 3 specific interpretations
        elif model_code == "3" or model_code == "E":
            if drivetrain_code == "E":
                if battery_code == "C":
                    result["drivetrain"] = "Dual Motor - AWD (Performance)"
                    result["trim"] = "Performance"
                else:
                    result["drivetrain"] = "Dual Motor - AWD"
                    result["trim"] = TeslaVINDecoder.BATTERY_CODES.get(battery_code, "")
            else:
                result["drivetrain"] = TeslaVINDecoder.DRIVETRAIN_CODES.get(
                    drivetrain_code, "Unknown Drivetrain"
                )
                if "Performance" in result["drivetrain"]:
                    result["trim"] = "Performance"
                else:
                    result["trim"] = TeslaVINDecoder.BATTERY_CODES.get(battery_code, "")

            result["battery_config"] = TeslaVINDecoder.BATTERY_CODES.get(
                battery_code, "Unknown Battery Config"
            )

        # Model Y specific interpretations
        elif model_code == "Y" or model_code == "G":
            if drivetrain_code == "E":
                if battery_code == "E":
                    result["drivetrain"] = "Dual Motor - AWD"
                    result["trim"] = "Long Range"
                elif battery_code == "F" or battery_code == "P":
                    result["drivetrain"] = "Dual Motor - AWD (Performance)"
                    result["trim"] = "Performance"
                else:
                    result["drivetrain"] = "Dual Motor - AWD"
                    result["trim"] = TeslaVINDecoder.BATTERY_CODES.get(battery_code, "")
            else:
                result["drivetrain"] = TeslaVINDecoder.DRIVETRAIN_CODES.get(
                    drivetrain_code, "Unknown Drivetrain"
                )
                if "Performance" in result["drivetrain"]:
                    result["trim"] = "Performance"
                else:
                    result["trim"] = TeslaVINDecoder.BATTERY_CODES.get(battery_code, "")

            result["battery_config"] = TeslaVINDecoder.BATTERY_CODES.get(
                battery_code, "Unknown Battery Config"
            )

        # Model X and other models
        else:
            result["drivetrain"] = TeslaVINDecoder.DRIVETRAIN_CODES.get(
                drivetrain_code, "Unknown Drivetrain"
            )
            result["battery_config"] = TeslaVINDecoder.BATTERY_CODES.get(
                battery_code, "Unknown Battery Config"
            )

            if "Plaid" in result["drivetrain"]:
                result["trim"] = "Plaid"
            elif (
                "Performance" in result["drivetrain"]
                or "Performance" in result["battery_config"]
            ):
                result["trim"] = "Performance"
            else:
                result["trim"] = TeslaVINDecoder.BATTERY_CODES.get(battery_code, "")

        # Determine drive type
        if "AWD" in result.get("drivetrain", ""):
            result["drive_type"] = "AWD"
        elif "RWD" in result.get("drivetrain", ""):
            result["drive_type"] = "RWD"
        else:
            result["drive_type"] = ""

        # Create full model description
        full_description_parts = [result["model"]]
        if "trim" in result and result["trim"]:
            full_description_parts.append(result["trim"])
        if "drive_type" in result and result["drive_type"]:
            full_description_parts.append(result["drive_type"])

        result["full_description"] = " ".join(full_description_parts)

        return result

    @staticmethod
    def batch_decode(vins: List[str]) -> List[Dict[str, Any]]:
        """Decode multiple VINs and return a list of decoded results."""
        return [TeslaVINDecoder.decode_vin(vin) for vin in vins]


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
                "Tesla - Get Vehicles": self.get_vehicles,
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

    async def get_vehicles(self):
        """Get list of vehicles with key state information

        Args:
            None

        Returns:
            str: Table of user's Tesla vehicles with key information

        Note: This should be used any time the user asks for any vehicle interaction to ensure the correct vehicle is selected by vehicle tag (VIN).
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get the list of vehicles
            url = f"{self.api_base_url}/vehicles"
            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                raise Exception(f"Failed to get vehicles: {response.text}")

            data = response.json()
            vehicle_data = data["response"]

            # Collect VINs for decoding
            vins = []
            for vehicle in vehicle_data:
                if "vin" in vehicle:
                    vins.append(vehicle["vin"])

            # Decode VINs
            vin_decodings = TeslaVINDecoder.batch_decode(vins)

            # Create result table header with additional columns
            vehicles = "User's Tesla Vehicles:\n| VIN | Model | Year | Description | Battery | Status | Climate | Odometer |\n"
            vehicles += "| --- | --- | --- | --- | --- | --- | --- | --- |\n"

            # Process each vehicle
            for vehicle in vehicle_data:
                if "vin" not in vehicle:
                    continue

                # Find the VIN decoding for this vehicle
                decoded_info = next(
                    (
                        decoded
                        for decoded in vin_decodings
                        if decoded["vin"] == vehicle["vin"]
                    ),
                    {},
                )

                # Initialize additional data fields
                battery_level = "N/A"
                vehicle_status = vehicle.get("state", "Unknown")
                climate_info = "N/A"
                odometer = "N/A"

                # Only fetch additional data if vehicle is online
                if vehicle.get("state") == "online":
                    try:
                        # Get vehicle data
                        vehicle_id = vehicle["id_s"]
                        vehicle_data_url = (
                            f"{self.api_base_url}/vehicles/{vehicle_id}/vehicle_data"
                        )
                        vehicle_response = requests.get(
                            vehicle_data_url, headers=headers
                        )

                        if vehicle_response.status_code == 200:
                            v_data = vehicle_response.json().get("response", {})

                            # Extract battery info
                            charge_state = v_data.get("charge_state", {})
                            if charge_state:
                                battery_level = (
                                    f"{charge_state.get('battery_level', 'N/A')}%"
                                )
                                vehicle_status = charge_state.get(
                                    "charging_state", vehicle_status
                                )

                            # Extract climate info
                            climate_state = v_data.get("climate_state", {})
                            if climate_state:
                                is_climate_on = climate_state.get(
                                    "is_climate_on", False
                                )
                                inside_temp = climate_state.get("inside_temp")
                                temp_units = (
                                    "°F"
                                    if v_data.get("gui_settings", {}).get(
                                        "gui_temperature_units"
                                    )
                                    == "F"
                                    else "°C"
                                )

                                if inside_temp is not None:
                                    climate_info = f"{'On' if is_climate_on else 'Off'} ({inside_temp}{temp_units})"
                                else:
                                    climate_info = "On" if is_climate_on else "Off"

                            # Extract odometer
                            vehicle_state = v_data.get("vehicle_state", {})
                            if (
                                vehicle_state
                                and vehicle_state.get("odometer") is not None
                            ):
                                odometer_value = vehicle_state.get("odometer")
                                distance_units = (
                                    v_data.get("gui_settings", {})
                                    .get("gui_distance_units", "mi/hr")
                                    .split("/")[0]
                                )
                                odometer = f"{odometer_value:.1f} {distance_units}"

                    except Exception as e:
                        logging.error(
                            f"Error getting data for vehicle {vehicle.get('id_s')}: {str(e)}"
                        )

                # Add row to table
                vehicles += (
                    f"| {vehicle['vin']} | "
                    f"{decoded_info.get('model', 'Unknown')} | "
                    f"{decoded_info.get('model_year', 'Unknown')} | "
                    f"{decoded_info.get('full_description', 'Unknown')} | "
                    f"{battery_level} | "
                    f"{vehicle_status} | "
                    f"{climate_info} | "
                    f"{odometer} |\n"
                )

            return vehicles
        except Exception as e:
            logging.error(f"Error getting vehicles: {str(e)}")
            return {"error": str(e)}

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
