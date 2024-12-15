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
