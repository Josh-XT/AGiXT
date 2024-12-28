from Extensions import Extensions
import requests
import json
from datetime import date, timedelta
import logging


class oura(Extensions):
    """
    The Oura extension for AGiXT enables you to interact with the Oura API to retrieve health and wellness data for the user.
    """

    def __init__(self, OURA_API_KEY: str = "", **kwargs):
        self.base_uri = "https://api.ouraring.com"
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {OURA_API_KEY}"})
        self.commands = {
            "Get Oura Ring Data": self.get_oura_data,
        }

    async def get_oura_data(self, start_date=None, end_date=None):
        """
        Fetch and aggregate user personal biometric data from the Oura Ring API.
        This allows specifying a date range to capture as much data as possible from various endpoints.

        Args:
            start_date (str): Optional. Start date in 'YYYY-MM-DD' format.
            end_date (str): Optional. End date in 'YYYY-MM-DD' format.

        Returns:
            str: A markdown-formatted string summarizing combined user data
                 or a JSON-formatted string if an error occurs.
        """
        # If no dates are provided, default to the past 7 days
        if not start_date:
            start_date = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = date.today().strftime("%Y-%m-%d")

        # Define endpoints that require date ranges
        endpoints = {
            "personal_info": "v2/usercollection/personal_info",
            "daily_activity": f"v2/usercollection/daily_activity?start_date={start_date}&end_date={end_date}",
            "daily_sleep": f"v2/usercollection/daily_sleep?start_date={start_date}&end_date={end_date}",
            "daily_readiness": f"v2/usercollection/daily_readiness?start_date={start_date}&end_date={end_date}",
            "daily_stress": f"v2/usercollection/daily_stress?start_date={start_date}&end_date={end_date}",
            "daily_spo2": f"v2/usercollection/daily_spo2?start_date={start_date}&end_date={end_date}",
            "sleep_time": f"v2/usercollection/sleep_time?start_date={start_date}&end_date={end_date}",
            "workout": f"v2/usercollection/workout?start_date={start_date}&end_date={end_date}",
            "session": f"v2/usercollection/session?start_date={start_date}&end_date={end_date}",
        }

        combined_data = {}

        for key, endpoint in endpoints.items():
            url = f"{self.base_uri}/{endpoint}"
            try:
                response = self.session.get(url)
                response.raise_for_status()
                resp_json = response.json()

                # The personal_info endpoint usually returns a single object under 'data'
                # Others may return lists of documents under 'data'
                if key == "personal_info":
                    combined_data[key] = resp_json.get("data", {})
                else:
                    combined_data[key] = resp_json.get("data", [])
            except requests.exceptions.HTTPError as err:
                # Capture the error information rather than failing completely
                status_code = err.response.status_code if err.response else None
                combined_data[key] = {
                    "error": True,
                    "status_code": status_code,
                    "message": str(err),
                }

        data = combined_data
        markdown_lines = []
        markdown_lines.append("# Oura Data Summary\n")

        # Personal Info Section
        try:
            personal_info = data.get("personal_info", {})
            if personal_info and isinstance(personal_info, dict):
                markdown_lines.append("## Personal Info")
                for k, v in personal_info.items():
                    markdown_lines.append(f"- **{k}**: {v}")
                markdown_lines.append("")
        except Exception as e:
            logging.warning(f"Error processing personal_info: {e}")

        # Daily Activity
        try:
            daily_activity = data.get("daily_activity", [])
            if isinstance(daily_activity, list) and daily_activity:
                markdown_lines.append("## Daily Activity")
                markdown_lines.append("| Date | Steps | Calories |")
                markdown_lines.append("|------|-------|----------|")
                for entry in daily_activity:
                    date_val = entry.get("day", "N/A")
                    steps_val = entry.get("steps", "N/A")
                    cal_val = entry.get("cal_total", "N/A")
                    markdown_lines.append(f"| {date_val} | {steps_val} | {cal_val} |")
                markdown_lines.append("")
            else:
                markdown_lines.append("## Daily Activity\n- No activity data found.\n")
        except Exception as e:
            logging.warning(f"Error processing daily_activity: {e}")

        # Daily Sleep
        try:
            daily_sleep = data.get("daily_sleep", [])
            if isinstance(daily_sleep, list) and daily_sleep:
                markdown_lines.append("## Daily Sleep")
                for entry in daily_sleep:
                    date_val = entry.get("day", "N/A")
                    total_sleep_duration = entry.get("total_sleep_duration", "N/A")
                    markdown_lines.append(
                        f"- **Date**: {date_val}\n  - Total Sleep Duration: {total_sleep_duration}"
                    )
                markdown_lines.append("")
        except Exception as e:
            logging.warning(f"Error processing daily_sleep: {e}")

        # Daily Readiness
        try:
            daily_readiness = data.get("daily_readiness", [])
            if isinstance(daily_readiness, list) and daily_readiness:
                markdown_lines.append("## Daily Readiness")
                for entry in daily_readiness:
                    date_val = entry.get("day", "N/A")
                    score = entry.get("score", "N/A")
                    markdown_lines.append(
                        f"- **Date**: {date_val}\n  - Readiness Score: {score}"
                    )
                markdown_lines.append("")
        except Exception as e:
            logging.warning(f"Error processing daily_readiness: {e}")

        # Daily Stress
        try:
            daily_stress = data.get("daily_stress", [])
            if isinstance(daily_stress, list) and daily_stress:
                markdown_lines.append("## Daily Stress")
                for entry in daily_stress:
                    date_val = entry.get("day", "N/A")
                    stress_score = entry.get("score", "N/A")
                    markdown_lines.append(
                        f"- **Date**: {date_val}\n  - Stress Score: {stress_score}"
                    )
                markdown_lines.append("")
        except Exception as e:
            logging.warning(f"Error processing daily_stress: {e}")

        # Daily SpO2
        try:
            daily_spo2 = data.get("daily_spo2", [])
            if isinstance(daily_spo2, list) and daily_spo2:
                markdown_lines.append("## Daily SpO2")
                for entry in daily_spo2:
                    date_val = entry.get("day", "N/A")
                    average_spo2 = entry.get("average_spo2", "N/A")
                    markdown_lines.append(
                        f"- **Date**: {date_val}\n  - Average SpO2: {average_spo2}"
                    )
                markdown_lines.append("")
        except Exception as e:
            logging.warning(f"Error processing daily_spo2: {e}")

        # Sleep Time
        try:
            sleep_time = data.get("sleep_time", [])
            if isinstance(sleep_time, list) and sleep_time:
                markdown_lines.append("## Sleep Time")
                for entry in sleep_time:
                    date_val = entry.get("day", "N/A")
                    bedtime_start = entry.get("bedtime_start", "N/A")
                    bedtime_end = entry.get("bedtime_end", "N/A")
                    markdown_lines.append(
                        f"- **Date**: {date_val}\n"
                        f"  - Bedtime Start: {bedtime_start}\n"
                        f"  - Bedtime End: {bedtime_end}"
                    )
                markdown_lines.append("")
        except Exception as e:
            logging.warning(f"Error processing sleep_time: {e}")

        # Workout
        try:
            workout = data.get("workout", [])
            if isinstance(workout, list) and workout:
                markdown_lines.append("## Workouts")
                for entry in workout:
                    start_time = entry.get("start_datetime", "N/A")
                    workout_type = entry.get("type", "N/A")
                    duration = entry.get("duration", "N/A")
                    markdown_lines.append(
                        f"- **Start Time**: {start_time}\n"
                        f"  - Type: {workout_type}\n"
                        f"  - Duration: {duration}"
                    )
                markdown_lines.append("")
        except Exception as e:
            logging.warning(f"Error processing workout: {e}")

        # Session
        try:
            session = data.get("session", [])
            if isinstance(session, list) and session:
                markdown_lines.append("## Sessions")
                for entry in session:
                    start_time = entry.get("start_datetime", "N/A")
                    session_type = entry.get("type", "N/A")
                    score = entry.get("score", "N/A")
                    markdown_lines.append(
                        f"- **Start Time**: {start_time}\n"
                        f"  - Type: {session_type}\n"
                        f"  - Score: {score}"
                    )
                markdown_lines.append("")
        except Exception as e:
            logging.warning(f"Error processing session: {e}")

        if markdown_lines:
            # Final assembled markdown output
            return "\n".join(markdown_lines)
        else:
            return json.dumps(combined_data, indent=4)
