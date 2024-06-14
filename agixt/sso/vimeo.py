import os
import json
import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- VIMEO_CLIENT_ID: Vimeo OAuth client ID
- VIMEO_CLIENT_SECRET: Vimeo OAuth client secret

Required APIs

Ensure you have the necessary APIs enabled in Vimeo's developer platform,
then add the `VIMEO_CLIENT_ID` and `VIMEO_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Vimeo OAuth

- public
- private
- video_files
"""


class VimeoSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("VIMEO_CLIENT_ID")
        self.client_secret = getenv("VIMEO_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://api.vimeo.com/oauth/access_token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.vimeo.com/me"
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
            first_name = data["name"].split()[0]
            last_name = data["name"].split()[-1]
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Vimeo",
            )

    def upload_video(self, video_file_path, video_title, video_description):
        uri = "https://api.vimeo.com/me/videos"
        response = requests.post(
            uri,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(
                {
                    "upload": {
                        "approach": "tus",
                        "size": str(os.path.getsize(video_file_path)),
                    },
                    "name": video_title,
                    "description": video_description,
                }
            ),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                uri,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(
                    {
                        "upload": {
                            "approach": "tus",
                            "size": str(os.path.getsize(video_file_path)),
                        },
                        "name": video_title,
                        "description": video_description,
                    }
                ),
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Error uploading video to Vimeo: {response.text}",
            )
        upload_link = response.json()["upload"]["upload_link"]
        with open(video_file_path, "rb") as video_file:
            tus_response = requests.patch(
                upload_link,
                data=video_file,
                headers={"Content-Type": "application/offset+octet-stream"},
            )
            if tus_response.status_code != 204:
                raise HTTPException(
                    status_code=tus_response.status_code,
                    detail=f"Error uploading video to Vimeo using upload link: {tus_response.text}",
                )
        return response.json()


def vimeo_sso(code, redirect_uri=None) -> VimeoSSO:
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
        "https://api.vimeo.com/oauth/access_token",
        data={
            "client_id": getenv("VIMEO_CLIENT_ID"),
            "client_secret": getenv("VIMEO_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Vimeo access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return VimeoSSO(access_token=access_token, refresh_token=refresh_token)
