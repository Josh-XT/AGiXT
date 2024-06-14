import json
import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- FORMSTACK_CLIENT_ID: Formstack OAuth client ID
- FORMSTACK_CLIENT_SECRET: Formstack OAuth client secret

Required APIs

Ensure that you have the necessary APIs enabled on your Formstack account,
then add the `FORMSTACK_CLIENT_ID` and `FORMSTACK_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Formstack OAuth

- formstack:read
- formstack:write
"""


class FormstackSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("FORMSTACK_CLIENT_ID")
        self.client_secret = getenv("FORMSTACK_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://www.formstack.com/api/v2/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://www.formstack.com/api/v2/user.json"
        response = requests.get(
            uri,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        try:
            data = response.json()
            first_name = data["first_name"]
            last_name = data["last_name"]
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Formstack",
            )

    def send_form_submission(self, form_id, submission_data):
        form_submission_url = (
            f"https://www.formstack.com/api/v2/form/{form_id}/submission.json"
        )
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            form_submission_url,
            headers=headers,
            data=json.dumps(submission_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                form_submission_url,
                headers=headers,
                data=json.dumps(submission_data),
            )
        return response.json()


def formstack_sso(code, redirect_uri=None) -> FormstackSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )
    response = requests.post(
        f"https://www.formstack.com/api/v2/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": getenv("FORMSTACK_CLIENT_ID"),
            "client_secret": getenv("FORMSTACK_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Formstack access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return FormstackSSO(access_token=access_token, refresh_token=refresh_token)
