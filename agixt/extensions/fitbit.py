import logging
import requests
import asyncio
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class fitbit(Extensions):
    """
    The Fitbit extension for AGiXT enables you to interact with Fitbit health and fitness data.
    This extension provides comprehensive access to your Fitbit account including:
    - Activity data (steps, calories, distance)
    - Heart rate monitoring
    - Sleep tracking
    - Exercise and workout data
    - Weight and body composition
    - Water intake tracking

    All data is retrieved securely using OAuth authentication with Fitbit's official API.
    """

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("FITBIT_ACCESS_TOKEN", None)
        fitbit_client_id = getenv("FITBIT_CLIENT_ID")
        fitbit_client_secret = getenv("FITBIT_CLIENT_SECRET")

        self.base_url = "https://api.fitbit.com/1"
        self.session = requests.Session()
        self.failures = 0
        self.auth = None

        # Only enable commands if Fitbit is properly configured
        if fitbit_client_id and fitbit_client_secret:
            self.commands = {
                "Get Steps": self.get_steps,
                "Get Heart Rate": self.get_heart_rate,
                "Get Sleep Data": self.get_sleep_data,
                "Get Calories Burned": self.get_calories_burned,
                "Get Exercise Data": self.get_exercise_data,
                "Get Activity Summary": self.get_activity_summary,
                "Get Weight Data": self.get_weight_data,
                "Get Water Intake": self.get_water_intake,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Fitbit extension auth: {str(e)}")
        else:
            self.commands = {}

    def verify_user(self):
        """
        Verify user access token and refresh if needed using MagicalAuth
        """
        if not self.auth:
            raise Exception("Authentication context not initialized.")

        try:
            # Refresh token via MagicalAuth, which handles expiry checks
            refreshed_token = self.auth.refresh_oauth_token(provider="fitbit")
            if refreshed_token:
                self.access_token = refreshed_token
                self.session.headers.update(
                    {
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    }
                )
            else:
                if not self.access_token:
                    raise Exception("No valid Fitbit access token found")

        except Exception as e:
            logging.error(f"Error verifying/refreshing Fitbit token: {str(e)}")
            raise Exception("Failed to authenticate with Fitbit")

    async def get_steps(self, date: str = "today") -> str:
        """
        Get step count data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Step count information for the specified date
        """
        try:
            self.verify_user()

            url = f"{self.base_url}/user/-/activities/steps/date/{date}/1d.json"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                steps_data = data.get("activities-steps", [])

                if steps_data:
                    step_info = steps_data[0]
                    date_str = step_info.get("dateTime", date)
                    steps = step_info.get("value", "0")

                    self.failures = 0
                    return f"Steps for {date_str}: {int(steps):,} steps"
                else:
                    return f"No step data found for {date}"
            else:
                error_msg = (
                    response.json()
                    .get("errors", [{}])[0]
                    .get("message", "Unknown error")
                )
                return f"Failed to get steps: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_steps(date)
            return f"Error getting steps: {str(e)}"

    async def get_heart_rate(self, date: str = "today") -> str:
        """
        Get heart rate data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Heart rate information for the specified date
        """
        try:
            self.verify_user()

            url = f"{self.base_url}/user/-/activities/heart/date/{date}/1d.json"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                heart_data = data.get("activities-heart", [])

                if heart_data:
                    heart_info = heart_data[0]
                    date_str = heart_info.get("dateTime", date)
                    resting_hr = heart_info.get("value", {}).get(
                        "restingHeartRate", "N/A"
                    )

                    heart_zones = heart_info.get("value", {}).get("heartRateZones", [])
                    zones_info = []

                    for zone in heart_zones:
                        zone_name = zone.get("name", "Unknown")
                        minutes = zone.get("minutes", 0)
                        calories = zone.get("caloriesOut", 0)
                        zones_info.append(
                            f"  - {zone_name}: {minutes} minutes, {calories} calories"
                        )

                    zones_text = (
                        "\n".join(zones_info)
                        if zones_info
                        else "  No heart rate zones data"
                    )

                    self.failures = 0
                    return f"""Heart Rate Data for {date_str}:
- Resting Heart Rate: {resting_hr} bpm
- Heart Rate Zones:
{zones_text}"""
                else:
                    return f"No heart rate data found for {date}"
            else:
                error_msg = (
                    response.json()
                    .get("errors", [{}])[0]
                    .get("message", "Unknown error")
                )
                return f"Failed to get heart rate: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_heart_rate(date)
            return f"Error getting heart rate: {str(e)}"

    async def get_sleep_data(self, date: str = "today") -> str:
        """
        Get sleep data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Sleep information for the specified date
        """
        try:
            self.verify_user()

            url = f"{self.base_url}/user/-/sleep/date/{date}.json"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                sleep_sessions = data.get("sleep", [])

                if sleep_sessions:
                    main_sleep = sleep_sessions[0]  # Get main sleep session
                    date_str = main_sleep.get("dateOfSleep", date)
                    start_time = main_sleep.get("startTime", "N/A")
                    end_time = main_sleep.get("endTime", "N/A")
                    duration = (
                        main_sleep.get("duration", 0) // 60000
                    )  # Convert to minutes
                    efficiency = main_sleep.get("efficiency", "N/A")

                    # Sleep stages
                    levels = main_sleep.get("levels", {})
                    summary = levels.get("summary", {})

                    deep_minutes = summary.get("deep", {}).get("minutes", 0)
                    light_minutes = summary.get("light", {}).get("minutes", 0)
                    rem_minutes = summary.get("rem", {}).get("minutes", 0)
                    wake_minutes = summary.get("wake", {}).get("minutes", 0)

                    self.failures = 0
                    return f"""Sleep Data for {date_str}:
- Sleep Duration: {duration} minutes ({duration // 60}h {duration % 60}m)
- Start Time: {start_time}
- End Time: {end_time}
- Sleep Efficiency: {efficiency}%
- Sleep Stages:
  - Deep Sleep: {deep_minutes} minutes
  - Light Sleep: {light_minutes} minutes
  - REM Sleep: {rem_minutes} minutes
  - Awake: {wake_minutes} minutes"""
                else:
                    return f"No sleep data found for {date}"
            else:
                error_msg = (
                    response.json()
                    .get("errors", [{}])[0]
                    .get("message", "Unknown error")
                )
                return f"Failed to get sleep data: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_sleep_data(date)
            return f"Error getting sleep data: {str(e)}"

    async def get_calories_burned(self, date: str = "today") -> str:
        """
        Get calories burned data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Calories burned information for the specified date
        """
        try:
            self.verify_user()

            url = f"{self.base_url}/user/-/activities/calories/date/{date}/1d.json"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                calories_data = data.get("activities-calories", [])

                if calories_data:
                    calorie_info = calories_data[0]
                    date_str = calorie_info.get("dateTime", date)
                    calories = calorie_info.get("value", "0")

                    self.failures = 0
                    return f"Calories burned for {date_str}: {calories} calories"
                else:
                    return f"No calorie data found for {date}"
            else:
                error_msg = (
                    response.json()
                    .get("errors", [{}])[0]
                    .get("message", "Unknown error")
                )
                return f"Failed to get calories: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_calories_burned(date)
            return f"Error getting calories: {str(e)}"

    async def get_exercise_data(self, date: str = "today") -> str:
        """
        Get exercise and activity data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Exercise and activity information for the specified date
        """
        try:
            self.verify_user()

            url = f"{self.base_url}/user/-/activities/date/{date}.json"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                activities = data.get("activities", [])
                summary = data.get("summary", {})

                # Activity summary
                active_minutes = summary.get("veryActiveMinutes", 0) + summary.get(
                    "fairlyActiveMinutes", 0
                )
                sedentary_minutes = summary.get("sedentaryMinutes", 0)
                distance = summary.get("totalDistance", 0)
                floors = summary.get("floors", 0)

                exercise_report = f"""Exercise Data for {date}:
- Total Distance: {distance} miles
- Active Minutes: {active_minutes} minutes
- Sedentary Minutes: {sedentary_minutes} minutes
- Floors Climbed: {floors}"""

                if activities:
                    exercise_report += "\n- Logged Activities:"
                    for activity in activities:
                        name = activity.get("name", "Unknown")
                        duration = (
                            activity.get("duration", 0) // 60000
                        )  # Convert to minutes
                        calories = activity.get("calories", 0)
                        distance_activity = activity.get("distance", 0)

                        exercise_report += (
                            f"\n  - {name}: {duration} minutes, {calories} calories"
                        )
                        if distance_activity > 0:
                            exercise_report += f", {distance_activity} miles"
                else:
                    exercise_report += "\n- No logged activities"

                self.failures = 0
                return exercise_report
            else:
                error_msg = (
                    response.json()
                    .get("errors", [{}])[0]
                    .get("message", "Unknown error")
                )
                return f"Failed to get exercise data: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_exercise_data(date)
            return f"Error getting exercise data: {str(e)}"

    async def get_activity_summary(self, date: str = "today") -> str:
        """
        Get a comprehensive activity summary for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Comprehensive activity summary for the specified date
        """
        try:
            self.verify_user()

            url = f"{self.base_url}/user/-/activities/date/{date}.json"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                summary = data.get("summary", {})
                goals = data.get("goals", {})

                steps = summary.get("steps", 0)
                calories = summary.get("caloriesOut", 0)
                distance = summary.get("totalDistance", 0)
                active_minutes = summary.get("veryActiveMinutes", 0) + summary.get(
                    "fairlyActiveMinutes", 0
                )
                floors = summary.get("floors", 0)

                steps_goal = goals.get("steps", 1)  # Avoid division by zero
                calories_goal = goals.get("caloriesOut", 1)
                distance_goal = goals.get("distance", 1)
                active_goal = goals.get("activeMinutes", 1)
                floors_goal = goals.get("floors", 1)

                self.failures = 0
                return f"""Activity Summary for {date}:
- Steps: {steps:,} / {steps_goal:,} ({(steps/steps_goal*100):.1f}% of goal)
- Calories: {calories} / {calories_goal} ({(calories/calories_goal*100):.1f}% of goal)
- Distance: {distance:.2f} / {distance_goal:.2f} miles ({(distance/distance_goal*100):.1f}% of goal)
- Active Minutes: {active_minutes} / {active_goal} ({(active_minutes/active_goal*100):.1f}% of goal)
- Floors: {floors} / {floors_goal} ({(floors/floors_goal*100):.1f}% of goal)"""
            else:
                error_msg = (
                    response.json()
                    .get("errors", [{}])[0]
                    .get("message", "Unknown error")
                )
                return f"Failed to get activity summary: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_activity_summary(date)
            return f"Error getting activity summary: {str(e)}"

    async def get_weight_data(self, date: str = "today") -> str:
        """
        Get weight data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Weight information for the specified date
        """
        try:
            self.verify_user()

            url = f"{self.base_url}/user/-/body/log/weight/date/{date}.json"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                weight_logs = data.get("weight", [])

                if weight_logs:
                    latest_weight = weight_logs[-1]  # Get most recent entry
                    weight = latest_weight.get("weight", "N/A")
                    bmi = latest_weight.get("bmi", "N/A")
                    date_logged = latest_weight.get("date", date)

                    self.failures = 0
                    return f"""Weight Data for {date_logged}:
- Weight: {weight} lbs
- BMI: {bmi}"""
                else:
                    return f"No weight data found for {date}"
            else:
                error_msg = (
                    response.json()
                    .get("errors", [{}])[0]
                    .get("message", "Unknown error")
                )
                return f"Failed to get weight data: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_weight_data(date)
            return f"Error getting weight data: {str(e)}"

    async def get_water_intake(self, date: str = "today") -> str:
        """
        Get water intake data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Water intake information for the specified date
        """
        try:
            self.verify_user()

            url = f"{self.base_url}/user/-/foods/log/water/date/{date}.json"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                summary = data.get("summary", {})
                water_logs = data.get("water", [])

                total_water = summary.get("water", 0)
                goal = summary.get("goal", 1)  # Avoid division by zero

                water_report = f"""Water Intake for {date}:
- Total Water: {total_water} ml ({total_water * 0.033814:.1f} fl oz)
- Goal: {goal} ml ({goal * 0.033814:.1f} fl oz)
- Progress: {(total_water/goal*100):.1f}% of goal"""

                if water_logs:
                    water_report += "\n- Log Entries:"
                    for log in water_logs:
                        amount = log.get("amount", 0)
                        time_logged = log.get("time", "Unknown")
                        water_report += f"\n  - {time_logged}: {amount} ml"

                self.failures = 0
                return water_report
            else:
                error_msg = (
                    response.json()
                    .get("errors", [{}])[0]
                    .get("message", "Unknown error")
                )
                return f"Failed to get water intake: {error_msg}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_water_intake(date)
            return f"Error getting water intake: {str(e)}"
