
import os
from Extensions import Extensions
import json

try:
    import requests
except ImportError:
    import sys
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

class testmail(Extensions):
    def __init__(
        self,
        TESTMAIL_API_KEY: str = "",
        TESTMAIL_NAMESPACE: str = "",
        **kwargs,
    ):
        self.TESTMAIL_API_KEY = TESTMAIL_API_KEY
        self.TESTMAIL_NAMESPACE = TESTMAIL_NAMESPACE
        if self.TESTMAIL_API_KEY and self.TESTMAIL_NAMESPACE:
            self.commands = {
                "Create Email Address": self.create_email_address,
                "Get Emails": self.get_emails,
                "Get Email Content": self.get_email_content,
                "Get Spam Score": self.get_spam_score,
                "Get Spam Report": self.get_spam_report,
                "Delete Email": self.delete_email,
            }
        self.base_url = "https://api.testmail.app/api/json"
        self.headers = {"Authorization": f"Bearer {self.TESTMAIL_API_KEY}"}

    async def create_email_address(self, tag: str = "") -> str:
        '''
        Create a new email address in the testmail.app namespace

        Args:
        tag (str): Optional tag for the email address

        Returns:
        str: The newly created email address
        '''
        try:
            email = f"{self.TESTMAIL_NAMESPACE}"
            if tag:
                email += f".{tag}"
            email += "@inbox.testmail.app"
            return email
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_emails(self, tag: str = "", limit: int = 10, timestamp_from: int = None, timestamp_to: int = None, livequery: bool = False) -> str:
        '''
        Get emails from the testmail.app inbox

        Args:
        tag (str): Optional tag to filter emails
        limit (int): Number of emails to retrieve (default: 10)
        timestamp_from (int): Optional start timestamp in milliseconds
        timestamp_to (int): Optional end timestamp in milliseconds
        livequery (bool): Whether to use live query (default: False)

        Returns:
        str: JSON string containing the list of emails
        '''
        try:
            params = {
                "namespace": self.TESTMAIL_NAMESPACE,
                "pretty": "true",
                "limit": limit
            }
            if tag:
                params["tag"] = tag
            if timestamp_from:
                params["timestamp_from"] = timestamp_from
            if timestamp_to:
                params["timestamp_to"] = timestamp_to
            if livequery:
                params["livequery"] = "true"
            
            response = requests.get(self.base_url, params=params, headers=self.headers)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_email_content(self, email_id: str) -> str:
        '''
        Get the content of a specific email

        Args:
        email_id (str): The ID of the email to retrieve

        Returns:
        str: The content of the email
        '''
        try:
            params = {
                "namespace": self.TESTMAIL_NAMESPACE,
                "pretty": "true",
                "email_id": email_id
            }
            response = requests.get(f"{self.base_url}/email", params=params, headers=self.headers)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_spam_score(self, email_id: str) -> str:
        '''
        Get the spam score of a specific email

        Args:
        email_id (str): The ID of the email to check

        Returns:
        str: The spam score of the email
        '''
        try:
            params = {
                "namespace": self.TESTMAIL_NAMESPACE,
                "pretty": "true",
                "email_id": email_id
            }
            response = requests.get(f"{self.base_url}/email", params=params, headers=self.headers)
            response.raise_for_status()
            email_data = json.loads(response.text)
            return str(email_data.get('spam_score', 'N/A'))
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_spam_report(self, email_id: str) -> str:
        '''
        Get the spam report of a specific email

        Args:
        email_id (str): The ID of the email to check

        Returns:
        str: The spam report of the email
        '''
        try:
            params = {
                "namespace": self.TESTMAIL_NAMESPACE,
                "pretty": "true",
                "email_id": email_id
            }
            response = requests.get(f"{self.base_url}/email", params=params, headers=self.headers)
            response.raise_for_status()
            email_data = json.loads(response.text)
            return email_data.get('spam_report', 'N/A')
        except Exception as e:
            return f"Error: {str(e)}"

    async def delete_email(self, email_id: str) -> str:
        '''
        Delete a specific email

        Args:
        email_id (str): The ID of the email to delete

        Returns:
        str: The result of the delete operation
        '''
        try:
            params = {
                "namespace": self.TESTMAIL_NAMESPACE,
                "email_id": email_id
            }
            response = requests.delete(f"{self.base_url}/email", params=params, headers=self.headers)
            response.raise_for_status()
            return "Email deleted successfully"
        except Exception as e:
            return f"Error: {str(e)}"
