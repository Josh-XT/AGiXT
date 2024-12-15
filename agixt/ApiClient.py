import logging
import jwt
from agixtsdk import AGiXTSDK
from fastapi import Header, HTTPException
from Globals import getenv
from datetime import datetime, timedelta

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
WORKERS = int(getenv("UVICORN_WORKERS"))
AGIXT_URI = getenv("AGIXT_URI")

# Defining these here to be referenced externally.
from Agent import Agent, add_agent, delete_agent, rename_agent, get_agents
from Chain import Chain
from Prompts import Prompts
from Conversations import Conversations
from MagicalAuth import verify_api_key


def get_api_client(authorization: str = Header(None)):
    authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    return AGiXTSDK(base_uri="http://localhost:7437", api_key=authorization)


def is_admin(email: str = "USER", api_key: str = None):
    return True
    # Commenting out functionality until testing is complete.
    AGIXT_API_KEY = getenv("AGIXT_API_KEY")
    if api_key is None:
        api_key = ""
    api_key = api_key.replace("Bearer ", "").replace("bearer ", "")
    if AGIXT_API_KEY == api_key:
        return True

    if email == "" or email is None or email == "None":
        email = getenv("DEFAULT_USER")
        if email == "" or email is None or email == "None":
            email = "USER"
    return is_agixt_admin(email=email, api_key=api_key)
    return False
