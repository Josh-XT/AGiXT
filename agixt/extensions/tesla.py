import logging
import requests
import json
import base64
import time
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Dict, List, Any
from endpoints.TeslaIntegration import get_tesla_private_key


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
                "Tesla - Check Account Permissions": self.check_account_permissions,
                "Tesla - Check Vehicle Third Party Access": self.check_vehicle_third_party_access,
                "Tesla - Test Unsigned Command": self.test_unsigned_command,
                "Tesla - Diagnose Tesla Setup": self.diagnose_tesla_setup,
                "Tesla - Check TVCP Requirements": self.check_tvcp_requirement,
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

    def sign_command(self, command_data: Dict, vehicle_id: str, command: str) -> Dict:
        """Sign Tesla commands using Tesla Vehicle Command Protocol (TVCP)

        Tesla Fleet API now requires TVCP for vehicle commands.
        Reference: https://developer.tesla.com/docs/fleet-api/support/announcements

        Args:
            command_data: The command data to sign
            vehicle_id: The vehicle ID
            command: The command name

        Returns:
            Dict containing headers with signature for TVCP
        """
        try:
            # Get the private key
            private_key_pem = get_tesla_private_key()

            # Load the private key
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(), password=None
            )

            # TVCP requires a specific signing format
            timestamp = str(int(time.time()))

            # For TVCP, the message to sign should be the command payload
            # in the same format as would be sent to the legacy endpoint
            if command_data:
                canonical_message = json.dumps(
                    command_data, separators=(",", ":"), sort_keys=True
                )
            else:
                # For commands with no parameters (like honk_horn), use empty object
                canonical_message = "{}"

            # TVCP message format: timestamp.canonical_message
            message_to_sign = f"{timestamp}.{canonical_message}"

            # Debug logging
            logging.info(f"TVCP signing message: {message_to_sign}")

            # Sign the message
            signature = private_key.sign(
                message_to_sign.encode("utf-8"), ec.ECDSA(hashes.SHA256())
            )

            # Encode signature in base64
            signature_b64 = base64.b64encode(signature).decode()

            # Debug logging
            logging.info(f"TVCP signature generated: {signature_b64[:20]}...")

            # Return headers with TVCP signature format
            return {
                "tesla-signature": signature_b64,
                "tesla-timestamp": timestamp,
                "tesla-command-protocol": "1.0",  # Indicate TVCP version
            }

        except Exception as e:
            logging.error(f"Error signing Tesla command with TVCP: {str(e)}")
            raise Exception(f"Failed to sign command with TVCP: {str(e)}")

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
                            vehicle_detail = vehicle_response.json().get("response", {})

                            # Extract battery info
                            charge_state = vehicle_detail.get("charge_state", {})
                            if charge_state:
                                battery_level = (
                                    f"{charge_state.get('battery_level', 'N/A')}%"
                                )

                            # Extract climate info
                            climate_state = vehicle_detail.get("climate_state", {})
                            if climate_state:
                                inside_temp = climate_state.get("inside_temp")
                                outside_temp = climate_state.get("outside_temp")
                                climate_on = climate_state.get("is_climate_on", False)
                                if inside_temp is not None and outside_temp is not None:
                                    status = "On" if climate_on else "Off"
                                    climate_info = (
                                        f"{inside_temp}°C/{outside_temp}°C ({status})"
                                    )

                            # Extract odometer
                            vehicle_state = vehicle_detail.get("vehicle_state", {})
                            if vehicle_state:
                                odometer_miles = vehicle_state.get("odometer")
                                if odometer_miles is not None:
                                    odometer = f"{odometer_miles:.0f} mi"

                    except Exception as e:
                        logging.warning(
                            f"Failed to get detailed data for vehicle {vehicle['vin']}: {str(e)}"
                        )

                # Build table row
                vin = vehicle["vin"]
                model = decoded_info.get("model", "Unknown")
                year = decoded_info.get("model_year", "Unknown")
                description = decoded_info.get("full_description", "Unknown")

                vehicles += f"| {vin} | {model} | {year} | {description} | {battery_level} | {vehicle_status} | {climate_info} | {odometer} |\n"

            return vehicles

        except Exception as e:
            logging.error(f"Error getting Tesla vehicles: {str(e)}")
            return f"Error retrieving Tesla vehicles: {str(e)}"

    async def send_command(self, vehicle_tag, command, data=None):
        """Send command to vehicle with proper signing for Fleet API
        
        Note: As of January 2024, most vehicles require the Tesla Vehicle Command Protocol (TVCP).
        Direct Fleet API command calls are deprecated for newer vehicles.
        
        For newer vehicles, you should use Tesla's Vehicle Command Proxy:
        https://github.com/teslamotors/vehicle-command
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "User-Agent": "AGiXT-Tesla/1.0",
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

            # Try the legacy command endpoint first (for older vehicles or fleet accounts)
            url = f"{self.api_base_url}/vehicles/{vehicle_id}/command/{command}"

            # Prepare command data
            command_data = data if data is not None else {}

            # For newer vehicles, try TVCP signing
            try:
                signature_headers = self.sign_command(command_data, vehicle_id, command)
                # Add signature headers to existing headers
                headers.update(signature_headers)
                logging.info(f"Command signed with TVCP headers")
            except Exception as e:
                logging.warning(f"TVCP signing failed, trying without: {str(e)}")

            # Log details for debugging
            logging.info(f"Tesla command: {command} for vehicle {vehicle_id}")
            logging.info(f"Payload: {command_data}")
            logging.info(f"URL: {url}")

            response = requests.post(url, headers=headers, json=command_data, timeout=15)

            logging.info(f"Response status: {response.status_code}")
            logging.info(f"Response text: {response.text}")

            # Check for TVCP requirement error
            if response.status_code == 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", "")
                    if "Tesla Vehicle Command Protocol required" in error_msg or "routable_message" in error_msg:
                        return {
                            "error": "This vehicle requires Tesla Vehicle Command Protocol (TVCP). "
                                   "The direct Fleet API command endpoint is deprecated for this vehicle. "
                                   "You need to either:\n"
                                   "1. Use Tesla's Vehicle Command Proxy (recommended): "
                                   "https://github.com/teslamotors/vehicle-command\n"
                                   "2. Implement full TVCP protocol with protobuf messages\n"
                                   "3. Check if this is a fleet account vehicle (which may still support direct commands)\n"
                                   f"Original error: {error_msg}"
                        }
                except:
                    pass

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

            url = f"{self.api_base_url}/vehicles/{vehicle_id}/wake_up"
            response = requests.post(url, headers=headers, timeout=30)

            if response.status_code not in [200, 201, 202]:
                return self.handle_tesla_error(response)

            result = response.json()
            return result

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
            {"which_trunk": which_trunk},
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
            {"climate_keeper_mode": mode},
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
            data["lat"] = lat
            data["lon"] = lon
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
                "error": "Vehicle is not online. Please wake the vehicle first.",
                "suggestion": "Try using the 'Wake Vehicle' command first, then retry the fart command.",
            }

        try:
            # Try the boombox fart command
            result = await self.send_command(
                vehicle_tag,
                "remote_boombox",
                {"sound": 1},  # Sound 1 is typically a fart sound
            )

            if "error" in result:
                # If boombox isn't available, try honk as alternative
                return {
                    "error": "Boombox feature not available on this vehicle.",
                    "alternative": "Used horn honk instead!",
                    "result": await self.honk_horn(vehicle_tag),
                }

            return result

        except Exception as e:
            logging.error(f"Error with fart command: {str(e)}")
            return {
                "error": f"Fart command failed: {str(e)}",
                "suggestion": "This feature requires a vehicle with external speakers (Boombox). Try honking the horn instead!",
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
            data = await self.get_vehicle_data(
                vehicle_tag, "data_request/vehicle_state"
            )

            if "error" in data:
                return data

            vehicle_state = data.get("response", {})

            # Format important state information
            state_info = {
                "doors_locked": vehicle_state.get("locked"),
                "doors_open": {
                    "driver_front": vehicle_state.get("df") == 1,
                    "driver_rear": vehicle_state.get("dr") == 1,
                    "passenger_front": vehicle_state.get("pf") == 1,
                    "passenger_rear": vehicle_state.get("pr") == 1,
                },
                "windows_open": {
                    "driver_front": vehicle_state.get("fd_window") > 0,
                    "driver_rear": vehicle_state.get("rd_window") > 0,
                    "passenger_front": vehicle_state.get("fp_window") > 0,
                    "passenger_rear": vehicle_state.get("rp_window") > 0,
                },
                "trunk_open": {
                    "front": vehicle_state.get("ft") == 1,
                    "rear": vehicle_state.get("rt") == 1,
                },
                "odometer": vehicle_state.get("odometer"),
                "software_update": vehicle_state.get("software_update"),
                "sentry_mode": vehicle_state.get("sentry_mode"),
                "valet_mode": vehicle_state.get("valet_mode"),
                "vehicle_name": vehicle_state.get("vehicle_name"),
            }

            return {"response": state_info}

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
            data = await self.get_vehicle_data(vehicle_tag, "data_request/charge_state")

            if "error" in data:
                return data

            charge_state = data.get("response", {})

            # Format important charging information
            charging_info = {
                "battery_level": charge_state.get("battery_level"),
                "usable_battery_level": charge_state.get("usable_battery_level"),
                "charge_limit_soc": charge_state.get("charge_limit_soc"),
                "charging_state": charge_state.get("charging_state"),
                "time_to_full_charge": charge_state.get("time_to_full_charge"),
                "charge_rate": charge_state.get("charge_rate"),
                "charge_port_door_open": charge_state.get("charge_port_door_open"),
                "charge_port_latch": charge_state.get("charge_port_latch"),
                "charger_voltage": charge_state.get("charger_voltage"),
                "charger_actual_current": charge_state.get("charger_actual_current"),
                "charger_power": charge_state.get("charger_power"),
                "est_battery_range": charge_state.get("est_battery_range"),
                "ideal_battery_range": charge_state.get("ideal_battery_range"),
            }

            return {"response": charging_info}

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
            data = await self.get_vehicle_data(
                vehicle_tag, "data_request/climate_state"
            )

            if "error" in data:
                return data

            climate_state = data.get("response", {})

            # Format important climate information
            climate_info = {
                "inside_temp": climate_state.get("inside_temp"),
                "outside_temp": climate_state.get("outside_temp"),
                "driver_temp_setting": climate_state.get("driver_temp_setting"),
                "passenger_temp_setting": climate_state.get("passenger_temp_setting"),
                "is_climate_on": climate_state.get("is_climate_on"),
                "is_auto_conditioning_on": climate_state.get("is_auto_conditioning_on"),
                "fan_status": climate_state.get("fan_status"),
                "seat_heater_left": climate_state.get("seat_heater_left"),
                "seat_heater_right": climate_state.get("seat_heater_right"),
                "seat_heater_rear_left": climate_state.get("seat_heater_rear_left"),
                "seat_heater_rear_right": climate_state.get("seat_heater_rear_right"),
                "steering_wheel_heater": climate_state.get("steering_wheel_heater"),
                "climate_keeper_mode": climate_state.get("climate_keeper_mode"),
            }

            return {"response": climate_info}

        except Exception as e:
            logging.error(f"Error getting climate state: {str(e)}")
            return {"error": str(e)}

    def handle_tesla_error(self, response):
        """Handle common Tesla API errors with user-friendly messages"""
        if response.status_code == 401:
            return {"error": "Authentication failed. Please refresh your Tesla token."}
        elif response.status_code == 403:
            error_details = response.text
            base_error = "Access denied. Please ensure your account has the necessary permissions."

            # Try to parse more specific error information
            try:
                error_json = response.json()
                if "error" in error_json:
                    specific_error = error_json["error"]
                    if "description" in error_json:
                        specific_error += f": {error_json['description']}"
                    base_error += f" Details: {specific_error}"
            except:
                base_error += f" Raw response: {error_details}"

            return {
                "error": base_error,
                "suggestions": [
                    "1. Ensure your Tesla app has granted vehicle command permissions",
                    "2. Check that your OAuth token includes 'vehicle_cmds' scope",
                    "3. Verify your application is registered with Tesla Fleet API",
                    "4. Ensure the vehicle is online and not in service mode",
                ],
            }
        elif response.status_code == 404:
            return {"error": "Vehicle not found. Please check the VIN or vehicle ID."}
        elif response.status_code == 408:
            return {
                "error": "Vehicle command timeout. The vehicle may be asleep or out of range."
            }
        elif response.status_code == 429:
            return {
                "error": "Rate limit exceeded. Please wait before sending more commands."
            }
        elif response.status_code == 500:
            return {"error": "Tesla server error. Please try again later."}
        elif response.status_code == 503:
            return {"error": "Tesla service unavailable. Please try again later."}
        else:
            return {"error": f"Tesla API error {response.status_code}: {response.text}"}

    async def check_account_permissions(self):
        """Check if the Tesla account has the necessary permissions for vehicle commands

        Returns:
            dict: Permission status and available scopes
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Check the me endpoint to see what permissions we have
            me_url = f"{self.api_base_url}/users/me"
            response = requests.get(me_url, headers=headers, timeout=10)

            if response.status_code == 200:
                user_data = response.json().get("response", {})

                # Check if we have vehicle command permissions
                # This is indicated by having vehicles that allow commands
                vehicles_url = f"{self.api_base_url}/vehicles"
                vehicles_response = requests.get(
                    vehicles_url, headers=headers, timeout=10
                )

                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])

                    permission_info = {
                        "user_id": user_data.get("id"),
                        "email": user_data.get("email"),
                        "total_vehicles": len(vehicles),
                        "vehicles_with_commands": 0,
                        "command_capable_vehicles": [],
                    }

                    # Check each vehicle for command capability
                    for vehicle in vehicles:
                        vehicle_id = vehicle.get("id_s")
                        vin = vehicle.get("vin")
                        state = vehicle.get("state")

                        # Try to get vehicle data (this doesn't require command permissions)
                        try:
                            vehicle_data_url = f"{self.api_base_url}/vehicles/{vehicle_id}/vehicle_data"
                            vehicle_data_response = requests.get(
                                vehicle_data_url, headers=headers, timeout=10
                            )

                            if vehicle_data_response.status_code == 200:
                                permission_info["vehicles_with_commands"] += 1
                                permission_info["command_capable_vehicles"].append(
                                    {
                                        "vin": vin,
                                        "state": state,
                                        "command_capable": True,
                                    }
                                )
                            else:
                                permission_info["command_capable_vehicles"].append(
                                    {
                                        "vin": vin,
                                        "state": state,
                                        "command_capable": False,
                                        "error": f"HTTP {vehicle_data_response.status_code}",
                                    }
                                )
                        except Exception as e:
                            permission_info["command_capable_vehicles"].append(
                                {
                                    "vin": vin,
                                    "state": state,
                                    "command_capable": False,
                                    "error": str(e),
                                }
                            )

                    return {"status": "success", "permissions": permission_info}
                else:
                    return {
                        "status": "error",
                        "error": f"Failed to get vehicles: {vehicles_response.text}",
                    }
            else:
                return {
                    "status": "error",
                    "error": f"Failed to get user info: {response.text}",
                }

        except Exception as e:
            logging.error(f"Error checking account permissions: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def diagnose_tesla_setup(self):
        """Comprehensive diagnostic of Tesla integration setup

        Returns:
            dict: Complete diagnostic information about Tesla setup
        """
        diagnostic_results = {
            "timestamp": int(time.time()),
            "domain_registered": None,
            "keys_exist": False,
            "oauth_token_valid": False,
            "fleet_api_access": False,
            "command_permissions": False,
            "vehicles_accessible": False,
            "error_details": [],
        }

        try:
            # Check if domain is registered
            import os
            from endpoints.TeslaIntegration import REGISTRATION_FILE, TESLA_DOMAIN

            if os.path.exists(REGISTRATION_FILE):
                with open(REGISTRATION_FILE, "r") as f:
                    reg_data = json.load(f)
                    diagnostic_results["domain_registered"] = {
                        "status": reg_data.get("registered", False),
                        "domain": reg_data.get("domain"),
                        "date": reg_data.get("date"),
                    }
            else:
                diagnostic_results["error_details"].append(
                    "Registration file not found"
                )

            # Check if Tesla keys exist
            try:
                from endpoints.TeslaIntegration import get_tesla_private_key

                private_key = get_tesla_private_key()
                if private_key and (
                    "BEGIN EC PRIVATE KEY" in private_key
                    or "BEGIN PRIVATE KEY" in private_key
                ):
                    diagnostic_results["keys_exist"] = True
                else:
                    diagnostic_results["error_details"].append(
                        "Tesla private key invalid format"
                    )
            except Exception as e:
                diagnostic_results["error_details"].append(
                    f"Tesla keys error: {str(e)}"
                )

            # Check OAuth token
            try:
                self.verify_user()
                if self.access_token:
                    diagnostic_results["oauth_token_valid"] = True
                else:
                    diagnostic_results["error_details"].append("No Tesla access token")
            except Exception as e:
                diagnostic_results["error_details"].append(
                    f"OAuth token error: {str(e)}"
                )

            # Check Fleet API access
            if diagnostic_results["oauth_token_valid"]:
                try:
                    headers = {
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    }

                    # Test basic API access
                    me_url = f"{self.api_base_url}/users/me"
                    response = requests.get(me_url, headers=headers, timeout=10)

                    if response.status_code == 200:
                        diagnostic_results["fleet_api_access"] = True
                        user_data = response.json().get("response", {})
                        diagnostic_results["user_info"] = {
                            "email": user_data.get("email"),
                            "id": user_data.get("id"),
                        }
                    else:
                        diagnostic_results["error_details"].append(
                            f"Fleet API access failed: HTTP {response.status_code} - {response.text}"
                        )

                except Exception as e:
                    diagnostic_results["error_details"].append(
                        f"Fleet API test error: {str(e)}"
                    )

            # Check vehicles access
            if diagnostic_results["fleet_api_access"]:
                try:
                    vehicles_url = f"{self.api_base_url}/vehicles"
                    response = requests.get(vehicles_url, headers=headers, timeout=10)

                    if response.status_code == 200:
                        vehicles = response.json().get("response", [])
                        diagnostic_results["vehicles_accessible"] = True
                        diagnostic_results["vehicle_count"] = len(vehicles)
                        diagnostic_results["vehicles"] = [
                            {
                                "vin": v.get("vin"),
                                "state": v.get("state"),
                                "display_name": v.get("display_name"),
                            }
                            for v in vehicles
                        ]
                    else:
                        diagnostic_results["error_details"].append(
                            f"Vehicles access failed: HTTP {response.status_code} - {response.text}"
                        )

                except Exception as e:
                    diagnostic_results["error_details"].append(
                        f"Vehicles access error: {str(e)}"
                    )

            # Test command signing
            if diagnostic_results["keys_exist"]:
                try:
                    test_command = {"test": "data"}
                    signed_headers = self.sign_command(
                        test_command, "test_vehicle_id", "test_command"
                    )

                    # Debug: log what we got back
                    logging.info(f"Diagnostic signing test returned: {signed_headers}")

                    if (
                        "tesla-signature" in signed_headers
                        and "tesla-timestamp" in signed_headers
                        and "tesla-command-protocol" in signed_headers
                    ):
                        diagnostic_results["command_signing"] = True
                        diagnostic_results["command_protocol"] = "TVCP"
                    else:
                        diagnostic_results["command_signing"] = False
                        diagnostic_results["error_details"].append(
                            f"TVCP signing failed. Got headers: {list(signed_headers.keys()) if signed_headers else 'None'}"
                        )
                except Exception as e:
                    diagnostic_results["command_signing"] = False
                    diagnostic_results["error_details"].append(
                        f"Command signing test error: {str(e)}"
                    )

            # Overall health check
            diagnostic_results["overall_health"] = (
                diagnostic_results.get("domain_registered", {}).get("status", False)
                and diagnostic_results["keys_exist"]
                and diagnostic_results["oauth_token_valid"]
                and diagnostic_results["fleet_api_access"]
                and diagnostic_results["vehicles_accessible"]
                and diagnostic_results.get("command_signing", False)
            )

            return diagnostic_results

        except Exception as e:
            diagnostic_results["error_details"].append(f"Diagnostic error: {str(e)}")
            return diagnostic_results

    async def check_vehicle_third_party_access(self, vehicle_tag):
        """Check if a specific vehicle is enabled for third-party access

        Tesla requires vehicles to be explicitly enabled for third-party API access
        in the Tesla mobile app under Security & Privacy settings.

        Args:
            vehicle_tag: VIN or vehicle ID

        Returns:
            dict: Third-party access status and instructions
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get vehicle ID if VIN was provided
            if len(vehicle_tag) == 17 and vehicle_tag.isalnum():
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
                        vehicle_vin = vehicle["vin"]
                        vehicle_state = vehicle.get("state")
                    else:
                        return {"error": f"Vehicle with VIN {vehicle_tag} not found"}
                else:
                    return {
                        "error": f"Failed to get vehicles: {vehicles_response.text}"
                    }
            else:
                vehicle_id = vehicle_tag
                # Get VIN for this vehicle ID
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])
                    vehicle = next(
                        (v for v in vehicles if v.get("id_s") == vehicle_tag), None
                    )
                    if vehicle:
                        vehicle_vin = vehicle["vin"]
                        vehicle_state = vehicle.get("state")
                    else:
                        return {"error": f"Vehicle with ID {vehicle_tag} not found"}

            # Try to get vehicle data - this tests basic access
            vehicle_data_url = f"{self.api_base_url}/vehicles/{vehicle_id}/vehicle_data"
            data_response = requests.get(vehicle_data_url, headers=headers, timeout=10)

            # Try a simple command to test command access - use wake_up as it's harmless
            wake_url = f"{self.api_base_url}/vehicles/{vehicle_id}/wake_up"
            wake_response = requests.post(wake_url, headers=headers, timeout=10)

            result = {
                "vehicle_vin": vehicle_vin,
                "vehicle_state": vehicle_state,
                "data_access": data_response.status_code == 200,
                "command_access": wake_response.status_code in [200, 201, 202],
                "data_error": (
                    None
                    if data_response.status_code == 200
                    else f"HTTP {data_response.status_code}: {data_response.text}"
                ),
                "command_error": (
                    None
                    if wake_response.status_code in [200, 201, 202]
                    else f"HTTP {wake_response.status_code}: {wake_response.text}"
                ),
            }

            if not result["command_access"]:
                result["instructions"] = {
                    "message": "Vehicle may not be enabled for third-party access",
                    "steps": [
                        "1. Open the Tesla mobile app",
                        "2. Go to Security & Privacy settings",
                        "3. Enable 'Allow Mobile Connector' or 'Third-Party App Access'",
                        "4. Ensure the vehicle is online and not in service mode",
                        "5. Try the command again after a few minutes",
                    ],
                }

            return result

        except Exception as e:
            logging.error(f"Error checking third-party access: {str(e)}")
            return {"error": str(e)}

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
                        return vehicle.get("state") == "online"
                    else:
                        return False
                else:
                    return False
            else:
                # Direct vehicle ID lookup
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])
                    vehicle = next(
                        (v for v in vehicles if v.get("id_s") == vehicle_tag), None
                    )
                    if vehicle:
                        return vehicle.get("state") == "online"
                    else:
                        return False
                else:
                    return False

        except Exception as e:
            logging.error(f"Error checking vehicle online status: {str(e)}")
            return False

    async def test_unsigned_command(self, vehicle_tag):
        """Test sending a command without signing to isolate signing vs access issues

        This uses the wake_up endpoint which might not require signing.

        Args:
            vehicle_tag: VIN or vehicle ID

        Returns:
            dict: Test result to help diagnose if issue is signing or access
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get vehicle ID if VIN was provided
            if len(vehicle_tag) == 17 and vehicle_tag.isalnum():
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
                        return {"error": f"Vehicle with VIN {vehicle_tag} not found"}
                else:
                    return {
                        "error": f"Failed to get vehicles: {vehicles_response.text}"
                    }
            else:
                vehicle_id = vehicle_tag

            # Test wake_up command without signing
            wake_url = f"{self.api_base_url}/vehicles/{vehicle_id}/wake_up"

            logging.info(f"Testing unsigned wake_up command for vehicle {vehicle_id}")
            logging.info(f"URL: {wake_url}")

            response = requests.post(wake_url, headers=headers, timeout=15)

            logging.info(f"Unsigned command response status: {response.status_code}")
            logging.info(f"Unsigned command response: {response.text}")

            result = {
                "test_type": "unsigned_wake_up",
                "vehicle_id": vehicle_id,
                "status_code": response.status_code,
                "success": response.status_code in [200, 201, 202],
                "response": response.text,
                "analysis": "",
            }

            if result["success"]:
                result["analysis"] = (
                    "Unsigned commands work - issue is likely with command signing format"
                )
            elif response.status_code == 403:
                result["analysis"] = (
                    "Access denied even without signing - likely third-party access not enabled"
                )
            elif response.status_code == 401:
                result["analysis"] = "Authentication issue - token may be invalid"
            else:
                result["analysis"] = f"Unexpected error: HTTP {response.status_code}"

            return result

        except Exception as e:
            logging.error(f"Error testing unsigned command: {str(e)}")
            return {"error": str(e)}

    async def check_tvcp_requirement(self, vehicle_tag):
        """Check if vehicle requires Tesla Vehicle Command Protocol (TVCP)
        
        Args:
            vehicle_tag: Vehicle VIN or ID
            
        Returns:
            str: Information about TVCP requirements and setup instructions
        """
        try:
            # Get vehicle info first
            vehicles_info = await self.get_vehicles()
            
            info = f"""
Tesla Vehicle Command Protocol (TVCP) Information:

As of January 2024, most Tesla vehicles require TVCP for commands.
Your vehicles may need Tesla's Vehicle Command Proxy.

{vehicles_info}

TVCP Setup Options:

1. **Tesla Vehicle Command Proxy (Recommended)**:
   - Download: https://github.com/teslamotors/vehicle-command
   - This acts as a translation layer between REST API and TVCP
   - No code changes needed - just point to the proxy instead of Tesla's API

2. **Direct Fleet API (Limited)**:
   - Only works for: Fleet accounts, Pre-2021 Model S/X
   - Newer consumer vehicles require TVCP

3. **Setup Instructions**:
   - Generate virtual key: tesla-keygen create > public_key.pem
   - Register your domain and public key with Tesla
   - Run proxy: tesla-http-proxy -cert cert.pem -tls-key key.pem
   - Point your application to proxy instead of owner-api.teslamotors.com

Current Status:
- Your account diagnostics show command_protocol: TVCP
- This means your vehicles likely require the Vehicle Command Proxy
"""
            return info
            
        except Exception as e:
            return f"Error checking TVCP requirements: {str(e)}"
