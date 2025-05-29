import logging
import requests
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Dict, List, Any
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class garmin(Extensions):
    """
    The Garmin extension for AGiXT enables you to interact with Garmin health and fitness data.
    This extension provides comprehensive access to your Garmin Connect account including:
    - Heart rate measurements and zones
    - Daily step counts and activity data
    - Sleep data and patterns
    - GPS and location data from activities
    - Stress monitoring and Body Battery
    - Comprehensive activity and exercise data

    All data is retrieved securely using OAuth authentication with Garmin's Connect IQ API.
    """

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("GARMIN_ACCESS_TOKEN", None)
        garmin_client_id = getenv("GARMIN_CLIENT_ID")
        garmin_client_secret = getenv("GARMIN_CLIENT_SECRET")

        self.base_url = "https://connectapi.garmin.com"
        self.session = requests.Session()
        self.failures = 0
        self.auth = None

        # Only enable commands if Garmin is properly configured
        if garmin_client_id and garmin_client_secret:
            self.commands = {
                "Get Heart Rate": self.get_heart_rate,
                "Get Steps": self.get_steps,
                "Get Sleep Data": self.get_sleep_data,
                "Get GPS Data": self.get_gps_data,
                "Get Activity Data": self.get_activity_data,
                "Get Daily Summary": self.get_daily_summary,
                "Get Stress Data": self.get_stress_data,
                "Get Body Battery": self.get_body_battery,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Garmin extension auth: {str(e)}")
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
            refreshed_token = self.auth.refresh_oauth_token(provider="garmin")
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
                    raise Exception("No valid Garmin access token found")

        except Exception as e:
            logging.error(f"Error verifying/refreshing Garmin token: {str(e)}")
            raise Exception("Failed to authenticate with Garmin")

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

            if date == "today":
                date = datetime.now().strftime("%Y-%m-%d")

            url = f"{self.base_url}/wellness-service/wellness/dailyHeartRate/{date}"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()

                resting_hr = data.get("restingHeartRate", "N/A")
                max_hr = data.get("maxHeartRate", "N/A")
                min_hr = data.get("minHeartRate", "N/A")

                heart_rate_values = data.get("heartRateValues", [])
                avg_hr = "N/A"
                if heart_rate_values:
                    valid_hrs = [hr for hr in heart_rate_values if hr and hr > 0]
                    if valid_hrs:
                        avg_hr = sum(valid_hrs) // len(valid_hrs)

                # Heart rate zones
                zones = data.get("heartRateZones", [])
                zones_info = []
                for i, zone in enumerate(zones):
                    zone_name = f"Zone {i+1}"
                    zone_min = zone.get("zoneLowBoundary", 0)
                    zone_max = zone.get("zoneHighBoundary", 0)
                    time_in_zone = zone.get("secsInZone", 0) // 60  # Convert to minutes
                    zones_info.append(
                        f"  - {zone_name} ({zone_min}-{zone_max} bpm): {time_in_zone} minutes"
                    )

                zones_text = (
                    "\n".join(zones_info)
                    if zones_info
                    else "  No heart rate zones data"
                )

                self.failures = 0
                return f"""Heart Rate Data for {date}:
- Resting Heart Rate: {resting_hr} bpm
- Average Heart Rate: {avg_hr} bpm
- Max Heart Rate: {max_hr} bpm
- Min Heart Rate: {min_hr} bpm
- Heart Rate Zones:
{zones_text}"""
            else:
                return f"Failed to get heart rate data: HTTP {response.status_code}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_heart_rate(date)
            return f"Error getting heart rate: {str(e)}"

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

            if date == "today":
                date = datetime.now().strftime("%Y-%m-%d")

            url = f"{self.base_url}/wellness-service/wellness/dailySummaryChart/{date}"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()

                steps = data.get("totalSteps", 0)
                step_goal = data.get("stepGoal", 0)
                distance = data.get("totalDistanceMeters", 0) / 1000  # Convert to km
                calories = data.get("totalKilocalories", 0)
                active_seconds = data.get("activeSeconds", 0)
                active_minutes = active_seconds // 60

                goal_percentage = (steps / step_goal * 100) if step_goal > 0 else 0

                self.failures = 0
                return f"""Step Data for {date}:
- Steps: {steps:,} / {step_goal:,} ({goal_percentage:.1f}% of goal)
- Distance: {distance:.2f} km ({distance * 0.621371:.2f} miles)
- Calories Burned: {calories} kcal
- Active Time: {active_minutes} minutes"""
            else:
                return f"Failed to get step data: HTTP {response.status_code}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_steps(date)
            return f"Error getting steps: {str(e)}"

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

            if date == "today":
                date = (datetime.now() - timedelta(days=1)).strftime(
                    "%Y-%m-%d"
                )  # Sleep data is usually for previous night

            url = f"{self.base_url}/wellness-service/wellness/dailySleep/{date}"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()

                sleep_start = data.get("sleepStartTimestampGMT")
                sleep_end = data.get("sleepEndTimestampGMT")
                total_sleep_time = (
                    data.get("sleepTimeSeconds", 0) // 60
                )  # Convert to minutes
                deep_sleep = data.get("deepSleepSeconds", 0) // 60
                light_sleep = data.get("lightSleepSeconds", 0) // 60
                rem_sleep = data.get("remSleepSeconds", 0) // 60
                awake_time = data.get("awakeTimeSeconds", 0) // 60

                # Convert timestamps to readable format
                if sleep_start and sleep_end:
                    start_time = datetime.fromtimestamp(sleep_start / 1000).strftime(
                        "%H:%M"
                    )
                    end_time = datetime.fromtimestamp(sleep_end / 1000).strftime(
                        "%H:%M"
                    )
                    sleep_period = f"{start_time} - {end_time}"
                else:
                    sleep_period = "N/A"

                sleep_score = data.get("overallSleepScore", "N/A")

                self.failures = 0
                return f"""Sleep Data for {date}:
- Sleep Period: {sleep_period}
- Total Sleep Time: {total_sleep_time//60}h {total_sleep_time%60}m
- Deep Sleep: {deep_sleep//60}h {deep_sleep%60}m
- Light Sleep: {light_sleep//60}h {light_sleep%60}m
- REM Sleep: {rem_sleep//60}h {rem_sleep%60}m
- Awake Time: {awake_time//60}h {awake_time%60}m
- Sleep Score: {sleep_score}"""
            else:
                return f"Failed to get sleep data: HTTP {response.status_code}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_sleep_data(date)
            return f"Error getting sleep data: {str(e)}"

    async def get_gps_data(self, activity_id: str = None) -> str:
        """
        Get GPS data from a specific activity or recent activities

        Args:
        activity_id (str): Specific activity ID, or None for recent activities

        Returns:
        str: GPS and location information
        """
        try:
            self.verify_user()

            if activity_id:
                url = f"{self.base_url}/activity-service/activity/{activity_id}"
            else:
                # Get recent activities
                url = f"{self.base_url}/activity-service/activities"

            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()

                if activity_id:
                    # Single activity GPS data
                    activity_name = data.get("activityName", "Unknown Activity")
                    start_time = data.get("startTimeLocal", "N/A")
                    distance = data.get("distance", 0) / 1000  # Convert to km
                    duration = data.get("duration", 0) // 60  # Convert to minutes

                    gps_data = data.get("geoPolylineDTO", {})
                    if gps_data:
                        start_lat = gps_data.get("startPoint", {}).get("lat", "N/A")
                        start_lon = gps_data.get("startPoint", {}).get("lon", "N/A")
                        end_lat = gps_data.get("endPoint", {}).get("lat", "N/A")
                        end_lon = gps_data.get("endPoint", {}).get("lon", "N/A")

                        self.failures = 0
                        return f"""GPS Data for Activity: {activity_name}
- Start Time: {start_time}
- Distance: {distance:.2f} km
- Duration: {duration} minutes
- Start Location: {start_lat}, {start_lon}
- End Location: {end_lat}, {end_lon}"""
                    else:
                        return f"No GPS data available for activity: {activity_name}"
                else:
                    # Recent activities list
                    activities = data.get("activities", [])[:5]  # Last 5 activities
                    if activities:
                        activity_list = []
                        for activity in activities:
                            name = activity.get("activityName", "Unknown")
                            date = activity.get("startTimeLocal", "N/A")
                            distance = activity.get("distance", 0) / 1000
                            activity_list.append(
                                f"  - {name}: {date} ({distance:.2f} km)"
                            )

                        self.failures = 0
                        return f"""Recent Activities with GPS:
{chr(10).join(activity_list)}

Use specific activity ID to get detailed GPS data."""
                    else:
                        return "No recent activities found"
            else:
                return f"Failed to get GPS data: HTTP {response.status_code}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_gps_data(activity_id)
            return f"Error getting GPS data: {str(e)}"

    async def get_activity_data(self, date: str = "today", limit: int = 10) -> str:
        """
        Get activity and exercise data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')
        limit (int): Maximum number of activities to retrieve (default: 10)

        Returns:
        str: Activity and exercise information
        """
        try:
            self.verify_user()

            if date == "today":
                date = datetime.now().strftime("%Y-%m-%d")

            url = f"{self.base_url}/activity-service/activities/search/activities"
            params = {"start": 0, "limit": limit, "startDate": date, "endDate": date}

            response = self.session.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                activities = data.get("activities", [])

                if activities:
                    activity_list = []
                    for activity in activities:
                        name = activity.get("activityName", "Unknown Activity")
                        activity_type = activity.get("activityType", {}).get(
                            "typeKey", "Unknown"
                        )
                        start_time = activity.get("startTimeLocal", "N/A")
                        duration = (
                            activity.get("duration", 0) // 60
                        )  # Convert to minutes
                        distance = (
                            activity.get("distance", 0) / 1000
                            if activity.get("distance")
                            else 0
                        )
                        calories = activity.get("calories", 0)
                        avg_hr = activity.get("averageHR", "N/A")
                        max_hr = activity.get("maxHR", "N/A")

                        activity_info = f"""  - {name} ({activity_type})
    Start: {start_time}
    Duration: {duration} minutes
    Distance: {distance:.2f} km
    Calories: {calories}
    Avg HR: {avg_hr} bpm, Max HR: {max_hr} bpm"""
                        activity_list.append(activity_info)

                    self.failures = 0
                    return f"""Activity Data for {date}:
{chr(10).join(activity_list)}"""
                else:
                    return f"No activities found for {date}"
            else:
                return f"Failed to get activity data: HTTP {response.status_code}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_activity_data(date, limit)
            return f"Error getting activity data: {str(e)}"

    async def get_daily_summary(self, date: str = "today") -> str:
        """
        Get comprehensive daily summary including all health metrics

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Comprehensive daily health summary
        """
        try:
            self.verify_user()

            if date == "today":
                date = datetime.now().strftime("%Y-%m-%d")

            url = f"{self.base_url}/wellness-service/wellness/dailySummaryChart/{date}"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()

                # Extract key metrics
                steps = data.get("totalSteps", 0)
                step_goal = data.get("stepGoal", 0)
                distance = data.get("totalDistanceMeters", 0) / 1000
                calories = data.get("totalKilocalories", 0)
                active_time = data.get("activeSeconds", 0) // 60
                resting_hr = data.get("restingHeartRate", "N/A")
                stress_score = data.get("averageStressLevel", "N/A")
                body_battery = data.get("bodyBatteryChargedUp", "N/A")

                # Calculate goal percentages
                step_percentage = (steps / step_goal * 100) if step_goal > 0 else 0

                self.failures = 0
                return f"""Daily Summary for {date}:

🚶 Activity:
- Steps: {steps:,} / {step_goal:,} ({step_percentage:.1f}% of goal)
- Distance: {distance:.2f} km ({distance * 0.621371:.2f} miles)
- Active Time: {active_time} minutes
- Calories: {calories} kcal

❤️ Health:
- Resting Heart Rate: {resting_hr} bpm
- Stress Level: {stress_score}
- Body Battery: {body_battery}

📊 Overall Status: {"Goal Achieved! 🎉" if step_percentage >= 100 else "Keep Going! 💪"}"""
            else:
                return f"Failed to get daily summary: HTTP {response.status_code}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_daily_summary(date)
            return f"Error getting daily summary: {str(e)}"

    async def get_stress_data(self, date: str = "today") -> str:
        """
        Get stress monitoring data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Stress monitoring information
        """
        try:
            self.verify_user()

            if date == "today":
                date = datetime.now().strftime("%Y-%m-%d")

            url = f"{self.base_url}/wellness-service/wellness/dailyStress/{date}"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()

                overall_stress = data.get("overallStressLevel", "N/A")
                avg_stress = data.get("avgStressLevel", "N/A")
                max_stress = data.get("maxStressLevel", "N/A")
                rest_stress = data.get("restStressAvgLevel", "N/A")
                activity_stress = data.get("activityStressAvgLevel", "N/A")
                stress_duration = (
                    data.get("stressDuration", 0) // 60
                )  # Convert to minutes
                rest_duration = data.get("restStressDuration", 0) // 60

                # Stress level interpretation
                stress_levels = []
                if isinstance(overall_stress, int):
                    if overall_stress < 25:
                        stress_levels.append("Low stress (rest)")
                    elif overall_stress < 50:
                        stress_levels.append("Low stress")
                    elif overall_stress < 75:
                        stress_levels.append("Medium stress")
                    else:
                        stress_levels.append("High stress")

                stress_interpretation = (
                    " - ".join(stress_levels) if stress_levels else "N/A"
                )

                self.failures = 0
                return f"""Stress Data for {date}:
- Overall Stress Level: {overall_stress} ({stress_interpretation})
- Average Stress: {avg_stress}
- Maximum Stress: {max_stress}
- Rest Stress Average: {rest_stress}
- Activity Stress Average: {activity_stress}
- Time in Stress: {stress_duration} minutes
- Time at Rest: {rest_duration} minutes"""
            else:
                return f"Failed to get stress data: HTTP {response.status_code}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_stress_data(date)
            return f"Error getting stress data: {str(e)}"

    async def get_body_battery(self, date: str = "today") -> str:
        """
        Get Body Battery energy monitoring data for a specific date

        Args:
        date (str): Date in YYYY-MM-DD format or 'today' (default: 'today')

        Returns:
        str: Body Battery energy information
        """
        try:
            self.verify_user()

            if date == "today":
                date = datetime.now().strftime("%Y-%m-%d")

            url = f"{self.base_url}/wellness-service/wellness/bodyBattery/{date}"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()

                charged_up = data.get("bodyBatteryChargedUp", "N/A")
                drained = data.get("bodyBatteryDrained", "N/A")
                highest_level = data.get("bodyBatteryHighestLevel", "N/A")
                lowest_level = data.get("bodyBatteryLowestLevel", "N/A")
                current_level = data.get("bodyBatteryMostRecentLevel", "N/A")

                # Body Battery interpretation
                energy_status = "N/A"
                if isinstance(current_level, int):
                    if current_level >= 75:
                        energy_status = "High energy 🔋🔋🔋"
                    elif current_level >= 50:
                        energy_status = "Good energy 🔋🔋"
                    elif current_level >= 25:
                        energy_status = "Medium energy 🔋"
                    else:
                        energy_status = "Low energy ⚠️"

                self.failures = 0
                return f"""Body Battery for {date}:
- Current Level: {current_level}/100 ({energy_status})
- Highest Level: {highest_level}/100
- Lowest Level: {lowest_level}/100
- Energy Charged: +{charged_up}
- Energy Drained: -{drained}

💡 Body Battery tracks your energy reserves throughout the day.
   Higher levels indicate better readiness for physical activity."""
            else:
                return f"Failed to get Body Battery data: HTTP {response.status_code}"

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_body_battery(date)
            return f"Error getting Body Battery data: {str(e)}"
