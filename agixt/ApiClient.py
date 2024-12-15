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


def verify_api_key(authorization: str = Header(None)):
    USING_JWT = True if getenv("USING_JWT").lower() == "true" else False
    AGIXT_API_KEY = getenv("AGIXT_API_KEY")
    DEFAULT_USER = getenv("DEFAULT_USER")
    authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    if DEFAULT_USER == "" or DEFAULT_USER is None or DEFAULT_USER == "None":
        DEFAULT_USER = "user"
    try:
        token = jwt.decode(
            jwt=authorization,
            key=AGIXT_API_KEY,
            algorithms=["HS256"],
            leeway=timedelta(hours=5),
        )
        return token["email"]
    except Exception as e:
        if authorization == AGIXT_API_KEY:
            return DEFAULT_USER
        if authorization != AGIXT_API_KEY:
            logging.info(f"Invalid API Key: {authorization}")
            raise HTTPException(status_code=401, detail="Invalid API Key")
    if AGIXT_API_KEY:
        if authorization is None:
            logging.info("Authorization header is missing")
            raise HTTPException(
                status_code=401, detail="Authorization header is missing"
            )
        authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
        if AGIXT_API_KEY == authorization:
            return DEFAULT_USER
        if USING_JWT:
            try:
                token = jwt.decode(
                    jwt=authorization,
                    key=AGIXT_API_KEY,
                    algorithms=["HS256"],
                    leeway=timedelta(hours=5),
                )
                return token["email"]
            except Exception as e:
                if authorization != AGIXT_API_KEY:
                    logging.info(f"Invalid API Key: {authorization}")
                    raise HTTPException(status_code=401, detail="Invalid API Key")
                return DEFAULT_USER
        if authorization != AGIXT_API_KEY:
            logging.info(f"Invalid API Key: {authorization}")
            raise HTTPException(status_code=401, detail="Invalid API Key")
    else:
        return DEFAULT_USER


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
