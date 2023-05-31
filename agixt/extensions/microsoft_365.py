from typing import List
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from Extensions import Extensions


class microsoft_365(Extensions):
    def __init__(
        self,
        MICROSOFT_365_CLIENT_ID: str = "",
        MICROSOFT_365_CLIENT_SECRET: str = "",
        MICROSOFT_365_REDIRECT_URI: str = "",
        **kwargs,
    ):
        self.MICROSOFT_365_CLIENT_ID = MICROSOFT_365_CLIENT_ID
        self.MICROSOFT_365_CLIENT_SECRET = MICROSOFT_365_CLIENT_SECRET
        self.MICROSOFT_365_REDIRECT_URI = MICROSOFT_365_REDIRECT_URI
        if (
            self.MICROSOFT_365_CLIENT_ID
            and self.MICROSOFT_365_CLIENT_SECRET
            and self.MICROSOFT_365_REDIRECT_URI
        ):
            self.commands = {
                "Send Email with Microsoft 365": self.send_email,
                "Check Email with Microsoft 365": self.check_email,
                "Move Email with Microsoft 365": self.move_email,
            }
            try:
                if (
                    self.MICROSOFT_365_CLIENT_SECRET != "None"
                    and self.MICROSOFT_365_CLIENT_SECRET != ""
                ):
                    self.credentials = self.get_credentials()
            except:
                pass

    def get_credentials(self) -> Credentials:
        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": self.MICROSOFT_365_CLIENT_ID,
                    "client_secret": self.MICROSOFT_365_CLIENT_SECRET,
                    "redirect_uris": [self.MICROSOFT_365_REDIRECT_URI],
                    "auth_uri": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                    "token_uri": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                }
            },
            ["https://graph.microsoft.com/Mail.ReadWrite"],
        )

        return flow.run_local_server(port=0)

    def send_email(
        self, from_email: str, to_email: str, subject: str, content: str
    ) -> List[str]:
        try:
            message = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": content},
                    "toRecipients": [{"emailAddress": {"address": to_email}}],
                    "from": {"emailAddress": {"address": from_email}},
                },
                "saveToSentItems": "true",
            }

            service = build("graph.microsoft.com", "v1.0", credentials=self.credentials)
            response = (
                service.users().messages().send(userId="me", body=message).execute()
            )
            return [f"Email sent successfully. Message ID: {response['id']}"]

        except HttpError as error:
            return [f"Error sending email: {error}"]

    def check_email(self) -> List[str]:
        try:
            service = build("graph.microsoft.com", "v1.0", credentials=self.credentials)
            response = service.users().messages().list(userId="me").execute()
            emails = response.get("value", [])

            result = []
            for email in emails:
                result.append(f"Email ID: {email['id']}, Subject: {email['subject']}")

            return result

        except HttpError as error:
            return [f"Error checking email: {error}"]

    def move_email(self, message_id: str, destination_folder_id: str) -> List[str]:
        try:
            service = build("graph.microsoft.com", "v1.0", credentials=self.credentials)
            response = (
                service.users()
                .messages()
                .move(
                    userId="me",
                    id=message_id,
                    body={"destinationId": destination_folder_id},
                )
                .execute()
            )
            return [
                f"Email moved successfully. New folder ID: {response['parentFolderId']}"
            ]

        except HttpError as error:
            return [f"Error moving email: {error}"]
