import logging
import requests
import asyncio
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Dict, List, Any
from fastapi import HTTPException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


"""
Required environment variables:

- FITBIT_CLIENT_ID: Fitbit OAuth client ID
- FITBIT_CLIENT_SECRET: Fitbit OAuth client secret
"""

SCOPES = [
    "activity",
    "heartrate",
    "location",
    "nutrition",
    "profile",
    "settings",
    "sleep",
    "social",
    "weight",
]
AUTHORIZE = "https://www.fitbit.com/oauth2/authorize"
PKCE_REQUIRED = True


class FitbitSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("FITBIT_CLIENT_ID")
        self.client_secret = getenv("FITBIT_CLIENT_SECRET")
        self.domain = (
            getenv("AGIXT_URI")
            .replace("https://", "")
            .replace("http://", "")
            .rstrip("/")
        )
        self.token_url = "https://api.fitbit.com/oauth2/token"
        self.api_base_url = "https://api.fitbit.com"

        # Get user info
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Get a new access token using the refresh token"""
        import base64

        # Fitbit requires Basic auth with client credentials
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        response = requests.post(
            self.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            headers={
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to refresh Fitbit token: {response.text}",
            )

        data = response.json()

        # Update our tokens for immediate use
        if "access_token" in data:
            self.access_token = data["access_token"]
        else:
            raise Exception("No access_token in Fitbit refresh response")

        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        return data

    def get_user_info(self):
        """Get user information from Fitbit API"""
        if not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            # Try with current token
            user_url = f"{self.api_base_url}/1/user/-/profile.json"
            response = requests.get(user_url, headers=headers)

            # If token expired, try refreshing
            if response.status_code == 401 and self.refresh_token:
                logging.info("Fitbit token expired, refreshing...")
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(user_url, headers=headers)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get Fitbit user info: {response.text}",
                )

            data = response.json()
            user_data = data.get("user", {})

            return {
                "email": user_data.get("email"),
                "first_name": user_data.get("firstName"),
                "last_name": user_data.get("lastName"),
                "display_name": user_data.get("displayName"),
                "member_since": user_data.get("memberSince"),
                "country": user_data.get("country"),
                "timezone": user_data.get("timezone"),
            }

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Error getting Fitbit user info: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error getting Fitbit user info: {str(e)}"
            )


def sso(code, redirect_uri=None, code_verifier=None):
    """Handle Fitbit OAuth flow"""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    logging.info(
        f"Exchanging Fitbit authorization code for tokens with redirect URI: {redirect_uri}"
    )

    import base64

    # Fitbit requires Basic auth with client credentials
    client_id = getenv("FITBIT_CLIENT_ID")
    client_secret = getenv("FITBIT_CLIENT_SECRET")
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    # Exchange authorization code for tokens
    token_url = "https://api.fitbit.com/oauth2/token"

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }

    # Add code verifier if using PKCE
    if code_verifier:
        payload["code_verifier"] = code_verifier

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    logging.info(f"Sending token request to {token_url}")
    response = requests.post(token_url, data=payload, headers=headers)

    if response.status_code != 200:
        logging.error(
            f"Error getting Fitbit access token: {response.status_code} - {response.text}"
        )
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    logging.info(
        f"Successfully obtained Fitbit tokens. Access token expires in {expires_in} seconds."
    )

    return FitbitSSO(access_token=access_token, refresh_token=refresh_token)


def get_authorization_url(state=None, code_challenge=None):
    """Generate Fitbit authorization URL"""
    client_id = getenv("FITBIT_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "redirect_uri": redirect_uri,
    }

    if state:
        params["state"] = state

    # Add PKCE parameters if provided
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    # Build query string
    query = "&".join([f"{k}={v}" for k, v in params.items()])

    return f"https://www.fitbit.com/oauth2/authorize?{query}"


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

    CATEGORY = "Health & Fitness"

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
