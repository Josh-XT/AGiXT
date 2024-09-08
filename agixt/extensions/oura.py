from Extensions import Extensions
import requests


class oura(Extensions):
    def __init__(self, OURA_API_KEY, **kwargs):
        self.base_uri = "https://api.ouraring.com"
        self.api_key = OURA_API_KEY
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
        self.commands = {
            "Get personal info": self.get_personal_info,
            "Get usercollection tag": self.get_usercollection_tag,
            "Get sandbox usercollection tags": self.get_sandbox_usercollection_tags,
            "Get enhanced tag documents": self.get_enhanced_tag_documents,
            "Get sandbox usercollection enhanced tag": self.get_sandbox_usercollection_enhanced_tag,
            "Get multiple workout documents": self.get_multiple_workout_documents,
            "Get sandbox user workouts": self.get_sandbox_user_workouts,
            "Get multiple session documents": self.get_multiple_session_documents,
            "Get sandbox session documents": self.get_sandbox_session_documents,
            "Get multiple daily activity documents": self.get_multiple_daily_activity_documents,
            "Get sandbox usercollection daily activity": self.get_sandbox_usercollection_daily_activity,
            "Get daily sleep": self.get_daily_sleep,
            "Get sandbox usercollection daily sleep": self.get_sandbox_usercollection_daily_sleep,
            "Get multiple daily spo2 documents": self.get_multiple_daily_spo2_documents,
            "Get sandbox daily spo2": self.get_sandbox_daily_spo2,
            "Get daily readiness": self.get_daily_readiness,
            "Get sandbox daily readiness": self.get_sandbox_daily_readiness,
            "Get user sleep documents": self.get_user_sleep_documents,
            "Get sandbox user sleep data": self.get_sandbox_user_sleep_data,
            "Get sleep time documents": self.get_sleep_time_documents,
            "Get sandbox sleep time": self.get_sandbox_sleep_time,
            "Get rest mode period documents": self.get_rest_mode_period_documents,
            "Get sandbox rest mode periods": self.get_sandbox_rest_mode_periods,
            "Get ring configuration": self.get_ring_configuration,
            "Get sandbox ring configuration": self.get_sandbox_ring_configuration,
            "Get daily stress": self.get_daily_stress,
            "Get daily stress documents": self.get_daily_stress_documents,
            "Get daily resilience documents": self.get_daily_resilience_documents,
            "Get sandbox daily resilience": self.get_sandbox_daily_resilience,
            "Get daily cardiovascular age": self.get_daily_cardiovascular_age,
            "Get vo2 max documents": self.get_vo2_max_documents,
            "Get sandbox usercollection vo2 max": self.get_sandbox_usercollection_vo2_max,
            "Get single tag document": self.get_single_tag_document,
            "Get enhanced tag document": self.get_enhanced_tag_document,
            "Get sandbox single enhanced tag document": self.get_sandbox_single_enhanced_tag_document,
            "Get single workout document": self.get_single_workout_document,
            "Get sandbox single workout document": self.get_sandbox_single_workout_document,
            "Get single session document": self.get_single_session_document,
            "Get sandbox single session document": self.get_sandbox_single_session_document,
            "Get single daily activity document": self.get_single_daily_activity_document,
            "Get sandbox daily activity document": self.get_sandbox_daily_activity_document,
            "Get daily sleep document": self.get_daily_sleep_document,
            "Get single daily spo2 document": self.get_single_daily_spo2_document,
            "Get sandbox daily spo2 document": self.get_sandbox_daily_spo2_document,
            "Get single daily readiness document": self.get_single_daily_readiness_document,
            "Get daily readiness document": self.get_daily_readiness_document,
            "Get single sleep document": self.get_single_sleep_document,
            "Get sleep time document": self.get_sleep_time_document,
            "Get rest mode period document": self.get_rest_mode_period_document,
            "Get single ring configuration document": self.get_single_ring_configuration_document,
            "Get ring configuration document": self.get_ring_configuration_document,
            "Get single daily stress document": self.get_single_daily_stress_document,
            "Get daily stress document": self.get_daily_stress_document,
            "Get daily resilience document": self.get_daily_resilience_document,
            "Get single daily resilience document": self.get_single_daily_resilience_document,
            "Get daily cardiovascular age document": self.get_daily_cardiovascular_age_document,
            "Get vo2 max document": self.get_vO2_max_document,
            "Get sandbox vo2 max document": self.get_sandbox_vo2_max_document,
            "List webhook subscriptions": self.list_webhook_subscriptions,
            "Create webhook subscription": self.create_webhook_subscription,
            "Get webhook subscription": self.get_webhook_subscription,
            "Update webhook subscription": self.update_webhook_subscription,
            "Delete webhook subscription": self.delete_webhook_subscription,
            "Renew webhook subscription": self.renew_webhook_subscription,
            "Get heart rate data": self.get_heart_rate_data,
            "Get sandbox heartrate documents": self.get_sandbox_heartrate_documents,
        }

    async def get_personal_info(self):
        """
        Fetch the single personal info document of the user.

        Makes an authenticated GET request to the /v2/usercollection/personal_info endpoint to retrieve the personal information.

        Returns:
            dict: The personal info document if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/personal_info"
        try:
            response = await self.session.get(url)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.HTTPError as err:
            # Handle specific HTTP errors
            if response.status_code == 400:
                return {"error": "Client Exception", "message": str(err)}
            elif response.status_code == 401:
                return {"error": "Unauthorized access", "message": str(err)}
            elif response.status_code == 403:
                return {"error": "Access forbidden", "message": str(err)}
            elif response.status_code == 429:
                return {"error": "Request Rate Limit Exceeded", "message": str(err)}
            else:
                raise

    async def get_usercollection_tag(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Retrieve multiple tag documents from the user collection.

        :param start_date: Optional start date for filtering the tag documents.
        :param end_date: Optional end date for filtering the tag documents.
        :param next_token: Optional token for pagination to get the next set of results.
        :return: JSON response from the API containing the tag documents.
        :raises: requests.exceptions.HTTPError: If an error occurs during the API request.
        """
        url = f"{self.base_uri}/v2/usercollection/tag"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Handle specific HTTP errors if needed, here we re-raise to propagate the error
            raise e

    async def get_sandbox_usercollection_tags(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple tag documents from the sandbox user collection.

        :param start_date: Optional. The start date to filter the documents.
        :param end_date: Optional. The end date to filter the documents.
        :param next_token: Optional. The token for pagination to get the next set of results.

        :return: JSON response from the API if the request is successful.
        :raises requests.exceptions.HTTPError: If the request to the API fails.
        """
        endpoint = f"{self.base_uri}/v2/sandbox/usercollection/tag"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_enhanced_tag_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple enhanced tag documents from the user collection.

        :param start_date: Optional start date for filtering the documents.
        :param end_date: Optional end date for filtering the documents.
        :param next_token: Optional token for pagination.
        :return: JSON response with the list of enhanced tag documents.
        :raises requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/enhanced_tag"
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_sandbox_usercollection_enhanced_tag(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple enhanced tag documents from the sandbox user collection.

        Parameters:
        - self: Reference to the current object
        - start_date (str, optional): The start date for filtering the documents.
        - end_date (str, optional): The end date for filtering the documents.
        - next_token (str, optional): Token for pagination to fetch the next set of documents.

        Returns:
        - JSON response from the API containing the enhanced tag documents.

        Raises:
        - requests.exceptions.HTTPError: If an HTTP error occurs during the API call.
        """
        endpoint = f"{self.base_uri}/v2/sandbox/usercollection/enhanced_tag"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_multiple_workout_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple workout documents from the API endpoint with optional query parameters for filtering.

        :param start_date: The start date for filtering workout documents.
        :param end_date: The end date for filtering workout documents.
        :param next_token: The token for fetching the next set of workout documents.
        :return: JSON response from the API endpoint.
        :raises: HTTPError for any errors encountered during the request.
        """
        url = f"{self.base_uri}/v2/usercollection/workout"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "next_token": next_token,
        }

        try:
            response = await self.session.get(
                url, params={k: v for k, v in params.items() if v is not None}
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_sandbox_user_workouts(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple workout documents from the sandbox user collection within a date range.

        Parameters:
        - self: Reference to the instance of the containing class.
        - start_date (str, optional): The start date for fetching workouts.
        - end_date (str, optional): The end date for fetching workouts.
        - next_token (str, optional): Token to fetch the next set of workouts.

        Returns:
        - dict: JSON response from the API containing workout documents.

        Raises:
        - requests.exceptions.HTTPError: If an error occurs during the request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/workout"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise SystemExit(e)

    async def get_multiple_session_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple session documents from the /v2/usercollection/session endpoint.

        Parameters:
            start_date (str, optional): The start date for filtering sessions.
            end_date (str, optional): The end date for filtering sessions.
            next_token (str, optional): Token for pagination to fetch next set of sessions.

        Returns:
            dict: JSON response containing session documents.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/session"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e), "status_code": e.response.status_code}

    async def get_sandbox_session_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Retrieve multiple session documents from the sandbox endpoint.

        Parameters:
        - self: The class instance containing base_uri and session.
        - start_date (str, optional): The start date for the session documents in ISO 8601 format.
        - end_date (str, optional): The end date for the session documents in ISO 8601 format.
        - next_token (str, optional): The token for fetching the next set of session documents.

        Returns:
        - dict: The JSON response from the API containing the session documents.

        Raises:
        - requests.exceptions.HTTPError: If an HTTP error occurs during the request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/session"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "next_token": next_token,
        }

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(err)

    async def get_multiple_daily_activity_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetches multiple daily activity documents within the specified date range or next_token.

        Args:
            start_date (str, optional): The start date for fetching activity documents.
            end_date (str, optional): The end date for fetching activity documents.
            next_token (str, optional): Token for fetching the next set of documents.

        Returns:
            dict: The JSON response from the API containing the daily activity documents.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/daily_activity"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "next_token": next_token,
        }
        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Handle specific HTTP errors if needed
            raise e

    async def get_sandbox_usercollection_daily_activity(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetches multiple daily activity documents from the sandbox user collection.

        Args:
            start_date (str, optional): The start date for the data retrieval period.
            end_date (str, optional): The end date for the data retrieval period.
            next_token (str, optional): Token for fetching the next page of results.

        Returns:
            dict: JSON response containing the daily activity documents.

        Raises:
            HTTPError: An error occurred during the request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_activity"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "next_token": next_token,
        }

        try:
            response = await self.session.get(
                url, params={k: v for k, v in params.items() if v is not None}
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e), "status_code": response.status_code}

    async def get_daily_sleep(self, start_date=None, end_date=None, next_token=None):
        """
        Fetches multiple daily sleep documents from the API.

        Parameters:
        - start_date (str): Optional. The start date for the sleep data.
        - end_date (str): Optional. The end date for the sleep data.
        - next_token (str): Optional. Token for fetching the next set of results.

        Returns:
        - dict: JSON response from the API with daily sleep data.

        Raises:
        - requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        endpoint = f"{self.base_uri}/v2/usercollection/daily_sleep"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_sandbox_usercollection_daily_sleep(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple daily sleep documents from the Oura sandbox user collection.

        :param start_date: (Optional) The start date for filtering the sleep data.
        :param end_date: (Optional) The end date for filtering the sleep data.
        :param next_token: (Optional) The token for pagination to fetch the next set of results.
        :return: JSON response from the API.
        :raises requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_sleep"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_multiple_daily_spo2_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple daily SpO2 documents within a specified date range from the Oura API.

        :param start_date: The start date for the range of daily SpO2 documents.
        :param end_date: The end date for the range of daily SpO2 documents.
        :param next_token: The token for paginated results.
        :return: JSON response from the Oura API.
        """
        url = f"{self.base_uri}/v2/usercollection/daily_spo2"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "next_token": next_token,
        }
        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            return {"error": str(http_err)}

    async def get_sandbox_daily_spo2(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple daily SpO2 (blood oxygen level) documents from the sandbox environment.

        Parameters:
        - start_date (str, optional): The start date for the data range in 'YYYY-MM-DD' format.
        - end_date (str, optional): The end date for the data range in 'YYYY-MM-DD' format.
        - next_token (str, optional): The token for fetching the next set of results.

        Returns:
        - dict: The JSON response containing the daily SpO2 data or an error message.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_spo2"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            return {"error": str(http_err)}

    async def get_daily_readiness(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple daily readiness documents within the specified date range.

        Args:
            start_date (str, optional): The start date for fetching data in YYYY-MM-DD format.
            end_date (str, optional): The end date for fetching data in YYYY-MM-DD format.
            next_token (str, optional): Token for pagination to retrieve the next set of results.

        Returns:
            dict: The JSON response from the API.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        endpoint = f"{self.base_uri}/v2/usercollection/daily_readiness"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "next_token": next_token,
        }

        # Filter out parameters that are None
        params = {k: v for k, v in params.items() if v is not None}

        try:
            response = await self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # You may want to add additional logging or error handling here
            raise e

    async def get_sandbox_daily_readiness(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple daily readiness documents from the sandbox environment.

        Parameters:
        - start_date (str, optional): The start date for the query in YYYY-MM-DD format.
        - end_date (str, optional): The end date for the query in YYYY-MM-DD format.
        - next_token (str, optional): The token for fetching the next set of results.

        Returns:
        - dict: The JSON response from the API.

        Raises:
        - requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_readiness"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_user_sleep_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetches multiple sleep documents for the user within the specified date range and pagination token.

        Parameters:
        - start_date: Optional; The start date for the query in 'YYYY-MM-DD' format.
        - end_date: Optional; The end date for the query in 'YYYY-MM-DD' format.
        - next_token: Optional; Token for pagination to fetch the next set of results.

        Returns:
        - A JSON response with the sleep documents data.

        Raises:
        - HTTPError: If an error occurs during the request.
        """
        endpoint = f"{self.base_uri}/v2/usercollection/sleep"
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e), "status_code": response.status_code}

    async def get_sandbox_user_sleep_data(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple sleep documents for the sandbox user collection.

        Args:
            start_date (str, optional): The start date for the data retrieval in YYYY-MM-DD format.
            end_date (str, optional): The end date for the data retrieval in YYYY-MM-DD format.
            next_token (str, optional): The token for retrieving the next set of results.

        Returns:
            dict: The JSON response from the API containing the sleep documents.

        Raises:
            HTTPError: If the HTTP request returns an unsuccessful status code.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/sleep"
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise SystemError(err)

    async def get_sleep_time_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple sleep time documents from the Oura API.

        Parameters:
            start_date (str, optional): The start date for the range of sleep time documents.
            end_date (str, optional): The end date for the range of sleep time documents.
            next_token (str, optional): The token for pagination to fetch the next set of documents.

        Returns:
            dict: The JSON response from the API containing the sleep time documents.

        Raises:
            requests.exceptions.HTTPError: If an error occurs while making the request.
        """
        url = f"{self.base_uri}/v2/usercollection/sleep_time"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_sandbox_sleep_time(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetches multiple sleep time documents from the sandbox environment.

        Args:
            start_date (str, optional): The start date for fetching sleep time data.
            end_date (str, optional): The end date for fetching sleep time data.
            next_token (str, optional): The token for fetching the next page of results.

        Returns:
            dict: The JSON response from the API.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/sleep_time"
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            return {"error": str(http_err)}

    async def get_rest_mode_period_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple rest mode period documents from the Oura API.

        :param start_date: Optional; The start date for filtering the documents.
        :param end_date: Optional; The end date for filtering the documents.
        :param next_token: Optional; Token for paginating through results.
        :return: JSON response from the API containing the rest mode period documents.
        :raises HTTPError: If an HTTP error occurs during the request.
        """
        url = f"{self.base_uri}/v2/usercollection/rest_mode_period"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
            return None
        except Exception as err:
            print(f"An error occurred: {err}")
            return None

    async def get_sandbox_rest_mode_periods(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetches multiple Rest Mode Period documents from the sandbox environment.

        Parameters:
        - self: Instance reference.
        - start_date (str, optional): The start date for filtering the rest mode periods.
        - end_date (str, optional): The end date for filtering the rest mode periods.
        - next_token (str, optional): Token to fetch the next set of rest mode periods.

        Returns:
        - dict: The JSON response from the API if the request is successful.

        Raises:
        - HTTPError: If an HTTP error occurs during the request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/rest_mode_period"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e), "status_code": e.response.status_code}

    async def get_ring_configuration(self, next_token=None):
        """
        Fetch multiple ring configuration documents from the API.

        Args:
            next_token (str, optional): Token for fetching the next set of results. Defaults to None.

        Returns:
            dict: JSON response from the API containing ring configuration documents.

        Raises:
            requests.exceptions.HTTPError: If an error occurs while making the request.
        """
        url = f"{self.base_uri}/v2/usercollection/ring_configuration"
        params = {}

        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_sandbox_ring_configuration(self, next_token=None):
        """
        Asynchronously fetches multiple ring configuration documents from the Oura sandbox.

        Args:
            next_token (str, optional): A token to retrieve the next page of results. Defaults to None.

        Returns:
            dict: The JSON response from the endpoint containing ring configuration documents.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/ring_configuration"
        params = {}
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(err)

    async def get_daily_stress(self, start_date=None, end_date=None, next_token=None):
        """
        Fetch multiple daily stress documents from the API.

        Parameters:
        - start_date (str, optional): The start date for fetching the stress documents.
        - end_date (str, optional): The end date for fetching the stress documents.
        - next_token (str, optional): The token for fetching the next set of stress documents.

        Returns:
        - dict: The JSON response from the API.

        Raises:
        - requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/daily_stress"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "next_token": next_token,
        }

        # Filter out None values from parameters
        params = {k: v for k, v in params.items() if v is not None}

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    async def get_daily_stress_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple daily stress documents from the sandbox environment.

        Parameters:
        - start_date (str, optional): The start date for the query in YYYY-MM-DD format.
        - end_date (str, optional): The end date for the query in YYYY-MM-DD format.
        - next_token (str, optional): Token for fetching the next set of results.

        Returns:
        - dict: The JSON response from the API.

        Raises:
        - HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_stress"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_daily_resilience_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple daily resilience documents from the user collection.

        :param start_date: The start date for the resilience documents in YYYY-MM-DD format (optional).
        :param end_date: The end date for the resilience documents in YYYY-MM-DD format (optional).
        :param next_token: The token for fetching the next set of results if available (optional).
        :return: JSON response containing daily resilience documents.
        :raises requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        endpoint = f"{self.base_uri}/v2/usercollection/daily_resilience"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "next_token": next_token,
        }
        # Remove any keys with value None to avoid sending them in the request
        params = {key: value for key, value in params.items() if value is not None}

        try:
            response = await self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Handle specific HTTP errors based on status codes
            if response.status_code == 400:
                print("Client Exception")
            elif response.status_code == 401:
                print("Unauthorized access exception. Check your access token.")
            elif response.status_code == 403:
                print("Access forbidden. Subscription to Oura has expired.")
            elif response.status_code == 429:
                print("Request Rate Limit Exceeded.")
            elif response.status_code == 422:
                print("Validation Error")
            else:
                print(f"HTTP error occurred: {e}")
            raise

    async def get_sandbox_daily_resilience(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetches multiple daily resilience documents from the sandbox environment.

        Parameters:
        - start_date (str, optional): The start date for the data retrieval.
        - end_date (str, optional): The end date for the data retrieval.
        - next_token (str, optional): The token for fetching the next set of results.

        Returns:
        - dict: The JSON response from the API endpoint.

        Raises:
        - requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_resilience"
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            # Log the error or handle accordingly
            raise SystemExit(err)

    async def get_daily_cardiovascular_age(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple daily cardiovascular age documents within a specified date range.

        Parameters:
        - start_date (str, optional): The start date for fetching records in YYYY-MM-DD format.
        - end_date (str, optional): The end date for fetching records in YYYY-MM-DD format.
        - next_token (str, optional): Token for fetching the next set of results.

        Returns:
        - dict: The JSON response from the API containing daily cardiovascular age documents.

        Raises:
        - requests.exceptions.HTTPError: For HTTP related errors such as 400, 401, 403, 422, and 429 status codes.
        """
        endpoint = f"{self.base_uri}/v2/usercollection/daily_cardiovascular_age"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "next_token": next_token,
        }
        # Remove None values from params
        params = {key: value for key, value in params.items() if value is not None}

        try:
            response = await self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_daily_cardiovascular_age(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetches multiple daily cardiovascular age documents from the sandbox.

        Args:
            start_date (str, optional): The start date for filtering the documents.
            end_date (str, optional): The end date for filtering the documents.
            next_token (str, optional): The token for fetching the next page of results.

        Returns:
            dict: The JSON response from the API.

        Raises:
            requests.exceptions.HTTPError: If the request fails due to an HTTP error.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_cardiovascular_age"
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    async def get_vo2_max_documents(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple Vo2 Max documents from the Oura API.

        Parameters:
            - start_date (str, optional): The start date for filtering the documents.
            - end_date (str, optional): The end date for filtering the documents.
            - next_token (str, optional): The token for fetching the next set of documents.

        Returns:
            - dict: JSON response from the Oura API.

        Raises:
            - requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/vO2_max"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise requests.exceptions.HTTPError(f"HTTP error occurred: {err}")

    async def get_sandbox_usercollection_vo2_max(
        self, start_date=None, end_date=None, next_token=None
    ):
        """
        Fetch multiple VO2 Max documents from the sandbox environment.

        :param start_date: Optional; Filter documents by start date.
        :param end_date: Optional; Filter documents by end date.
        :param next_token: Optional; Token for fetching the next page of results.
        :return: JSON response with VO2 Max documents or error information.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/vO2_max"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            return {"error": str(http_err), "status_code": response.status_code}

    async def get_single_tag_document(self, document_id):
        """
        Fetch a single tag document by its document ID.

        Args:
        document_id (str): The ID of the document to be retrieved.

        Returns:
        dict: JSON response from the API if the request is successful.

        Raises:
        HTTPError: If the request fails due to client or server error.
        """
        url = f"{self.base_uri}/v2/usercollection/tag/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    async def get_single_tag_document(self, document_id):
        """
        Fetches a single tagged document from the sandbox user collection.

        Args:
            document_id (str): The ID of the document to retrieve.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/tag/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as error:
            # Handle errors such as 400, 401, 403, 404, 422, 429
            return {"error": str(error), "status_code": response.status_code}

    async def get_enhanced_tag_document(self, document_id):
        """
        Fetch a single enhanced tag document by its document ID.

        Args:
        document_id (str): The ID of the document to retrieve.

        Returns:
        dict: The JSON response from the API.

        Raises:
        requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/enhanced_tag/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Handle different error status codes appropriately
            if response.status_code == 404:
                raise Exception("Not Found: The requested document does not exist.")
            elif response.status_code == 400:
                raise Exception("Client Exception: Bad Request.")
            elif response.status_code == 401:
                raise Exception(
                    "Unauthorized: Access token is expired, malformed, or revoked."
                )
            elif response.status_code == 403:
                raise Exception(
                    "Access Forbidden: The user's subscription has expired."
                )
            elif response.status_code == 429:
                raise Exception("Too Many Requests: Request rate limit exceeded.")
            elif response.status_code == 422:
                raise Exception("Validation Error: Invalid input parameters.")
            else:
                raise e

    async def get_sandbox_single_enhanced_tag_document(self, document_id):
        """
        Fetch a single enhanced tag document from the sandbox environment by document ID.

        Args:
            document_id (str): The ID of the document to fetch.

        Returns:
            dict: JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If the request encounters an HTTP error.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/enhanced_tag/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Log the error or handle it accordingly
            raise e

    async def get_single_workout_document(self, document_id):
        """
        Fetch a single workout document from the user's collection by document ID.

        Args:
            document_id (str): The ID of the workout document to fetch.

        Returns:
            dict: JSON response from the API containing workout document details.

        Raises:
            HTTPError: If the request to the API fails.
        """
        url = f"{self.base_uri}/v2/usercollection/workout/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            return {"error": str(http_err)}

    async def get_sandbox_single_workout_document(self, document_id):
        """
        Fetches a single workout document from the sandbox environment using the specified document_id.

        Args:
            document_id (str): The unique identifier of the workout document.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If an error occurs during the request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/workout/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            # Optionally, you can add custom error handling logic here
            raise err

    async def get_single_session_document(self, document_id):
        """
        Fetches a single session document by document_id.

        Args:
            document_id (str): The ID of the document to fetch.

        Returns:
            dict: The JSON response from the API.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/session/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Optionally log or handle the error further
            raise e

    async def get_sandbox_single_session_document(self, document_id):
        """
        Fetch a single session document from the sandbox user collection.

        Parameters:
        - document_id (str): The ID of the document to retrieve.

        Returns:
        - dict: The JSON response from the API.

        Raises:
        - HTTPError: If an HTTP error occurs during the request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/session/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            # Log or handle the HTTP error as needed
            raise http_err

    async def get_single_daily_activity_document(self, document_id):
        """
        Fetches a single daily activity document by document ID.

        Args:
            document_id (str): The ID of the daily activity document to fetch.

        Returns:
            dict: JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/daily_activity/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            # Handle known HTTP errors by status code
            if response.status_code == 404:
                raise ValueError("Daily activity document not found.") from http_err
            elif response.status_code == 400:
                raise ValueError("Client error.") from http_err
            elif response.status_code == 401:
                raise ValueError("Unauthorized access.") from http_err
            elif response.status_code == 403:
                raise ValueError("Access forbidden.") from http_err
            elif response.status_code == 429:
                raise ValueError("Request rate limit exceeded.") from http_err
            elif response.status_code == 422:
                raise ValueError("Validation error.") from http_err
            else:
                raise

    async def get_sandbox_daily_activity_document(self, document_id):
        """
        Fetch a single daily activity document from the sandbox environment.

        Args:
            document_id (str): The ID of the daily activity document to retrieve.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If the request results in an HTTP error.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_activity/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            # Handle specific HTTP errors
            if response.status_code == 404:
                raise ValueError("Document not found") from err
            elif response.status_code == 400:
                raise ValueError("Client exception") from err
            elif response.status_code == 401:
                raise ValueError(
                    "Unauthorized access - Token may be expired, malformed, or revoked"
                ) from err
            elif response.status_code == 403:
                raise ValueError(
                    "Access forbidden - Subscription may have expired"
                ) from err
            elif response.status_code == 429:
                raise ValueError("Request rate limit exceeded") from err
            elif response.status_code == 422:
                raise ValueError("Validation error") from err
            else:
                raise

    async def get_daily_sleep_document(self, document_id):
        """
        Fetch a single daily sleep document using the provided document ID.

        Args:
            document_id (str): The ID of the document to be fetched.

        Returns:
            dict: A JSON response containing the daily sleep document data.

        Raises:
            requests.exceptions.HTTPError: An error occurred when trying to fetch the document.
        """
        url = f"{self.base_uri}/v2/usercollection/daily_sleep/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Handle different types of errors accordingly
            if response.status_code == 404:
                print("Document not found.")
            elif response.status_code == 400:
                print("Client error.")
            elif response.status_code == 401:
                print("Unauthorized access. Check your access token.")
            elif response.status_code == 403:
                print("Access forbidden. Subscription may have expired.")
            elif response.status_code == 429:
                print("Request rate limit exceeded.")
            elif response.status_code == 422:
                print("Validation error.")
            raise e

    async def get_daily_sleep_document(self, document_id):
        """
        Fetch a single daily sleep document from the sandbox environment.

        Parameters:
        document_id (str): The ID of the daily sleep document to retrieve.

        Returns:
        dict: The JSON response from the API if the request is successful.

        Raises:
        HTTPError: If an error occurs during the HTTP request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_sleep/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
            raise
        except Exception as err:
            print(f"Other error occurred: {err}")
            raise

    async def get_single_daily_spo2_document(self, document_id):
        """
        Fetch a single daily SpO2 document by its document_id.

        Parameters:
            self: Reference to the current instance of the class.
            document_id (str): The unique identifier of the SpO2 document.

        Returns:
            dict: JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If the request results in an HTTP error.
        """
        url = f"{self.base_uri}/v2/usercollection/daily_spo2/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_sandbox_daily_spo2_document(self, document_id):
        """
        Fetch a single daily SpO2 document from the sandbox user collection using the provided document_id.

        Args:
            document_id (str): The ID of the document to retrieve.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs during the request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_spo2/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            # Handle specific HTTP errors and provide relevant information
            if response.status_code == 404:
                return {
                    "error": "Not Found",
                    "message": "The specified document was not found.",
                }
            elif response.status_code == 400:
                return {
                    "error": "Client Exception",
                    "message": "A client-side error occurred.",
                }
            elif response.status_code == 401:
                return {
                    "error": "Unauthorized",
                    "message": "Access token is expired, malformed, or revoked.",
                }
            elif response.status_code == 403:
                return {
                    "error": "Forbidden",
                    "message": "User's subscription has expired or data is not available.",
                }
            elif response.status_code == 429:
                return {
                    "error": "Too Many Requests",
                    "message": "Request rate limit exceeded.",
                }
            elif response.status_code == 422:
                return {
                    "error": "Validation Error",
                    "message": "Validation error occurred.",
                }
            else:
                return {"error": "HTTPError", "message": str(http_err)}

    async def get_single_daily_readiness_document(self, document_id):
        """
        Retrieve a single daily readiness document by its document ID.

        Args:
            document_id (str): The ID of the daily readiness document.

        Returns:
            dict: JSON response from the API.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/daily_readiness/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(err)

    async def get_daily_readiness_document(self, document_id):
        """
        Fetch a single daily readiness document from the sandbox.

        Args:
            document_id (str): The ID of the document to retrieve.

        Returns:
            dict: The JSON response from the API containing the daily readiness document data.

        Raises:
            requests.exceptions.HTTPError: If the request returns an HTTP error status.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_readiness/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(err)

    async def get_single_sleep_document(self, document_id):
        """
        Fetches a single sleep document from the user collection.

        Args:
            document_id (str): The ID of the sleep document to retrieve.

        Returns:
            dict: The JSON response from the API containing the sleep document details.

        Raises:
            HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/sleep/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            # Handle HTTP errors
            raise http_err

    async def get_single_sleep_document(self, document_id):
        """
        Fetches a single sleep document from the sandbox environment by document ID.

        Args:
            document_id (str): The ID of the sleep document to be fetched.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: An error occurred while making the HTTP request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/sleep/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_sleep_time_document(self, document_id):
        """
        Fetch a single sleep time document by document ID.

        Args:
            document_id (str): The ID of the sleep time document to retrieve.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/sleep_time/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            # Additional error handling could be added here if needed
            raise err

    async def get_sleep_time_document(self, document_id):
        """
        Fetches a single sleep time document from the Oura sandbox API.

        Args:
            document_id (str): The ID of the sleep time document to be fetched.

        Returns:
            dict: The JSON response from the API containing the sleep time document.

        Raises:
            requests.exceptions.HTTPError: An error occurred while making the request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/sleep_time/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Handle specific status codes or re-raise the exception
            if response.status_code == 404:
                raise Exception("Document not found") from e
            elif response.status_code == 400:
                raise Exception("Client Exception") from e
            elif response.status_code == 401:
                raise Exception("Unauthorized access. Check your token.") from e
            elif response.status_code == 403:
                raise Exception("Access forbidden. Check your subscription.") from e
            elif response.status_code == 429:
                raise Exception("Request rate limit exceeded.") from e
            elif response.status_code == 422:
                raise Exception("Validation error.") from e
            else:
                raise

    async def get_rest_mode_period_document(self, document_id):
        """
        Retrieve a single Rest Mode Period Document based on the provided document_id.

        Args:
            document_id (str): The ID of the document to retrieve.

        Returns:
            dict: The JSON response from the API.

        Raises:
            requests.exceptions.HTTPError: If an error occurs during the request.
        """
        url = f"{self.base_uri}/v2/usercollection/rest_mode_period/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"HTTPError: {e.response.status_code} - {e.response.reason}")
            print(e.response.text)
            raise

    async def get_rest_mode_period_document(self, document_id):
        """
        Retrieve a single rest mode period document from the sandbox environment.

        Parameters:
        - document_id (str): The ID of the document to retrieve.

        Returns:
        - dict: The JSON response from the API if successful.

        Raises:
        - requests.exceptions.HTTPError: For any HTTP error that occurs during the request.
        """
        url = (
            f"{self.base_uri}/v2/sandbox/usercollection/rest_mode_period/{document_id}"
        )

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise err

    async def get_single_ring_configuration_document(self, document_id):
        """
        Retrieve a single ring configuration document based on the provided document ID.

        Args:
            document_id (str): The ID of the document to retrieve.

        Returns:
            dict: The JSON response from the API.

        Raises:
            requests.exceptions.HTTPError: If the request fails due to an HTTP error.
        """
        url = f"{self.base_uri}/v2/usercollection/ring_configuration/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_ring_configuration_document(self, document_id):
        """
        Fetch a single ring configuration document from the sandbox user collection.

        Args:
            document_id (str): The ID of the document to be fetched.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/ring_configuration/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(err)

    async def get_single_daily_stress_document(self, document_id):
        """
        Fetch a single daily stress document by its document ID.

        :param document_id: The ID of the document to retrieve.
        :return: JSON response from the API.
        :raises requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/daily_stress/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            if response.status_code == 404:
                return {"error": "Document not found"}
            elif response.status_code == 400:
                return {"error": "Client exception"}
            elif response.status_code == 401:
                return {"error": "Unauthorized access exception"}
            elif response.status_code == 403:
                return {"error": "Access forbidden"}
            elif response.status_code == 429:
                return {"error": "Request rate limit exceeded"}
            elif response.status_code == 422:
                return {"error": "Validation error"}
            else:
                raise http_err

    async def get_daily_stress_document(self, document_id):
        """
        Retrieve a single daily stress document from the sandbox.

        Args:
            document_id (str): The ID of the document to retrieve.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If the request fails.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_stress/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(err)

    async def get_daily_resilience_document(self, document_id):
        """
        Fetch a single daily resilience document by its ID.

        Parameters:
        - document_id (str): The ID of the daily resilience document to fetch.

        Returns:
        - dict: The JSON response from the API if the request is successful.

        Raises:
        - HTTPError: If the request returns an error status code.
        """
        url = f"{self.base_uri}/v2/usercollection/daily_resilience/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            raise http_err

    async def get_single_daily_resilience_document(self, document_id):
        """
        Fetches a single daily resilience document from the sandbox.

        Parameters:
            self: The reference to the current instance.
            document_id (str): The ID of the document to retrieve.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            HTTPError: If the request to the API fails.
        """
        url = (
            f"{self.base_uri}/v2/sandbox/usercollection/daily_resilience/{document_id}"
        )
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def get_daily_cardiovascular_age_document(self, document_id):
        """
        Fetch a single daily cardiovascular age document using the provided document_id.

        Parameters:
        - document_id (str): The ID of the document to retrieve.

        Returns:
        - dict: JSON response from the API containing the document details.

        Raises:
        - requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = (
            f"{self.base_uri}/v2/usercollection/daily_cardiovascular_age/{document_id}"
        )

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            # Handle specific status codes
            if response.status_code == 404:
                return {"error": "Not Found"}
            elif response.status_code == 400:
                return {"error": "Client Exception"}
            elif response.status_code == 401:
                return {
                    "error": "Unauthorized access. Token may be expired or revoked."
                }
            elif response.status_code == 403:
                return {"error": "Access forbidden. Subscription may have expired."}
            elif response.status_code == 429:
                return {"error": "Request rate limit exceeded."}
            elif response.status_code == 422:
                return {"error": "Validation error."}
            else:
                raise http_err

    async def get_daily_cardiovascular_age(self, document_id):
        """
        Fetches a single daily cardiovascular age document from the sandbox environment.

        Args:
        document_id (str): The ID of the cardiovascular age document to retrieve.

        Returns:
        dict: A dictionary containing the cardiovascular age document data if successful.

        Raises:
        requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/daily_cardiovascular_age/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 400:
                print("Client Exception")
            elif response.status_code == 401:
                print(
                    "Unauthorized access exception. The access token may be expired, malformed or revoked."
                )
            elif response.status_code == 403:
                print(
                    "Access forbidden. The user's subscription to Oura may have expired and their data is not available via the API."
                )
            elif response.status_code == 404:
                print("Not Found. The requested document was not found.")
            elif response.status_code == 422:
                print("Validation Error")
            elif response.status_code == 429:
                print("Request Rate Limit Exceeded.")
            raise e

    async def get_vO2_max_document(self, document_id):
        """
        Fetch a single Vo2 Max document by its ID.

        Args:
            document_id (str): The ID of the Vo2 Max document to retrieve.

        Returns:
            dict: JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/usercollection/vO2_max/{document_id}"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise err

    async def get_sandbox_vo2_max_document(self, document_id):
        """
        Retrieve a single Vo2 Max document from the sandbox user collection.

        Args:
            document_id (str): The ID of the document to retrieve.

        Returns:
            dict: The JSON response from the API if the request is successful.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs during the request.
        """
        url = f"{self.base_uri}/v2/sandbox/usercollection/vO2_max/{document_id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise err

    async def list_webhook_subscriptions(self):
        """
        Asynchronously retrieves the list of webhook subscriptions.

        Makes a GET request to the /v2/webhook/subscription endpoint to fetch the
        current webhook subscriptions. Handles errors and returns the JSON response
        in case of a successful request.

        Returns:
            dict: The JSON response from the API containing webhook subscriptions.

        Raises:
            HTTPError: If an HTTP error occurs during the request.
        """
        url = f"{self.base_uri}/v2/webhook/subscription"
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise err

    async def create_webhook_subscription(
        self, callback_url, verification_token, event_type, data_type
    ):
        """
        Create a webhook subscription.

        Args:
            callback_url (str): The URL where the webhook payload will be sent.
            verification_token (str): A token to verify the webhook request.
            event_type (str): The type of event the webhook is subscribing to.
            data_type (str): The type of data to be sent in the webhook payload.

        Returns:
            dict: JSON response from the API.
        """
        url = f"{self.base_uri}/v2/webhook/subscription"
        payload = {
            "callback_url": callback_url,
            "verification_token": verification_token,
            "event_type": event_type,
            "data_type": data_type,
        }
        try:
            response = await self.session.post(url, json=payload)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            return {"error": str(http_err)}
        except Exception as err:
            return {"error": str(err)}

    async def get_webhook_subscription(self, id):
        """
        Get the details of a webhook subscription by its ID.

        :param id: The ID of the webhook subscription to retrieve.
        :return: The JSON response from the API.
        """
        url = f"{self.base_uri}/v2/webhook/subscription/{id}"

        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            # Handle specific error codes
            if response.status_code == 403:
                return {"error": "Webhook with specified id does not exist."}
            if response.status_code == 422:
                return {"error": "Validation Error"}
            # Raise the original HTTP error if not handled above
            raise http_err

    async def update_webhook_subscription(
        self, id, verification_token, callback_url=None, event_type=None, data_type=None
    ):
        """
        Update Webhook Subscription

        This function updates a webhook subscription with the specified ID using the provided parameters.

        Parameters:
            id (str): The ID of the webhook subscription to be updated.
            verification_token (str): The verification token required to update the subscription.
            callback_url (str, optional): The callback URL for the webhook subscription.
            event_type (str or None, optional): The type of event for the webhook subscription.
            data_type (str or None, optional): The data type for the webhook subscription.

        Returns:
            dict: The JSON response from the API if the update is successful.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/webhook/subscription/{id}"
        payload = {
            "verification_token": verification_token,
            "callback_url": callback_url,
            "event_type": event_type,
            "data_type": data_type,
        }

        try:
            response = await self.session.put(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e

    async def delete_webhook_subscription(self, id):
        """
        Delete Webhook Subscription.

        This function deletes a webhook subscription by its ID.

        Parameters:
        - id (str): The ID of the webhook subscription to delete.

        Returns:
        - JSON response if the deletion is unsuccessful.
        - None if the deletion is successful.

        Raises:
        - HTTPError: If the request returns an unsuccessful status code.
        """
        url = f"{self.base_uri}/v2/webhook/subscription/{id}"

        try:
            response = await self.session.delete(url)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if response.status_code == 403:
                return {"error": "Webhook with specified id does not exist."}
            elif response.status_code == 422:
                return {"error": "Validation Error"}
            else:
                raise err

        return None

    async def renew_webhook_subscription(self, id: str):
        """
        Renews a webhook subscription by the given subscription ID.

        Args:
            id (str): The ID of the webhook subscription to renew.

        Returns:
            dict: JSON response from the server.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs.
        """
        url = f"{self.base_uri}/v2/webhook/subscription/renew/{id}"

        try:
            response = await self.session.put(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise err

    async def get_heart_rate_data(
        self, start_datetime=None, end_datetime=None, next_token=None
    ):
        """
        Retrieve multiple heart rate documents within the specified date range.

        :param start_datetime: The start datetime for filtering data (optional)
        :param end_datetime: The end datetime for filtering data (optional)
        :param next_token: Token for pagination to retrieve next set of results (optional)
        :return: JSON response from the API containing heart rate data
        """
        url = f"{self.base_uri}/v2/usercollection/heartrate"
        params = {}
        if start_datetime:
            params["start_datetime"] = start_datetime
        if end_datetime:
            params["end_datetime"] = end_datetime
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            return {"error": str(err)}

    async def get_sandbox_heartrate_documents(
        self, start_datetime=None, end_datetime=None, next_token=None
    ):
        """
        Fetch multiple heart rate documents from the sandbox environment.

        Parameters:
            start_datetime (str, optional): The start datetime to filter results.
            end_datetime (str, optional): The end datetime to filter results.
            next_token (str, optional): The token for pagination to get next set of results.

        Returns:
            dict: The JSON response from the API containing the heart rate documents.

        Raises:
            requests.exceptions.HTTPError: If an error occurs during the API request.
        """
        endpoint = f"{self.base_uri}/v2/sandbox/usercollection/heartrate"
        params = {}
        if start_datetime:
            params["start_datetime"] = start_datetime
        if end_datetime:
            params["end_datetime"] = end_datetime
        if next_token:
            params["next_token"] = next_token

        try:
            response = await self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e
