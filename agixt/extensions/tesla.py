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
        "7G2": "Tesla USA (Cybertruck)",
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
        "E": "Truck",  # Updated for Cybertruck
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
        "E": "Tri Motor - AWD",  # Cybertruck Tri Motor
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

        # Cybertruck specific interpretations
        elif model_code == "C":
            # Cybertruck has different drivetrain interpretations
            if drivetrain_code == "E":
                # E = Dual Motor AWD for Cybertruck
                result["drivetrain"] = "Dual Motor - AWD"
                if battery_code == "D":
                    result["trim"] = "AWD"  # Standard dual motor
                else:
                    result["trim"] = "AWD"
            elif drivetrain_code == "F" or drivetrain_code == "D":
                # Tri-motor configurations (Cyberbeast)
                result["drivetrain"] = "Tri Motor - AWD"
                result["trim"] = "Cyberbeast"
            else:
                result["drivetrain"] = TeslaVINDecoder.DRIVETRAIN_CODES.get(
                    drivetrain_code, "Unknown Drivetrain"
                )
                if (
                    "Performance" in result["drivetrain"]
                    or "Tri Motor" in result["drivetrain"]
                ):
                    result["trim"] = "Cyberbeast"
                else:
                    result["trim"] = "AWD"

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

    @staticmethod
    def test_cybertruck_vin():
        """Test method for Cybertruck VIN decoding"""
        test_vin = "7G2CEHED8SA071826"
        result = TeslaVINDecoder.decode_vin(test_vin)
        return result


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
                "Tesla - Set Steering Wheel Heat": self.set_steering_wheel_heat,
                "Tesla - Set Climate Keeper": self.set_climate_keeper,
                # Charging Controls
                "Tesla - Start Charging": self.start_charging,
                "Tesla - Stop Charging": self.stop_charging,
                "Tesla - Set Charge Limit": self.set_charge_limit,
                "Tesla - Set Charging Amps": self.set_charging_amps,
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
                # Information Commands
                "Tesla - Get Vehicles": self.get_vehicles,
                "Tesla - Get Vehicle State": self.get_vehicle_state,
                "Tesla - Get Charge State": self.get_charge_state,
                "Tesla - Get Climate State": self.get_climate_state,
                "Tesla - Check Vehicle Online": self.check_vehicle_online,
                # Fun Commands
                "Tesla - Fart": self.fart,
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
                raise Exception(
                    f"Failed to get vehicles (HTTP {response.status_code}): {response.text}"
                )

            data = response.json()
            vehicle_data = data.get("response", [])

            if not vehicle_data:
                return "No Tesla vehicles found in your account."

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
                            vehicle_data_url, headers=headers, timeout=10
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
                        else:
                            logging.warning(
                                f"Failed to get vehicle data for {vehicle_id}: HTTP {vehicle_response.status_code}"
                            )

                    except requests.exceptions.Timeout:
                        logging.warning(
                            f"Timeout getting data for vehicle {vehicle.get('id_s')}"
                        )
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
            return f"Error retrieving vehicles: {str(e)}"

    async def send_command(self, vehicle_tag, command, data=None):
        """Send command to vehicle"""
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Check if vehicle_tag is VIN or vehicle ID
            if len(vehicle_tag) == 17 and vehicle_tag.isalnum():
                # It's a VIN, need to get vehicle ID first
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])
                    vehicle = next(
                        (v for v in vehicles if v.get("vin") == vehicle_tag), None
                    )
                    if vehicle:
                        vehicle_id = vehicle["id_s"]
                    else:
                        raise Exception(f"Vehicle with VIN {vehicle_tag} not found")
                else:
                    raise Exception(f"Failed to get vehicles: {vehicles_response.text}")
            else:
                vehicle_id = vehicle_tag

            url = f"{self.api_base_url}/vehicles/{vehicle_id}/command/{command}"

            if data:
                response = requests.post(url, headers=headers, json=data, timeout=15)
            else:
                response = requests.post(url, headers=headers, timeout=15)

            if response.status_code not in [200, 201, 202]:
                return self.handle_tesla_error(response)

            result = response.json()

            # Check if the command was successful
            if result.get("response", {}).get("result") == False:
                reason = result.get("response", {}).get("reason", "Unknown error")
                raise Exception(f"Command failed: {reason}")

            return result

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
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Check if vehicle_tag is VIN or vehicle ID
            if len(vehicle_tag) == 17 and vehicle_tag.isalnum():
                # It's a VIN, need to get vehicle ID first
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])
                    vehicle = next(
                        (v for v in vehicles if v.get("vin") == vehicle_tag), None
                    )
                    if vehicle:
                        vehicle_id = vehicle["id_s"]
                    else:
                        raise Exception(f"Vehicle with VIN {vehicle_tag} not found")
                else:
                    raise Exception(f"Failed to get vehicles: {vehicles_response.text}")
            else:
                vehicle_id = vehicle_tag

            # Wake up uses a different endpoint (POST to /vehicles/{id}/wake_up)
            url = f"{self.api_base_url}/vehicles/{vehicle_id}/wake_up"
            response = requests.post(url, headers=headers, timeout=15)

            if response.status_code not in [200, 201, 202]:
                return self.handle_tesla_error(response)

            return response.json()

        except Exception as e:
            logging.error(f"Error waking vehicle: {str(e)}")
            return {"error": str(e)}

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
        """Set seat heater level

        Args:
            vehicle_tag: VIN or vehicle ID
            seat_position: Seat position (0-8: 0=driver, 1=passenger, 2=rear_left, 4=rear_center, 5=rear_right, 6=third_row_left, 7=third_row_right)
            level: Heat level (0-3: 0=off, 1=low, 2=medium, 3=high)
        """
        return await self.send_command(
            vehicle_tag,
            "remote_seat_heater_request",
            {"heater": seat_position, "level": level},
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
        """Control windows (vent/close)

        Args:
            vehicle_tag: VIN or vehicle ID
            command: Window command ("vent" or "close")
            lat: Latitude for location verification (optional)
            lon: Longitude for location verification (optional)
        """
        data = {"command": command}
        if lat is not None and lon is not None:
            data.update({"lat": lat, "lon": lon})
        return await self.send_command(vehicle_tag, "window_control", data)

    async def control_sunroof(self, vehicle_tag, state):
        """Control sunroof (stop/close/vent)"""
        return await self.send_command(
            vehicle_tag, "sun_roof_control", {"state": state}
        )

    # Navigation
    async def navigate_to(self, vehicle_tag, lat, lon, order=0):
        """Navigate to coordinates

        Args:
            vehicle_tag: VIN or vehicle ID
            lat: Latitude coordinate
            lon: Longitude coordinate
            order: Waypoint order (default 0)
        """
        return await self.send_command(
            vehicle_tag,
            "navigation_gps_request",
            {"lat": lat, "lon": lon, "order": order},
        )

    async def navigate_to_supercharger(self, vehicle_tag, supercharger_id, order=0):
        """Navigate to supercharger

        Args:
            vehicle_tag: VIN or vehicle ID
            supercharger_id: Supercharger location ID
            order: Waypoint order (default 0)
        """
        return await self.send_command(
            vehicle_tag,
            "navigation_sc_request",
            {"id": supercharger_id, "order": order},
        )

    # Fun Commands
    async def fart(self, vehicle_tag):
        """Make the vehicle emit a fart sound

        Note: This command uses the vehicle's external speaker system (Boombox feature).
        This feature is only available on vehicles with external speakers and may require
        specific Tesla account permissions. If not available, this will suggest alternatives.

        Args:
            vehicle_tag: VIN or vehicle ID to identify the target vehicle

        Returns:
            dict: Response from Tesla API or helpful error message with alternatives
        """
        # First check if vehicle is online
        is_online = await self.check_vehicle_online(vehicle_tag)
        if not is_online:
            return {
                "error": "Vehicle is not online. Please wake the vehicle first using 'Tesla - Wake Vehicle'."
            }

        try:
            # Try the boombox command (requires external speakers)
            result = await self.send_command(
                vehicle_tag, "remote_boombox", {"sound": 1}
            )

            return result

        except Exception as e:
            error_msg = str(e)

            # Handle specific error cases with helpful messages
            if "Access denied" in error_msg or "403" in error_msg:
                return {
                    "error": "Fart sound not available on this vehicle or account.",
                    "reason": "This feature requires a vehicle with external speakers (Boombox) and appropriate Fleet API permissions.",
                    "alternatives": [
                        "Use 'Tesla - Honk Horn' for a fun sound effect",
                        "Use 'Tesla - Flash Lights' for a visual effect",
                        "Check if your vehicle has the Boombox feature in the Tesla mobile app",
                    ],
                }
            elif "404" in error_msg or "not found" in error_msg.lower():
                return {
                    "error": "Fart command not supported by this vehicle.",
                    "reason": "Your vehicle may not have external speakers or the Boombox feature.",
                    "alternatives": [
                        "Use 'Tesla - Honk Horn' instead",
                        "Use 'Tesla - Flash Lights' for a different fun effect",
                    ],
                }
            else:
                return {
                    "error": f"Fart command failed: {error_msg}",
                    "alternatives": [
                        "Try 'Tesla - Honk Horn' or 'Tesla - Flash Lights' instead"
                    ],
                }

    async def get_vehicle_data(self, vehicle_tag, data_type="vehicle_data"):
        """Get vehicle data from Tesla API

        Args:
            vehicle_tag: VIN or vehicle ID
            data_type: Type of data to retrieve (vehicle_data, charge_state, climate_state, etc.)

        Returns:
            dict: Vehicle data response
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Check if vehicle_tag is VIN or vehicle ID
            if len(vehicle_tag) == 17 and vehicle_tag.isalnum():
                # It's a VIN, need to get vehicle ID first
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])
                    vehicle = next(
                        (v for v in vehicles if v.get("vin") == vehicle_tag), None
                    )
                    if vehicle:
                        vehicle_id = vehicle["id_s"]
                    else:
                        raise Exception(f"Vehicle with VIN {vehicle_tag} not found")
                else:
                    raise Exception(f"Failed to get vehicles: {vehicles_response.text}")
            else:
                vehicle_id = vehicle_tag

            url = f"{self.api_base_url}/vehicles/{vehicle_id}/{data_type}"
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code not in [200, 201, 202]:
                return self.handle_tesla_error(response)

            return response.json()

        except Exception as e:
            logging.error(f"Error getting vehicle data: {str(e)}")
            return {"error": str(e)}

    # State Information Commands
    async def get_vehicle_state(self, vehicle_tag):
        """Get detailed vehicle state information

        Args:
            vehicle_tag: VIN or vehicle ID

        Returns:
            dict: Detailed vehicle state information including doors, locks, etc.
        """
        try:
            result = await self.get_vehicle_data(vehicle_tag, "vehicle_data")
            if "error" in result:
                return result

            vehicle_state = result.get("response", {}).get("vehicle_state", {})
            if not vehicle_state:
                return {"error": "No vehicle state data available"}

            # Format important state information
            state_info = {
                "doors_locked": vehicle_state.get("locked", "Unknown"),
                "doors_open": {
                    "driver_front": vehicle_state.get("df", 0) == 1,
                    "passenger_front": vehicle_state.get("pf", 0) == 1,
                    "driver_rear": vehicle_state.get("dr", 0) == 1,
                    "passenger_rear": vehicle_state.get("pr", 0) == 1,
                },
                "trunk_open": {
                    "front": vehicle_state.get("ft", 0) == 1,
                    "rear": vehicle_state.get("rt", 0) == 1,
                },
                "windows_open": {
                    "driver_front": vehicle_state.get("fd_window", 0) > 0,
                    "passenger_front": vehicle_state.get("fp_window", 0) > 0,
                    "driver_rear": vehicle_state.get("rd_window", 0) > 0,
                    "passenger_rear": vehicle_state.get("rp_window", 0) > 0,
                },
                "odometer": vehicle_state.get("odometer", "Unknown"),
                "software_update": vehicle_state.get("software_update", {}),
                "sentry_mode": vehicle_state.get("sentry_mode", "Unknown"),
            }

            return state_info

        except Exception as e:
            logging.error(f"Error getting vehicle state: {str(e)}")
            return {"error": str(e)}

    async def get_charge_state(self, vehicle_tag):
        """Get detailed charging state information

        Args:
            vehicle_tag: VIN or vehicle ID

        Returns:
            dict: Detailed charging state information
        """
        try:
            result = await self.get_vehicle_data(vehicle_tag, "vehicle_data")
            if "error" in result:
                return result

            charge_state = result.get("response", {}).get("charge_state", {})
            if not charge_state:
                return {"error": "No charge state data available"}

            # Format charging information
            charge_info = {
                "battery_level": f"{charge_state.get('battery_level', 'Unknown')}%",
                "usable_battery_level": f"{charge_state.get('usable_battery_level', 'Unknown')}%",
                "charge_limit_soc": f"{charge_state.get('charge_limit_soc', 'Unknown')}%",
                "charging_state": charge_state.get("charging_state", "Unknown"),
                "time_to_full_charge": f"{charge_state.get('time_to_full_charge', 'Unknown')} hours",
                "charge_rate": f"{charge_state.get('charge_rate', 'Unknown')} miles/hour",
                "charger_power": f"{charge_state.get('charger_power', 'Unknown')} kW",
                "charger_voltage": f"{charge_state.get('charger_voltage', 'Unknown')} V",
                "charger_actual_current": f"{charge_state.get('charger_actual_current', 'Unknown')} A",
                "charge_port_door_open": charge_state.get(
                    "charge_port_door_open", "Unknown"
                ),
                "est_battery_range": f"{charge_state.get('est_battery_range', 'Unknown')} miles",
                "ideal_battery_range": f"{charge_state.get('ideal_battery_range', 'Unknown')} miles",
            }

            return charge_info

        except Exception as e:
            logging.error(f"Error getting charge state: {str(e)}")
            return {"error": str(e)}

    async def get_climate_state(self, vehicle_tag):
        """Get detailed climate state information

        Args:
            vehicle_tag: VIN or vehicle ID

        Returns:
            dict: Detailed climate state information
        """
        try:
            result = await self.get_vehicle_data(vehicle_tag, "vehicle_data")
            if "error" in result:
                return result

            climate_state = result.get("response", {}).get("climate_state", {})
            if not climate_state:
                return {"error": "No climate state data available"}

            # Format climate information
            climate_info = {
                "is_climate_on": climate_state.get("is_climate_on", "Unknown"),
                "inside_temp": f"{climate_state.get('inside_temp', 'Unknown')}°C",
                "outside_temp": f"{climate_state.get('outside_temp', 'Unknown')}°C",
                "driver_temp_setting": f"{climate_state.get('driver_temp_setting', 'Unknown')}°C",
                "passenger_temp_setting": f"{climate_state.get('passenger_temp_setting', 'Unknown')}°C",
                "is_front_defroster_on": climate_state.get(
                    "is_front_defroster_on", "Unknown"
                ),
                "is_rear_defroster_on": climate_state.get(
                    "is_rear_defroster_on", "Unknown"
                ),
                "fan_status": climate_state.get("fan_status", "Unknown"),
                "seat_heater_left": climate_state.get("seat_heater_left", "Unknown"),
                "seat_heater_right": climate_state.get("seat_heater_right", "Unknown"),
                "seat_heater_rear_left": climate_state.get(
                    "seat_heater_rear_left", "Unknown"
                ),
                "seat_heater_rear_right": climate_state.get(
                    "seat_heater_rear_right", "Unknown"
                ),
                "steering_wheel_heater": climate_state.get(
                    "steering_wheel_heater", "Unknown"
                ),
                "climate_keeper_mode": climate_state.get(
                    "climate_keeper_mode", "Unknown"
                ),
            }

            return climate_info

        except Exception as e:
            logging.error(f"Error getting climate state: {str(e)}")
            return {"error": str(e)}

    def handle_tesla_error(self, response):
        """Handle common Tesla API errors with user-friendly messages"""
        if response.status_code == 401:
            return {
                "error": "Authentication failed. Please check your Tesla access token."
            }
        elif response.status_code == 403:
            return {
                "error": "Access denied. Please ensure your account has the necessary permissions."
            }
        elif response.status_code == 404:
            return {"error": "Vehicle not found. Please check the VIN or vehicle ID."}
        elif response.status_code == 408:
            return {
                "error": "Vehicle is not online or not responding. Try waking the vehicle first."
            }
        elif response.status_code == 429:
            return {
                "error": "Rate limit exceeded. Please wait before sending more commands."
            }
        elif response.status_code == 500:
            return {"error": "Tesla server error. Please try again later."}
        elif response.status_code == 503:
            return {
                "error": "Tesla service temporarily unavailable. Please try again later."
            }
        else:
            return {
                "error": f"Tesla API error (HTTP {response.status_code}): {response.text}"
            }

    async def check_vehicle_online(self, vehicle_tag):
        """Check if vehicle is online and ready to receive commands

        Args:
            vehicle_tag: VIN or vehicle ID

        Returns:
            bool: True if vehicle is online, False otherwise
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get vehicle status
            url = f"{self.api_base_url}/vehicles"
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                return False

            vehicles = response.json().get("response", [])

            # Find the vehicle
            if len(vehicle_tag) == 17 and vehicle_tag.isalnum():
                # It's a VIN
                vehicle = next(
                    (v for v in vehicles if v.get("vin") == vehicle_tag), None
                )
            else:
                # It's a vehicle ID
                vehicle = next(
                    (v for v in vehicles if v.get("id_s") == vehicle_tag), None
                )

            if not vehicle:
                return False

            return vehicle.get("state") == "online"

        except Exception as e:
            logging.error(f"Error checking vehicle online status: {str(e)}")
            return False
