import os
import logging
import jwt
from agixtsdk import AGiXTSDK
from dotenv import load_dotenv
from fastapi import Header, HTTPException

load_dotenv()

USING_JWT = True if os.getenv("USING_JWT", "false").lower() == "true" else False
DB_CONNECTED = True if os.getenv("DB_CONNECTED", "false").lower() == "true" else False
WORKERS = int(os.getenv("UVICORN_WORKERS", 10))
AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", None)
ApiClient = AGiXTSDK(base_uri="http://localhost:7437", api_key=AGIXT_API_KEY)

# Defining these here to be referenced externally.
if DB_CONNECTED:
    from db.Agent import Agent, add_agent, delete_agent, rename_agent, get_agents
    from db.Chain import Chain
    from db.Prompts import Prompts
    from db.History import (
        get_conversation,
        delete_history,
        delete_message,
        get_conversations,
        new_conversation,
        log_interaction,
        update_message,
    )
else:
    from fb.Agent import Agent, add_agent, delete_agent, rename_agent, get_agents
    from fb.Chain import Chain
    from fb.Prompts import Prompts
    from fb.History import (
        get_conversation,
        delete_history,
        delete_message,
        get_conversations,
        new_conversation,
        log_interaction,
        update_message,
    )


def verify_api_key(authorization: str = Header(None)):
    load_dotenv()
    USING_JWT = True if os.getenv("USING_JWT", "false").lower() == "true" else False
    AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", None)
    DEFAULT_USER = os.getenv("DEFAULT_USER", "USER")
    if DEFAULT_USER == "":
        DEFAULT_USER = "USER"
    if AGIXT_API_KEY:
        if authorization is None:
            logging.info("Authorization header is missing")
            raise HTTPException(
                status_code=401, detail="Authorization header is missing"
            )
        authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
        if USING_JWT:
            try:
                token = jwt.decode(
                    jwt=authorization,
                    key=AGIXT_API_KEY,
                    algorithms=["HS256"],
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


def is_admin(email: str, api_key: str = None):
    if os.getenv("AGIXT_API_KEY", None) == api_key:
        return True
    db = True if os.getenv("DB_CONNECTED", "false").lower() == "true" else False
    if db:
        from db.User import is_agixt_admin

        return is_agixt_admin(email=email, api_key=api_key)
    return False
