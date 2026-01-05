import os
import time
import logging
import asyncio
import requests
from datetime import datetime, timedelta
from Extensions import Extensions


class roomba(Extensions):
    """
    The Roomba extension provides control and monitoring capabilities for iRobot Roomba vacuum cleaners.

    This extension allows AI agents to:
    - Start and stop cleaning cycles
    - Send the Roomba to dock for charging
    - Schedule cleaning sessions
    - Check the current status and battery level
    - Monitor cleaning history and performance

    The extension requires iRobot API credentials and robot identification.
    AI agents should use this when they need to control or monitor Roomba vacuum cleaners.
    """

    CATEGORY = "Smart Home & IoT"

    def __init__(
        self,
        IROBOT_API_KEY: str = "",
        IROBOT_USERNAME: str = "",
        IROBOT_PASSWORD: str = "",
        ROOMBA_ROBOT_ID: str = "",
        **kwargs,
    ):
        self.IROBOT_API_KEY = IROBOT_API_KEY
        self.IROBOT_USERNAME = IROBOT_USERNAME
        self.IROBOT_PASSWORD = IROBOT_PASSWORD
        self.ROOMBA_ROBOT_ID = ROOMBA_ROBOT_ID
        self.base_url = "https://irobot.axeda.com/services/v1"
        self.session = requests.Session()

        if self.IROBOT_API_KEY and self.IROBOT_USERNAME and self.ROOMBA_ROBOT_ID:
            self.commands = {
                "Start Cleaning": self.start_cleaning,
                "Stop Cleaning": self.stop_cleaning,
                "Dock Roomba": self.dock_roomba,
                "Schedule Cleaning": self.schedule_cleaning,
                "Check Roomba Status": self.check_status,
                "Get Cleaning History": self.get_cleaning_history,
                "Get Battery Status": self.get_battery_status,
                "Set Cleaning Preferences": self.set_cleaning_preferences,
            }
            # Setup authentication
            self._authenticate()
        else:
            self.commands = {}

        self.failures = 0

    def _authenticate(self):
        """
        Authenticate with the iRobot API using provided credentials
        """
        try:
            auth_data = {
                "username": self.IROBOT_USERNAME,
                "password": self.IROBOT_PASSWORD,
                "api_key": self.IROBOT_API_KEY,
            }

            response = self.session.post(
                f"{self.base_url}/auth/login",
                json=auth_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                auth_token = response.json().get("token")
                self.session.headers.update({"Authorization": f"Bearer {auth_token}"})
                logging.info("Successfully authenticated with iRobot API")
            else:
                logging.error(
                    f"Failed to authenticate with iRobot API: {response.status_code}"
                )

        except Exception as e:
            logging.error(f"Authentication error: {str(e)}")

    async def start_cleaning(self, cleaning_mode: str = "auto") -> str:
        """
        Start a cleaning cycle on the Roomba

        Args:
        cleaning_mode (str): The cleaning mode to use ('auto', 'spot', 'edge', 'quick')

        Returns:
        str: The result of the start cleaning operation
        """
        try:
            command_data = {
                "command": "start",
                "mode": cleaning_mode,
                "robot_id": self.ROOMBA_ROBOT_ID,
            }

            response = self.session.post(
                f"{self.base_url}/robots/{self.ROOMBA_ROBOT_ID}/commands",
                json=command_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                self.failures = 0
                return f"Successfully started cleaning in {cleaning_mode} mode. Roomba is now cleaning."
            else:
                error_msg = response.json().get("error", "Unknown error")
                return f"Failed to start cleaning: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.start_cleaning(cleaning_mode)
            return f"Error starting cleaning: {str(e)}"

    async def stop_cleaning(self) -> str:
        """
        Stop the current cleaning cycle and pause the Roomba

        Returns:
        str: The result of the stop cleaning operation
        """
        try:
            command_data = {"command": "stop", "robot_id": self.ROOMBA_ROBOT_ID}

            response = self.session.post(
                f"{self.base_url}/robots/{self.ROOMBA_ROBOT_ID}/commands",
                json=command_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                self.failures = 0
                return "Successfully stopped cleaning. Roomba has paused its current cleaning cycle."
            else:
                error_msg = response.json().get("error", "Unknown error")
                return f"Failed to stop cleaning: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.stop_cleaning()
            return f"Error stopping cleaning: {str(e)}"

    async def dock_roomba(self) -> str:
        """
        Send the Roomba back to its charging dock

        Returns:
        str: The result of the dock operation
        """
        try:
            command_data = {"command": "dock", "robot_id": self.ROOMBA_ROBOT_ID}

            response = self.session.post(
                f"{self.base_url}/robots/{self.ROOMBA_ROBOT_ID}/commands",
                json=command_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                self.failures = 0
                return "Successfully sent Roomba to dock. It will return to its charging station."
            else:
                error_msg = response.json().get("error", "Unknown error")
                return f"Failed to dock Roomba: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.dock_roomba()
            return f"Error docking Roomba: {str(e)}"

    async def schedule_cleaning(
        self,
        day_of_week: str,
        hour: int = 9,
        minute: int = 0,
        cleaning_mode: str = "auto",
    ) -> str:
        """
        Schedule a cleaning session for a specific day and time

        Args:
        day_of_week (str): Day to schedule cleaning ('monday', 'tuesday', etc.)
        hour (int): Hour of the day in 24-hour format (0-23)
        minute (int): Minute of the hour (0-59)
        cleaning_mode (str): The cleaning mode to use ('auto', 'spot', 'edge', 'quick')

        Returns:
        str: The result of the scheduling operation
        """
        try:
            schedule_data = {
                "day": day_of_week.lower(),
                "hour": hour,
                "minute": minute,
                "mode": cleaning_mode,
                "enabled": True,
                "robot_id": self.ROOMBA_ROBOT_ID,
            }

            response = self.session.post(
                f"{self.base_url}/robots/{self.ROOMBA_ROBOT_ID}/schedule",
                json=schedule_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                self.failures = 0
                time_str = f"{hour:02d}:{minute:02d}"
                return f"Successfully scheduled cleaning for {day_of_week.title()} at {time_str} in {cleaning_mode} mode."
            else:
                error_msg = response.json().get("error", "Unknown error")
                return f"Failed to schedule cleaning: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.schedule_cleaning(
                    day_of_week, hour, minute, cleaning_mode
                )
            return f"Error scheduling cleaning: {str(e)}"

    async def check_status(self) -> str:
        """
        Check the current status of the Roomba including cleaning state, location, and battery

        Returns:
        str: The current status information of the Roomba
        """
        try:
            response = self.session.get(
                f"{self.base_url}/robots/{self.ROOMBA_ROBOT_ID}/status"
            )

            if response.status_code == 200:
                status_data = response.json()

                # Extract relevant status information
                cleaning_state = status_data.get("cleaning_state", "Unknown")
                battery_level = status_data.get("battery_level", "Unknown")
                location = status_data.get("location", "Unknown")
                error_code = status_data.get("error_code", None)
                bin_full = status_data.get("bin_full", False)
                dock_status = status_data.get("docked", "Unknown")

                status_report = f"""Roomba Status Report:
- Cleaning State: {cleaning_state}
- Battery Level: {battery_level}%
- Current Location: {location}
- Docked: {dock_status}
- Bin Full: {'Yes' if bin_full else 'No'}"""

                if error_code:
                    status_report += f"\n- Error Code: {error_code}"

                self.failures = 0
                return status_report
            else:
                error_msg = response.json().get("error", "Unknown error")
                return f"Failed to get status: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.check_status()
            return f"Error checking status: {str(e)}"

    async def get_cleaning_history(self, days: int = 7) -> str:
        """
        Get the cleaning history for the specified number of days

        Args:
        days (int): Number of days of history to retrieve (default: 7)

        Returns:
        str: The cleaning history information
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            params = {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "robot_id": self.ROOMBA_ROBOT_ID,
            }

            response = self.session.get(
                f"{self.base_url}/robots/{self.ROOMBA_ROBOT_ID}/history", params=params
            )

            if response.status_code == 200:
                history_data = response.json()
                cleaning_sessions = history_data.get("sessions", [])

                if not cleaning_sessions:
                    return f"No cleaning sessions found in the last {days} days."

                history_report = f"Cleaning History (Last {days} days):\n"
                for session in cleaning_sessions[-10:]:  # Show last 10 sessions
                    date = session.get("date", "Unknown")
                    duration = session.get("duration", "Unknown")
                    area_cleaned = session.get("area_cleaned", "Unknown")
                    status = session.get("status", "Unknown")

                    history_report += f"- {date}: {duration} minutes, {area_cleaned} sq ft, Status: {status}\n"

                self.failures = 0
                return history_report
            else:
                error_msg = response.json().get("error", "Unknown error")
                return f"Failed to get cleaning history: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_cleaning_history(days)
            return f"Error getting cleaning history: {str(e)}"

    async def get_battery_status(self) -> str:
        """
        Get detailed battery status and charging information

        Returns:
        str: The battery status information
        """
        try:
            response = self.session.get(
                f"{self.base_url}/robots/{self.ROOMBA_ROBOT_ID}/battery"
            )

            if response.status_code == 200:
                battery_data = response.json()

                battery_level = battery_data.get("level", "Unknown")
                charging_state = battery_data.get("charging", False)
                estimated_runtime = battery_data.get("estimated_runtime", "Unknown")
                charge_time_remaining = battery_data.get(
                    "charge_time_remaining", "Unknown"
                )

                battery_report = f"""Battery Status:
- Battery Level: {battery_level}%
- Charging: {'Yes' if charging_state else 'No'}
- Estimated Runtime: {estimated_runtime} minutes
- Charge Time Remaining: {charge_time_remaining} minutes"""

                self.failures = 0
                return battery_report
            else:
                error_msg = response.json().get("error", "Unknown error")
                return f"Failed to get battery status: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_battery_status()
            return f"Error getting battery status: {str(e)}"

    async def set_cleaning_preferences(
        self,
        cleaning_passes: int = 1,
        edge_sweep: bool = True,
        cleaning_power: str = "auto",
    ) -> str:
        """
        Set cleaning preferences for the Roomba

        Args:
        cleaning_passes (int): Number of cleaning passes (1-3)
        edge_sweep (bool): Whether to perform edge sweeping
        cleaning_power (str): Cleaning power level ('eco', 'auto', 'performance')

        Returns:
        str: The result of setting cleaning preferences
        """
        try:
            preferences_data = {
                "cleaning_passes": min(max(cleaning_passes, 1), 3),
                "edge_sweep": edge_sweep,
                "cleaning_power": cleaning_power,
                "robot_id": self.ROOMBA_ROBOT_ID,
            }

            response = self.session.put(
                f"{self.base_url}/robots/{self.ROOMBA_ROBOT_ID}/preferences",
                json=preferences_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                self.failures = 0
                return f"""Successfully updated cleaning preferences:
- Cleaning Passes: {preferences_data['cleaning_passes']}
- Edge Sweep: {'Enabled' if edge_sweep else 'Disabled'}
- Cleaning Power: {cleaning_power.title()}"""
            else:
                error_msg = response.json().get("error", "Unknown error")
                return f"Failed to set cleaning preferences: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.set_cleaning_preferences(
                    cleaning_passes, edge_sweep, cleaning_power
                )
            return f"Error setting cleaning preferences: {str(e)}"
