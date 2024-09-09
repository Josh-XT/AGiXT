from Extensions import Extensions
import requests


class oura(Extensions):
    """
    The Oura extension for AGiXT enables you to interact with the Oura API to retrieve health and wellness data for the user.
    """

    def __init__(self, OURA_API_KEY: str = "", **kwargs):
        self.base_uri = "https://api.ouraring.com"
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {OURA_API_KEY}"})
        self.commands = {
            "Get personal info": self.get_personal_info,
            "Get usercollection tag": self.get_usercollection_tag,
            "Get enhanced tag documents": self.get_enhanced_tag_documents,
            "Get multiple workout documents": self.get_multiple_workout_documents,
            "Get multiple session documents": self.get_multiple_session_documents,
            "Get multiple daily activity documents": self.get_multiple_daily_activity_documents,
            "Get daily sleep": self.get_daily_sleep,
            "Get multiple daily spo2 documents": self.get_multiple_daily_spo2_documents,
            "Get daily readiness": self.get_daily_readiness,
            "Get user sleep documents": self.get_user_sleep_documents,
            "Get sleep time documents": self.get_sleep_time_documents,
            "Get rest mode period documents": self.get_rest_mode_period_documents,
            "Get ring configuration": self.get_ring_configuration,
            "Get daily stress": self.get_daily_stress,
            "Get daily resilience documents": self.get_daily_resilience_documents,
            "Get daily cardiovascular age": self.get_daily_cardiovascular_age,
            "Get vo2 max documents": self.get_vo2_max_documents,
            "Get single tag document": self.get_single_tag_document,
            "Get enhanced tag document": self.get_enhanced_tag_document,
            "Get single workout document": self.get_single_workout_document,
            "Get single session document": self.get_single_session_document,
            "Get single daily activity document": self.get_single_daily_activity_document,
            "Get daily sleep document": self.get_daily_sleep_document,
            "Get single daily spo2 document": self.get_single_daily_spo2_document,
            "Get single daily readiness document": self.get_single_daily_readiness_document,
            "Get single sleep document": self.get_single_sleep_document,
            "Get sleep time document": self.get_sleep_time_document,
            "Get rest mode period document": self.get_rest_mode_period_document,
            "Get single ring configuration document": self.get_single_ring_configuration_document,
            "Get single daily stress document": self.get_single_daily_stress_document,
            "Get daily resilience document": self.get_daily_resilience_document,
            "Get daily cardiovascular age document": self.get_daily_cardiovascular_age_document,
            "Get vo2 max document": self.get_vO2_max_document,
            "Get heart rate data": self.get_heart_rate_data,
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
