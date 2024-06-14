import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- WECHAT_CLIENT_ID: WeChat OAuth client ID
- WECHAT_CLIENT_SECRET: WeChat OAuth client secret

Required scopes for WeChat SSO:

- snsapi_userinfo
"""


class WeChatSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("WECHAT_CLIENT_ID")
        self.client_secret = getenv("WECHAT_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.get(
            "https://api.weixin.qq.com/sns/oauth2/refresh_token",
            params={
                "appid": self.client_id,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.weixin.qq.com/sns/userinfo"
        response = requests.get(
            uri,
            params={
                "access_token": self.access_token,
                "openid": self.client_id,
                "lang": "en",
            },
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                params={
                    "access_token": self.access_token,
                    "openid": self.client_id,
                    "lang": "en",
                },
            )
        try:
            data = response.json()
            first_name = data["nickname"]
            last_name = ""  # WeChat does not provide last name
            email = data.get("email")  # WeChat may not provide email
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from WeChat",
            )


def wechat_sso(code, redirect_uri=None) -> WeChatSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    response = requests.get(
        "https://api.weixin.qq.com/sns/oauth2/access_token",
        params={
            "appid": getenv("WECHAT_CLIENT_ID"),
            "secret": getenv("WECHAT_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting WeChat access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return WeChatSSO(access_token=access_token, refresh_token=refresh_token)
