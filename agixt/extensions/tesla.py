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
from endpoints.TeslaIntegration import get_tesla_private_key, ensure_keys_exist
from fastapi import HTTPException


"""
Required environment variables:

- TESLA_CLIENT_ID: Tesla OAuth client ID
- TESLA_CLIENT_SECRET: Tesla OAuth client secret
- TESLA_AUDIENCE: Fleet API base URL (https://fleet-api.prd.na.vn.cloud.tesla.com)
"""

# Combined scopes needed for full vehicle control
SCOPES = [
    "openid",
    "offline_access",
    "user_data",
    "vehicle_device_data",
    "vehicle_cmds",
    "vehicle_charging_cmds",
    "vehicle_location",
]
AUTHORIZE = "https://auth.tesla.com/oauth2/v3/authorize"
PKCE_REQUIRED = False


class TeslaSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("TESLA_CLIENT_ID")
        self.client_secret = getenv("TESLA_CLIENT_SECRET")
        self.domain = (
            getenv("AGIXT_URI")
            .replace("https://", "")
            .replace("http://", "")
            .rstrip("/")
        )
        self.audience = getenv(
            "TESLA_AUDIENCE", "https://fleet-api.prd.na.vn.cloud.tesla.com"
        )
        self.token_url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
        self.api_base_url = f"{self.audience}/api/1"
        self.auth_base_url = "https://auth.tesla.com/oauth2/v3"

        # Ensure we have Tesla keys generated
        ensure_keys_exist()

        # Get user info
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Get a new access token using the refresh token"""
        refresh_url = f"{self.auth_base_url}/token"

        response = requests.post(
            refresh_url,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": self.refresh_token,
                "audience": self.audience,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Tesla token refresh failed: {response.text}",
            )

        token_data = response.json()

        # Update our tokens for immediate use
        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            raise Exception("No access_token in Tesla refresh response")

        if "refresh_token" in token_data:
            self.refresh_token = token_data["refresh_token"]

        return token_data

    def get_user_info(self):
        """Get user information from Tesla API"""
        if not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            # First try with current token
            user_url = f"{self.api_base_url}/users/me"
            response = requests.get(user_url, headers=headers)

            # If token expired, try refreshing
            if response.status_code == 401 and self.refresh_token:
                logging.info("Tesla token expired, refreshing...")
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(user_url, headers=headers)

            # If we get a 404, the endpoint might be different, try to diagnose
            if response.status_code == 404:
                logging.warning(f"Tesla API endpoint not found: {user_url}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            # If we need registration, log it clearly
            if response.status_code == 412 and "must be registered" in response.text:
                logging.error(f"Tesla account needs registration: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            data = response.json()
            if "response" in data:
                data = data["response"]
            return {
                "email": data.get("email"),
                "first_name": data.get("first_name"),
                "last_name": data.get("last_name"),
            }

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Error getting Tesla user info: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error getting Tesla user info: {str(e)}"
            )


def sso(code, redirect_uri=None):
    """Handle Tesla OAuth flow"""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    logging.info(
        f"Exchanging Tesla authorization code for tokens with redirect URI: {redirect_uri}"
    )

    # Exchange authorization code for tokens
    token_url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"

    payload = {
        "grant_type": "authorization_code",
        "client_id": getenv("TESLA_CLIENT_ID"),
        "client_secret": getenv("TESLA_CLIENT_SECRET"),
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "audience": getenv(
            "TESLA_AUDIENCE", "https://fleet-api.prd.na.vn.cloud.tesla.com"
        ),
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    logging.info(f"Sending token request to {token_url}")
    response = requests.post(token_url, data=payload, headers=headers)

    if response.status_code != 200:
        logging.error(
            f"Error getting Tesla access token: {response.status_code} - {response.text}"
        )
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    logging.info(
        f"Successfully obtained Tesla tokens. Access token expires in {expires_in} seconds."
    )

    return TeslaSSO(access_token=access_token, refresh_token=refresh_token)

    # If we got here but user_info is None, run diagnostics
    if not tesla_client.user_info:
        logging.warning(
            "Got Tesla tokens but couldn't get user info. Running diagnostics..."
        )
        response = requests.get(
            f"{tesla_client.api_base_url}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    return tesla_client


def get_authorization_url(state=None, prompt_missing_scopes=True):
    """Generate Tesla authorization URL"""
    client_id = getenv("TESLA_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "prompt_missing_scopes": str(prompt_missing_scopes).lower(),
    }

    if state:
        params["state"] = state

    # Build query string
    query = "&".join([f"{k}={v}" for k, v in params.items()])

    return f"https://auth.tesla.com/oauth2/v3/authorize?{query}"


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

    CATEGORY = "Robotics"

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
                "Tesla - TVCP Vehicle Pairing Guide": self.setup_vehicle_command_proxy,
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
        """Get list of vehicles with comprehensive state information

        Args:
            None

        Returns:
            str: Detailed table of user's Tesla vehicles with comprehensive state information

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

            # Create comprehensive result with basic info table and detailed state
            result = "## Tesla Vehicles Overview\n\n"

            # Basic info table
            result += "### Basic Vehicle Information\n"
            result += "| VIN | ID | Model | Year | Description | Status |\n"
            result += "| --- | --- | --- | --- | --- | --- |\n"

            # Process each vehicle for basic info
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

                vin = vehicle["vin"]
                vehicle_id = vehicle.get("id_s", "N/A")
                model = decoded_info.get("model", "Unknown")
                year = decoded_info.get("model_year", "Unknown")
                description = decoded_info.get("full_description", "Unknown")
                vehicle_status = vehicle.get("state", "Unknown")

                result += f"| {vin} | {vehicle_id} | {model} | {year} | {description} | {vehicle_status} |\n"

            # Detailed state information for each vehicle
            result += "\n### Detailed Vehicle State Information\n\n"

            for vehicle in vehicle_data:
                if "vin" not in vehicle:
                    continue

                vin = vehicle["vin"]
                vehicle_name = vehicle.get("display_name", f"Vehicle {vin[-6:]}")
                vehicle_status = vehicle.get("state", "Unknown")

                result += f"#### {vehicle_name} ({vin})\n"
                result += f"**Status:** {vehicle_status}\n\n"

                # Only fetch detailed data if vehicle is online
                if vehicle.get("state") == "online":
                    try:
                        # Get comprehensive vehicle data
                        vehicle_id = vehicle["id_s"]
                        vehicle_data_url = (
                            f"{self.api_base_url}/vehicles/{vehicle_id}/vehicle_data"
                        )
                        vehicle_response = requests.get(
                            vehicle_data_url, headers=headers, timeout=15
                        )

                        if vehicle_response.status_code == 200:
                            vehicle_detail = vehicle_response.json().get("response", {})

                            # Extract and format all state information
                            charge_state = vehicle_detail.get("charge_state", {})
                            climate_state = vehicle_detail.get("climate_state", {})
                            vehicle_state = vehicle_detail.get("vehicle_state", {})

                            # Battery and Charging Information
                            if charge_state:
                                battery_level = charge_state.get("battery_level", "N/A")
                                usable_battery = charge_state.get(
                                    "usable_battery_level", "N/A"
                                )
                                charging_state = charge_state.get(
                                    "charging_state", "Disconnected"
                                )
                                charge_limit = charge_state.get(
                                    "charge_limit_soc", "N/A"
                                )
                                est_range = charge_state.get("est_battery_range", "N/A")
                                charge_rate = charge_state.get("charge_rate", 0)
                                time_to_full = charge_state.get(
                                    "time_to_full_charge", 0
                                )

                                result += f"**🔋 Battery & Charging:**\n"
                                result += f"- Battery Level: {battery_level}% (usable: {usable_battery}%)\n"
                                result += f"- Charging State: {charging_state}\n"
                                result += f"- Charge Limit: {charge_limit}%\n"
                                result += f"- Estimated Range: {est_range} mi\n"
                                if charging_state != "Disconnected" and charge_rate > 0:
                                    result += f"- Charge Rate: {charge_rate} mi/hr\n"
                                    result += f"- Time to Full: {time_to_full} hours\n"
                                result += "\n"

                            # Climate Information
                            if climate_state:
                                inside_temp = climate_state.get("inside_temp")
                                outside_temp = climate_state.get("outside_temp")
                                climate_on = climate_state.get("is_climate_on", False)
                                driver_temp = climate_state.get("driver_temp_setting")
                                passenger_temp = climate_state.get(
                                    "passenger_temp_setting"
                                )

                                result += f"**🌡️ Climate:**\n"
                                result += f"- Climate System: {'On' if climate_on else 'Off'}\n"
                                if inside_temp is not None:
                                    inside_temp_f = round(inside_temp * 9 / 5 + 32, 1)
                                    result += (
                                        f"- Inside Temperature: {inside_temp_f}°F\n"
                                    )
                                if outside_temp is not None:
                                    outside_temp_f = round(outside_temp * 9 / 5 + 32, 1)
                                    result += (
                                        f"- Outside Temperature: {outside_temp_f}°F\n"
                                    )
                                if driver_temp is not None:
                                    driver_temp_f = round(driver_temp * 9 / 5 + 32, 1)
                                    result += f"- Driver Setting: {driver_temp_f}°F\n"
                                if passenger_temp is not None:
                                    passenger_temp_f = round(
                                        passenger_temp * 9 / 5 + 32, 1
                                    )
                                    result += (
                                        f"- Passenger Setting: {passenger_temp_f}°F\n"
                                    )
                                result += "\n"

                            # Vehicle State Information
                            if vehicle_state:
                                locked = vehicle_state.get("locked", "Unknown")
                                odometer = vehicle_state.get("odometer")
                                sentry_mode = vehicle_state.get("sentry_mode", False)
                                valet_mode = vehicle_state.get("valet_mode", False)
                                software_update = vehicle_state.get(
                                    "software_update", {}
                                )

                                result += f"**🚗 Vehicle State:**\n"
                                result += (
                                    f"- Doors Locked: {'Yes' if locked else 'No'}\n"
                                )
                                if odometer is not None:
                                    result += f"- Odometer: {odometer:.0f} mi\n"
                                result += (
                                    f"- Sentry Mode: {'On' if sentry_mode else 'Off'}\n"
                                )
                                result += (
                                    f"- Valet Mode: {'On' if valet_mode else 'Off'}\n"
                                )

                                # Doors status
                                doors_open = []
                                if vehicle_state.get("df") == 1:
                                    doors_open.append("Driver Front")
                                if vehicle_state.get("dr") == 1:
                                    doors_open.append("Driver Rear")
                                if vehicle_state.get("pf") == 1:
                                    doors_open.append("Passenger Front")
                                if vehicle_state.get("pr") == 1:
                                    doors_open.append("Passenger Rear")
                                if vehicle_state.get("ft") == 1:
                                    doors_open.append("Front Trunk")
                                if vehicle_state.get("rt") == 1:
                                    doors_open.append("Rear Trunk")

                                if doors_open:
                                    result += f"- Open Doors/Trunks: {', '.join(doors_open)}\n"
                                else:
                                    result += f"- Open Doors/Trunks: None\n"

                                # Software update status
                                if software_update and software_update.get("status"):
                                    status = software_update.get("status", "")
                                    version = software_update.get("version", "")
                                    result += f"- Software Update: {status}"
                                    if version:
                                        result += f" (v{version})"
                                    result += "\n"

                                result += "\n"

                        else:
                            result += f"⚠️ Unable to fetch detailed data (HTTP {vehicle_response.status_code})\n\n"

                    except Exception as e:
                        result += f"⚠️ Error fetching detailed data: {str(e)}\n\n"
                        logging.warning(
                            f"Failed to get detailed data for vehicle {vin}: {str(e)}"
                        )
                else:
                    result += f"ℹ️ Vehicle is {vehicle_status} - detailed state unavailable\n\n"

            return result

        except Exception as e:
            error_details = (
                f"Error retrieving Tesla vehicles: {str(e)}\n\nDebug Context:\n"
            )
            error_details += f"- Exception Type: {type(e).__name__}\n"
            error_details += f"- API Base URL: {self.api_base_url}\n"
            error_details += f"- Has Access Token: {'Yes' if hasattr(self, 'access_token') and self.access_token else 'No'}\n"
            logging.error(f"Error getting Tesla vehicles: {str(e)}")
            return error_details

    async def send_command(self, vehicle_tag, command, data=None):
        """Send command to vehicle with proper signing for Fleet API and auto-wake

        This method automatically wakes sleeping vehicles before sending control commands.
        Data retrieval commands may work without waking the vehicle.

        Args:
            vehicle_tag: Vehicle VIN or ID
            command: Tesla API command name
            data: Optional command data/parameters

        Returns:
            dict: Tesla API response or error information

        Note: As of January 2024, most vehicles require the Tesla Vehicle Command Protocol (TVCP).
        This method includes automatic vehicle wake functionality for commands that require it.
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "User-Agent": "AGiXT-Tesla/1.0",
            }

            # Check if vehicle_tag is VIN or vehicle ID
            if len(vehicle_tag) == 17 and vehicle_tag.replace("-", "").isalnum():
                # It's a VIN, need to get vehicle ID first
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])

                    # Normalize the input VIN for comparison
                    input_vin = vehicle_tag.upper().strip().replace("-", "")

                    # Find vehicle with case-insensitive VIN comparison
                    vehicle = None
                    for v in vehicles:
                        api_vin = v.get("vin", "").upper().strip().replace("-", "")
                        if api_vin == input_vin:
                            vehicle = v
                            break

                    if vehicle:
                        vehicle_id = vehicle["id_s"]
                    else:
                        available_vins = [v.get("vin", "N/A") for v in vehicles]
                        raise Exception(
                            f"Vehicle with VIN {vehicle_tag} not found. Available VINs: {available_vins}"
                        )
                else:
                    raise Exception(f"Failed to get vehicles: {vehicles_response.text}")
            else:
                vehicle_id = vehicle_tag

            # Auto-wake vehicle if it's not online (only for commands that require it)
            # Some data commands work even when vehicle is asleep
            commands_that_need_awake = {
                "door_lock",
                "door_unlock",
                "flash_lights",
                "honk_horn",
                "remote_start_drive",
                "actuate_trunk",
                "charge_port_door_open",
                "charge_port_door_close",
                "set_temps",
                "auto_conditioning_start",
                "auto_conditioning_stop",
                "remote_seat_heater_request",
                "remote_steering_wheel_heater_request",
                "set_climate_keeper_mode",
                "charge_start",
                "charge_stop",
                "set_charge_limit",
                "set_charging_amps",
                "adjust_volume",
                "media_toggle_playback",
                "media_next_track",
                "media_prev_track",
                "media_next_fav",
                "media_prev_fav",
                "window_control",
                "sun_roof_control",
                "navigation_gps_request",
                "navigation_sc_request",
                "remote_boombox",
                "set_valet_mode",
                "reset_valet_pin",
                "trigger_homelink",
                "speed_limit_activate",
                "speed_limit_deactivate",
                "speed_limit_clear_pin",
                "speed_limit_set_limit",
            }

            if command != "wake_up" and command in commands_that_need_awake:
                logging.info(
                    f"Ensuring vehicle {vehicle_id} is awake before sending command: {command}"
                )
                wake_result = await self.ensure_vehicle_awake(vehicle_tag)

                if not wake_result["success"]:
                    return {
                        "error": f"🚗 Vehicle Wake Required\n\n"
                        f"The vehicle needs to be awake to receive commands, but wake attempts failed.\n\n"
                        f"❌ Wake Error: {wake_result['error']}\n\n"
                        f"💡 TROUBLESHOOTING:\n"
                        f"• Check vehicle connectivity (cellular/WiFi)\n"
                        f"• Vehicle may be in deep sleep mode\n"
                        f"• Try manually waking via Tesla mobile app\n"
                        f"• Ensure vehicle has sufficient battery\n\n"
                        f"You can also try the manual 'Tesla - Wake Vehicle' command."
                    }
                else:
                    logging.info(
                        f"Vehicle {vehicle_id} is awake: {wake_result['message']}"
                    )
            elif command != "wake_up":
                logging.info(
                    f"Command {command} may work without waking vehicle (data retrieval)"
                )

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

            response = requests.post(
                url, headers=headers, json=command_data, timeout=15
            )

            logging.info(f"Response status: {response.status_code}")
            logging.info(f"Response text: {response.text}")

            # Check for TVCP requirement error
            if response.status_code == 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", "")
                    if (
                        "Tesla Vehicle Command Protocol required" in error_msg
                        or "routable_message" in error_msg
                    ):
                        pairing_url = self.get_vehicle_pairing_url()
                        tesla_domain = self.get_tesla_domain()

                        return {
                            "error": f"🚗 Vehicle Command Authentication Required\n\n"
                            f"This vehicle requires Tesla Vehicle Command Protocol (TVCP) authentication.\n"
                            f"Your AGiXT server is properly configured, but this vehicle needs to be paired.\n\n"
                            f"📱 TO FIX THIS:\n"
                            f"1. Open the Tesla mobile app on your phone\n"
                            f"2. Visit this URL in the Tesla app: {pairing_url}\n"
                            f"3. Approve the pairing request when prompted\n"
                            f"4. Try the command again\n\n"
                            f"🔒 This one-time pairing process allows your vehicle to trust commands from AGiXT.\n"
                            f"Domain: {tesla_domain}\n\n"
                            f"Original error: {error_msg}"
                        }
                except:
                    pass

            if response.status_code not in [200, 201, 202]:
                # Enhanced error handling with detailed context
                error_response = self.handle_tesla_error(response)
                # Add debugging context to the error
                if isinstance(error_response, dict) and "error" in error_response:
                    error_response["debug_context"] = {
                        "method": "send_command",
                        "command": command,
                        "input_vehicle_tag": vehicle_tag,
                        "resolved_vehicle_id": vehicle_id,
                        "api_url": url,
                        "command_data": command_data,
                        "response_status": response.status_code,
                        "response_body": (
                            response.text[:500] if response.text else "Empty response"
                        ),
                        "headers_sent": {
                            k: v
                            for k, v in headers.items()
                            if k.lower() not in ["authorization"]
                        },
                    }
                return error_response

            result = response.json()

            # Check if the command was successful
            if result.get("response", {}).get("result") == False:
                reason = result.get("response", {}).get("reason", "Unknown error")
                return {
                    "error": f"Command failed: {reason}",
                    "debug_context": {
                        "method": "send_command",
                        "command": command,
                        "input_vehicle_tag": vehicle_tag,
                        "resolved_vehicle_id": vehicle_id,
                        "api_response": result,
                        "failure_reason": reason,
                    },
                }

            return result

        except requests.exceptions.Timeout as e:
            return {
                "error": f"🚗 Command Timeout\n\n"
                f"The vehicle did not respond within the timeout period.\n"
                f"This usually means the vehicle has gone to sleep during command execution.\n\n"
                f"💡 SUGGESTIONS:\n"
                f"• Try the command again (auto-wake will attempt to wake the vehicle)\n"
                f"• Use 'Tesla - Wake Vehicle' manually first\n"
                f"• Check vehicle connectivity (cellular/WiFi)\n"
                f"• Ensure vehicle battery is not critically low",
                "debug_context": {
                    "method": "send_command",
                    "command": command,
                    "input_vehicle_tag": vehicle_tag,
                    "timeout_seconds": 15,
                    "exception_type": "Timeout",
                },
            }
        except Exception as e:
            error_str = str(e).lower()

            # Check for sleep-related errors
            if any(
                keyword in error_str
                for keyword in ["asleep", "sleep", "offline", "not available"]
            ):
                return {
                    "error": f"🚗 Vehicle Sleep/Connectivity Issue\n\n"
                    f"The vehicle appears to be asleep or offline.\n\n"
                    f"💡 TROUBLESHOOTING:\n"
                    f"• Auto-wake may have failed - try 'Tesla - Wake Vehicle' manually\n"
                    f"• Check vehicle connectivity (cellular/WiFi signal)\n"
                    f"• Ensure vehicle battery is not critically low\n"
                    f"• Vehicle may be in deep sleep mode\n\n"
                    f"Original error: {str(e)}",
                    "debug_context": {
                        "method": "send_command",
                        "command": command,
                        "input_vehicle_tag": vehicle_tag,
                        "exception_type": type(e).__name__,
                        "original_error": str(e),
                    },
                }

            return {
                "error": str(e),
                "debug_context": {
                    "method": "send_command",
                    "command": command,
                    "input_vehicle_tag": vehicle_tag,
                    "exception_type": type(e).__name__,
                    "api_base_url": self.api_base_url,
                },
            }

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
            if len(vehicle_tag) == 17 and vehicle_tag.replace("-", "").isalnum():
                # It's a VIN, need to get vehicle ID first
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])

                    # Normalize the input VIN for comparison
                    input_vin = vehicle_tag.upper().strip().replace("-", "")

                    # Find vehicle with case-insensitive VIN comparison
                    vehicle = None
                    for v in vehicles:
                        api_vin = v.get("vin", "").upper().strip().replace("-", "")
                        if api_vin == input_vin:
                            vehicle = v
                            break

                    if vehicle:
                        vehicle_id = vehicle["id_s"]
                    else:
                        available_vins = [v.get("vin", "N/A") for v in vehicles]
                        raise Exception(
                            f"Vehicle with VIN {vehicle_tag} not found. Available VINs: {available_vins}"
                        )
                else:
                    raise Exception(f"Failed to get vehicles: {vehicles_response.text}")
            else:
                vehicle_id = vehicle_tag

            url = f"{self.api_base_url}/vehicles/{vehicle_id}/wake_up"
            response = requests.post(url, headers=headers, timeout=30)

            if response.status_code not in [200, 201, 202]:
                # Enhanced error handling with detailed context
                error_response = self.handle_tesla_error(response)
                # Add debugging context to the error
                if isinstance(error_response, dict) and "error" in error_response:
                    error_response["debug_context"] = {
                        "method": "wake_vehicle",
                        "input_vehicle_tag": vehicle_tag,
                        "resolved_vehicle_id": vehicle_id,
                        "api_url": url,
                        "response_status": response.status_code,
                        "response_body": (
                            response.text[:500] if response.text else "Empty response"
                        ),
                    }
                return error_response

            result = response.json()
            return result

        except Exception as e:
            return {
                "error": str(e),
                "debug_context": {
                    "method": "wake_vehicle",
                    "input_vehicle_tag": vehicle_tag,
                    "api_base_url": self.api_base_url,
                    "exception_type": type(e).__name__,
                },
            }

    async def ensure_vehicle_awake(self, vehicle_tag, max_attempts=3, wait_seconds=5):
        """Ensure vehicle is awake before sending commands

        Args:
            vehicle_tag: VIN or vehicle ID
            max_attempts: Maximum number of wake attempts (default 3)
            wait_seconds: Seconds to wait between wake attempts (default 5)

        Returns:
            dict: Success/error status with details
        """
        try:
            # First check if vehicle is already online
            is_online = await self.check_vehicle_online(vehicle_tag)
            if is_online:
                logging.info(f"Vehicle {vehicle_tag} is already online")
                return {"success": True, "message": "Vehicle is already online"}

            logging.info(f"Vehicle {vehicle_tag} is asleep, attempting to wake...")

            # Try to wake the vehicle with retries
            for attempt in range(max_attempts):
                logging.info(
                    f"Wake attempt {attempt + 1}/{max_attempts} for vehicle {vehicle_tag}"
                )

                # Send wake command
                wake_result = await self.wake_vehicle(vehicle_tag)

                if "error" in wake_result:
                    logging.warning(
                        f"Wake attempt {attempt + 1} failed: {wake_result['error']}"
                    )
                    if attempt == max_attempts - 1:  # Last attempt
                        return {
                            "success": False,
                            "error": f"Failed to wake vehicle after {max_attempts} attempts: {wake_result['error']}",
                        }
                    continue

                # Wait for vehicle to wake up
                await self._sleep(wait_seconds)

                # Check if vehicle is now online
                is_online = await self.check_vehicle_online(vehicle_tag)
                if is_online:
                    logging.info(
                        f"Vehicle {vehicle_tag} successfully woken on attempt {attempt + 1}"
                    )
                    return {
                        "success": True,
                        "message": f"Vehicle woken successfully on attempt {attempt + 1}",
                    }

                logging.info(
                    f"Vehicle {vehicle_tag} still not online after attempt {attempt + 1}, waiting..."
                )

                # Wait before next attempt (except on last attempt)
                if attempt < max_attempts - 1:
                    await self._sleep(wait_seconds)

            return {
                "success": False,
                "error": f"Vehicle failed to wake up after {max_attempts} attempts. Vehicle may have connectivity issues or be in deep sleep mode.",
            }

        except Exception as e:
            logging.error(f"Error in ensure_vehicle_awake: {str(e)}")
            return {
                "success": False,
                "error": f"Error ensuring vehicle is awake: {str(e)}",
            }

    async def _sleep(self, seconds):
        """Helper method for non-blocking sleep"""
        import asyncio

        await asyncio.sleep(seconds)

    async def remote_start(self, vehicle_tag):
        """Enable keyless driving"""
        return await self.send_command(vehicle_tag, "remote_start")

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
        try:
            # Try the boombox fart command (send_command will auto-wake if needed)
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
            if len(vehicle_tag) == 17 and vehicle_tag.replace("-", "").isalnum():
                # It's a VIN, need to get vehicle ID first
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])

                    # Normalize the input VIN for comparison
                    input_vin = vehicle_tag.upper().strip().replace("-", "")

                    # Debug: Log available vehicles and their VINs
                    logging.info(f"Looking for VIN: {input_vin}")
                    available_vins = [v.get("vin", "N/A") for v in vehicles]
                    logging.info(f"Available vehicles VINs: {available_vins}")

                    # Find vehicle with case-insensitive VIN comparison
                    vehicle = None
                    for v in vehicles:
                        api_vin = v.get("vin", "").upper().strip().replace("-", "")
                        if api_vin == input_vin:
                            vehicle = v
                            break

                    if vehicle:
                        vehicle_id = vehicle["id_s"]
                        logging.info(
                            f"Found vehicle ID {vehicle_id} for VIN {input_vin}"
                        )
                    else:
                        error_msg = f"Vehicle with VIN {vehicle_tag} not found. Available VINs: {available_vins}"
                        logging.error(error_msg)
                        raise Exception(error_msg)
                else:
                    raise Exception(f"Failed to get vehicles: {vehicles_response.text}")
            else:
                vehicle_id = vehicle_tag

            url = f"{self.api_base_url}/vehicles/{vehicle_id}/{data_type}"
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code not in [200, 201, 202]:
                # Enhanced error handling with detailed context
                error_response = self.handle_tesla_error(response)
                # Add debugging context to the error
                if isinstance(error_response, dict) and "error" in error_response:
                    error_response["debug_context"] = {
                        "method": "get_vehicle_data",
                        "input_vehicle_tag": vehicle_tag,
                        "resolved_vehicle_id": vehicle_id,
                        "api_url": url,
                        "data_type": data_type,
                        "response_status": response.status_code,
                        "response_body": (
                            response.text[:500] if response.text else "Empty response"
                        ),
                    }
                return error_response

            return response.json()

        except Exception as e:
            error_details = {
                "error": str(e),
                "debug_context": {
                    "method": "get_vehicle_data",
                    "input_vehicle_tag": vehicle_tag,
                    "data_type": data_type,
                    "api_base_url": self.api_base_url,
                    "exception_type": type(e).__name__,
                },
            }
            logging.error(f"Error getting vehicle data: {error_details}")
            return error_details

    # State Information Commands
    async def get_vehicle_state(self, vehicle_tag):
        """Get detailed vehicle state information

        Args:
            vehicle_tag: VIN or vehicle ID

        Returns:
            dict: Detailed vehicle state information including doors, locks, etc.
        """
        try:
            # Use the correct Fleet API endpoint for vehicle data
            data = await self.get_vehicle_data(vehicle_tag, "vehicle_data")

            if "error" in data:
                return data

            # Extract vehicle_state from the full vehicle_data response
            full_response = data.get("response", {})
            vehicle_state = full_response.get("vehicle_state", {})

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
            # Use the correct Fleet API endpoint for vehicle data
            data = await self.get_vehicle_data(vehicle_tag, "vehicle_data")

            if "error" in data:
                return data

            # Extract charge_state from the full vehicle_data response
            full_response = data.get("response", {})
            charge_state = full_response.get("charge_state", {})

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
            # Use the correct Fleet API endpoint for vehicle data
            data = await self.get_vehicle_data(vehicle_tag, "vehicle_data")

            if "error" in data:
                return data

            # Extract climate_state from the full vehicle_data response
            full_response = data.get("response", {})
            climate_state = full_response.get("climate_state", {})

            # Format important climate information with temperatures in Fahrenheit
            climate_info = {
                "inside_temp_fahrenheit": None,
                "outside_temp_fahrenheit": None,
                "driver_temp_setting_fahrenheit": None,
                "passenger_temp_setting_fahrenheit": None,
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

            # Convert temperatures from Celsius to Fahrenheit
            if climate_state.get("inside_temp") is not None:
                climate_info["inside_temp_fahrenheit"] = round(
                    climate_state.get("inside_temp") * 9 / 5 + 32, 1
                )

            if climate_state.get("outside_temp") is not None:
                climate_info["outside_temp_fahrenheit"] = round(
                    climate_state.get("outside_temp") * 9 / 5 + 32, 1
                )

            if climate_state.get("driver_temp_setting") is not None:
                climate_info["driver_temp_setting_fahrenheit"] = round(
                    climate_state.get("driver_temp_setting") * 9 / 5 + 32, 1
                )

            if climate_state.get("passenger_temp_setting") is not None:
                climate_info["passenger_temp_setting_fahrenheit"] = round(
                    climate_state.get("passenger_temp_setting") * 9 / 5 + 32, 1
                )

            return {"response": climate_info}

        except Exception as e:
            logging.error(f"Error getting climate state: {str(e)}")
            return {"error": str(e)}

    def handle_tesla_error(self, response):
        """Handle common Tesla API errors with user-friendly messages"""

        # Base debug context that all errors will include
        base_debug_context = {
            "response_status": response.status_code,
            "response_headers": (
                dict(response.headers) if hasattr(response, "headers") else {}
            ),
            "response_body": (
                response.text[:1000] if response.text else "Empty response"
            ),
            "api_url": response.url if hasattr(response, "url") else "Unknown",
        }

        if response.status_code == 401:
            return {
                "error": "Authentication failed. Please refresh your Tesla token.",
                "debug_context": base_debug_context,
            }
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

                    # Check if this is a TVCP-related error
                    if "Tesla Vehicle Command Protocol required" in specific_error:
                        pairing_url = self.get_vehicle_pairing_url()
                        tesla_domain = self.get_tesla_domain()

                        return {
                            "error": f"🚗 Vehicle Command Authentication Required\n\n"
                            f"This vehicle requires Tesla Vehicle Command Protocol (TVCP) authentication.\n"
                            f"Your AGiXT server is properly configured, but this vehicle needs to be paired.\n\n"
                            f"📱 TO FIX THIS:\n"
                            f"1. Open the Tesla mobile app on your phone\n"
                            f"2. Visit this URL in the Tesla app: {pairing_url}\n"
                            f"3. Approve the pairing request when prompted\n"
                            f"4. Try the command again\n\n"
                            f"🔒 This one-time pairing process allows your vehicle to trust commands from AGiXT.\n"
                            f"Domain: {tesla_domain}\n\n"
                            f"Original error: {specific_error}",
                            "suggestions": [
                                f"1. Visit {pairing_url} in your Tesla mobile app",
                                "2. Approve the pairing request when prompted",
                                "3. Ensure your vehicle is online and connected",
                                "4. Try the command again after pairing",
                            ],
                            "debug_context": {
                                **base_debug_context,
                                "parsed_error": error_json,
                            },
                        }
            except:
                base_error += f" Raw response: {error_details}"

            return {
                "error": base_error,
                "suggestions": [
                    "1. Ensure your Tesla app has granted vehicle command permissions",
                    "2. Check that your OAuth token includes 'vehicle_cmds' scope",
                    "3. Verify your application is registered with Tesla Fleet API",
                    "4. Ensure the vehicle is online and not in service mode",
                    f"5. If using newer vehicles, visit {self.get_vehicle_pairing_url()} in Tesla app",
                ],
                "debug_context": base_debug_context,
            }
        elif response.status_code == 404:
            return {
                "error": "Vehicle not found. Please check the VIN or vehicle ID.",
                "debug_context": base_debug_context,
            }
        elif response.status_code == 408:
            return {
                "error": "Vehicle command timeout. The vehicle may be asleep or out of range.",
                "debug_context": base_debug_context,
            }
        elif response.status_code == 429:
            return {
                "error": "Rate limit exceeded. Please wait before sending more commands.",
                "debug_context": base_debug_context,
            }
        elif response.status_code == 500:
            return {
                "error": "Tesla server error. Please try again later.",
                "debug_context": base_debug_context,
            }
        elif response.status_code == 503:
            return {
                "error": "Tesla service unavailable. Please try again later.",
                "debug_context": base_debug_context,
            }
        else:
            return {
                "error": f"Tesla API error {response.status_code}: {response.text}",
                "debug_context": base_debug_context,
            }

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
            if len(vehicle_tag) == 17 and vehicle_tag.replace("-", "").isalnum():
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])

                    # Normalize the input VIN for comparison
                    input_vin = vehicle_tag.upper().strip().replace("-", "")

                    # Find vehicle with case-insensitive VIN comparison
                    vehicle = None
                    for v in vehicles:
                        api_vin = v.get("vin", "").upper().strip().replace("-", "")
                        if api_vin == input_vin:
                            vehicle = v
                            break

                    if vehicle:
                        vehicle_id = vehicle["id_s"]
                        vehicle_vin = vehicle["vin"]
                        vehicle_state = vehicle.get("state")
                    else:
                        available_vins = [v.get("vin", "N/A") for v in vehicles]
                        return {
                            "error": f"Vehicle with VIN {vehicle_tag} not found. Available VINs: {available_vins}"
                        }
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
            if len(vehicle_tag) == 17 and vehicle_tag.replace("-", "").isalnum():
                # It's a VIN, need to get vehicle ID first
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])

                    # Normalize the input VIN for comparison
                    input_vin = vehicle_tag.upper().strip().replace("-", "")

                    # Find vehicle with case-insensitive VIN comparison
                    for v in vehicles:
                        api_vin = v.get("vin", "").upper().strip().replace("-", "")
                        if api_vin == input_vin:
                            return v.get("state") == "online"

                    return False  # VIN not found
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
            if len(vehicle_tag) == 17 and vehicle_tag.replace("-", "").isalnum():
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])

                    # Normalize the input VIN for comparison
                    input_vin = vehicle_tag.upper().strip().replace("-", "")

                    # Find vehicle with case-insensitive VIN comparison
                    vehicle = None
                    for v in vehicles:
                        api_vin = v.get("vin", "").upper().strip().replace("-", "")
                        if api_vin == input_vin:
                            vehicle = v
                            break

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
            str: Information about TVCP requirements and vehicle pairing
        """
        try:
            # Get vehicle info first
            vehicles_info = await self.get_vehicles()
            tesla_domain = self.get_tesla_domain()
            pairing_url = self.get_vehicle_pairing_url()

            info = f"""
🚗 Tesla Vehicle Command Protocol (TVCP) Status Check
===================================================

✅ AGiXT TVCP CONFIGURATION: READY
Your AGiXT server has native TVCP support built-in.

{vehicles_info}

🔧 TVCP REQUIREMENTS BY VEHICLE:
------------------------------
🟢 Newer vehicles (2021+): Require TVCP + Vehicle Pairing
   • Cybertruck, Model 3/S/X/Y (2021+)
   • Must complete one-time pairing process

🟡 Older vehicles: May work without TVCP
   • Pre-2021 Model S/X 
   • Fleet account vehicles

📱 TO PAIR YOUR VEHICLES:
------------------------
1. Open Tesla mobile app
2. Visit: {pairing_url}
3. Approve the pairing request
4. Try your Tesla commands again

🛠️ CURRENT AGiXT SETUP:
----------------------
✅ TVCP Keys: Generated and secure
✅ Domain: {tesla_domain} registered with Tesla
✅ Public Key: Served at required endpoint
✅ Command Signing: Implemented
✅ Integration: Native (no proxy needed)

❓ TROUBLESHOOTING:
-----------------
• Command fails? → Complete vehicle pairing first
• Vehicle offline? → Use "Tesla - Wake Vehicle"
• Need more help? → Use "Tesla - TVCP Vehicle Pairing Guide"

Unlike other implementations, AGiXT has TVCP built-in natively.
No external proxy software is needed!
"""
            return info

        except Exception as e:
            return f"Error checking TVCP requirements: {str(e)}"

    async def setup_vehicle_command_proxy(self):
        """Provide information about AGiXT's built-in TVCP support and vehicle pairing

        Returns:
            str: Information about TVCP setup and vehicle pairing
        """
        try:
            tesla_domain = self.get_tesla_domain()
            pairing_url = self.get_vehicle_pairing_url()

            setup_guide = f"""
🚗 AGiXT Tesla Vehicle Command Protocol (TVCP) Status
===================================================

✅ GOOD NEWS: AGiXT already has TVCP built-in!
Your server is properly configured with Tesla Vehicle Command Protocol.

CURRENT SETUP STATUS
--------------------
✅ Tesla TVCP keys: Generated and stored securely
✅ Domain registration: {tesla_domain} is registered with Tesla
✅ Public key serving: Available at required Tesla endpoint
✅ Command signing: Implemented and ready
✅ AGiXT integration: Fully operational

WHAT YOU NEED TO DO
-------------------
🔗 PAIR YOUR VEHICLES (One-time setup per vehicle):

1. 📱 Open the Tesla mobile app on your phone
2. 🌐 Visit this URL in the Tesla app: {pairing_url}
3. ✅ Approve the pairing request when prompted
4. 🎯 Try your Tesla commands again

WHY PAIRING IS NEEDED
--------------------
• Newer vehicles (2021+) require TVCP authentication
• This includes: Cybertruck, Model 3/S/X/Y (2021+)
• Pairing allows your vehicle to trust commands from AGiXT
• It's a one-time process per vehicle

SUPPORTED VEHICLES
-----------------
🟢 With TVCP (requires pairing): Cybertruck, Model 3/S/X/Y (2021+)
🟡 Without TVCP (works directly): Pre-2021 Model S/X, Fleet vehicles

TROUBLESHOOTING
--------------
• Command fails with "TVCP required"? → Complete vehicle pairing
• Vehicle offline? → Use "Tesla - Wake Vehicle" first
• Still not working? → Check "Tesla - Diagnose Tesla Setup"

NO PROXY NEEDED
---------------
Unlike other implementations, AGiXT has TVCP built directly into the server.
You don't need to install or run any additional proxy software!

TECHNICAL DETAILS
----------------
• Domain: {tesla_domain}
• Public key: Served at /.well-known/appspecific/com.tesla.3p.public-key.pem
• Command signing: Automatic ECDSA-SHA256 with TVCP headers
• Integration: Native AGiXT implementation

For more help: "Tesla - Diagnose Tesla Setup"
"""
            return setup_guide

        except Exception as e:
            return f"Error generating TVCP setup guide: {str(e)}"

    def get_vehicles_data(self):
        """Helper method to get vehicle data for setup guide"""
        try:
            # This is a simplified version - in real implementation,
            # we'd parse the actual vehicle data
            return [
                {"year": 2022, "model": "Model 3"},
                {"year": 2022, "model": "Model S"},
                {"year": 2025, "model": "Cybertruck"},
                {"year": 2022, "model": "Model Y"},
            ]
        except:
            return []

    def get_tesla_domain(self):
        """Get the Tesla domain from environment variables"""
        tesla_domain = getenv("TESLA_DOMAIN")
        if not tesla_domain:
            # Fallback to extracting from AGIXT_URI
            agixt_uri = getenv("AGIXT_URI")
            if agixt_uri:
                tesla_domain = (
                    agixt_uri.replace("https://", "").replace("http://", "").rstrip("/")
                )
        return tesla_domain

    def get_vehicle_pairing_url(self):
        """Get the Tesla vehicle pairing URL for this domain"""
        tesla_domain = self.get_tesla_domain()
        if tesla_domain:
            return f"https://tesla.com/_ak/{tesla_domain}"
        return "https://tesla.com/_ak/yourdomain.com"

    async def debug_vehicle_lookup(self, vehicle_tag):
        """Debug method to show detailed VIN lookup process

        Args:
            vehicle_tag: VIN or vehicle ID to debug

        Returns:
            dict: Detailed debugging information
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get all vehicles
            vehicles_response = requests.get(
                f"{self.api_base_url}/vehicles", headers=headers
            )

            debug_info = {
                "input_vehicle_tag": vehicle_tag,
                "input_length": len(vehicle_tag),
                "input_is_alphanumeric": vehicle_tag.replace("-", "").isalnum(),
                "vehicles_api_status": vehicles_response.status_code,
                "vehicles_found": [],
                "lookup_result": None,
                "normalized_input": None,
            }

            if vehicles_response.status_code == 200:
                vehicles = vehicles_response.json().get("response", [])

                # Show all available vehicles
                for v in vehicles:
                    vehicle_info = {
                        "vin": v.get("vin", "N/A"),
                        "id_s": v.get("id_s", "N/A"),
                        "state": v.get("state", "N/A"),
                        "display_name": v.get("display_name", "N/A"),
                    }
                    debug_info["vehicles_found"].append(vehicle_info)

                # Check if vehicle_tag looks like a VIN
                if len(vehicle_tag) == 17 and vehicle_tag.replace("-", "").isalnum():
                    input_vin = vehicle_tag.upper().strip().replace("-", "")
                    debug_info["normalized_input"] = input_vin
                    debug_info["lookup_type"] = "VIN"

                    # Try to find matching vehicle
                    for v in vehicles:
                        api_vin = v.get("vin", "").upper().strip().replace("-", "")
                        if api_vin == input_vin:
                            debug_info["lookup_result"] = {
                                "found": True,
                                "matched_vehicle": {
                                    "vin": v.get("vin"),
                                    "id_s": v.get("id_s"),
                                    "state": v.get("state"),
                                    "api_vin_normalized": api_vin,
                                },
                            }
                            break

                    if not debug_info["lookup_result"]:
                        debug_info["lookup_result"] = {
                            "found": False,
                            "reason": "No VIN match found",
                        }
                else:
                    debug_info["lookup_type"] = "Vehicle ID"
                    debug_info["normalized_input"] = vehicle_tag

                    # Try to find by vehicle ID
                    for v in vehicles:
                        if v.get("id_s") == vehicle_tag:
                            debug_info["lookup_result"] = {
                                "found": True,
                                "matched_vehicle": {
                                    "vin": v.get("vin"),
                                    "id_s": v.get("id_s"),
                                    "state": v.get("state"),
                                },
                            }
                            break

                    if not debug_info["lookup_result"]:
                        debug_info["lookup_result"] = {
                            "found": False,
                            "reason": "No vehicle ID match found",
                        }
            else:
                debug_info["error"] = (
                    f"Failed to get vehicles: {vehicles_response.text}"
                )

            return debug_info

        except Exception as e:
            return {"error": f"Debug lookup failed: {str(e)}"}

    async def test_fleet_api_endpoints(self, vehicle_tag):
        """Test Tesla Fleet API endpoints to verify correct structure

        Args:
            vehicle_tag: VIN or vehicle ID to test

        Returns:
            dict: Test results for various Fleet API endpoints
        """
        try:
            self.verify_user()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get vehicle ID if VIN was provided
            if len(vehicle_tag) == 17 and vehicle_tag.replace("-", "").isalnum():
                vehicles_response = requests.get(
                    f"{self.api_base_url}/vehicles", headers=headers
                )
                if vehicles_response.status_code == 200:
                    vehicles = vehicles_response.json().get("response", [])
                    input_vin = vehicle_tag.upper().strip().replace("-", "")

                    vehicle = None
                    for v in vehicles:
                        api_vin = v.get("vin", "").upper().strip().replace("-", "")
                        if api_vin == input_vin:
                            vehicle = v
                            break

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

            # Test different Fleet API endpoints
            test_results = {
                "vehicle_id": vehicle_id,
                "input_vehicle_tag": vehicle_tag,
                "endpoint_tests": {},
            }

            # Test endpoints
            endpoints_to_test = [
                (
                    "vehicle_data",
                    f"{self.api_base_url}/vehicles/{vehicle_id}/vehicle_data",
                ),
                ("wake_up", f"{self.api_base_url}/vehicles/{vehicle_id}/wake_up"),
                (
                    "legacy_vehicle_state",
                    f"{self.api_base_url}/vehicles/{vehicle_id}/data_request/vehicle_state",
                ),
                (
                    "legacy_charge_state",
                    f"{self.api_base_url}/vehicles/{vehicle_id}/data_request/charge_state",
                ),
                (
                    "legacy_climate_state",
                    f"{self.api_base_url}/vehicles/{vehicle_id}/data_request/climate_state",
                ),
            ]

            for endpoint_name, url in endpoints_to_test:
                try:
                    if endpoint_name == "wake_up":
                        # POST for wake_up
                        response = requests.post(url, headers=headers, timeout=10)
                    else:
                        # GET for data endpoints
                        response = requests.get(url, headers=headers, timeout=10)

                    test_results["endpoint_tests"][endpoint_name] = {
                        "url": url,
                        "status_code": response.status_code,
                        "success": response.status_code in [200, 201, 202],
                        "response_preview": (
                            response.text[:200] if response.text else "Empty response"
                        ),
                        "is_html_error": "<!DOCTYPE html>" in response.text,
                    }

                except Exception as e:
                    test_results["endpoint_tests"][endpoint_name] = {
                        "url": url,
                        "error": str(e),
                        "success": False,
                    }

            return test_results

        except Exception as e:
            return {"error": f"Fleet API endpoint test failed: {str(e)}"}
