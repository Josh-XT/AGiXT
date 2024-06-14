import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- WEIBO_CLIENT_ID: Weibo OAuth client ID
- WEIBO_CLIENT_SECRET: Weibo OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `WEIBO_CLIENT_ID` and `WEIBO_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Weibo OAuth

- email
- statuses_update
"""


class WeiboSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("WEIBO_CLIENT_ID")
        self.client_secret = getenv("WEIBO_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://api.weibo.com/oauth2/access_token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.weibo.com/2/account/get_uid.json"
        response = requests.get(
            uri,
            params={"access_token": self.access_token},
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                params={"access_token": self.access_token},
            )
        try:
            uid_response = response.json()
            uid = uid_response["uid"]

            uri_info = f"https://api.weibo.com/2/users/show.json?uid={uid}"
            response = requests.get(
                uri_info,
                params={"access_token": self.access_token},
            )
            data = response.json()

            email = data.get(
                "email", None
            )  # Assuming you have permissions to email scope
            first_name = data["name"]
            last_name = ""  # Weibo does not provide a separate field for last name
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Weibo",
            )

    def send_message(self, status):
        uri = "https://api.weibo.com/2/statuses/update.json"
        data = {
            "access_token": self.access_token,
            "status": status,
        }

        response = requests.post(
            uri,
            data=data,
        )

        if response.status_code == 401:
            self.access_token = self.get_new_token()
            data["access_token"] = self.access_token
            response = requests.post(
                uri,
                data=data,
            )
        return response.json()


def sina_weibo_sso(code, redirect_uri=None) -> WeiboSSO:
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
        f"https://api.weibo.com/oauth2/access_token",
        data={
            "client_id": getenv("WEIBO_CLIENT_ID"),
            "client_secret": getenv("WEIBO_CLIENT_SECRET"),
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Weibo access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return WeiboSSO(access_token=access_token, refresh_token=refresh_token)
