import os
import jwt
from agixtsdk import AGiXTSDK
from dotenv import load_dotenv
from fastapi import Header, HTTPException

load_dotenv()
AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", None)
USING_JWT = True if os.getenv("USING_JWT", "false").lower() == "true" else False
DB_CONNECTED = True if os.getenv("DB_CONNECTED", "false").lower() == "true" else False
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
    )


def verify_api_key(authorization: str = Header(None)):
    if AGIXT_API_KEY:
        if authorization is None:
            raise HTTPException(
                status_code=401, detail="Authorization header is missing"
            )
        try:
            scheme, _, api_key = authorization.partition(" ")
            if scheme.lower() != "bearer":
                raise HTTPException(
                    status_code=401, detail="Invalid authentication scheme"
                )
            if USING_JWT:
                token = jwt.decode(
                    jwt=api_key,
                    key=AGIXT_API_KEY,
                    algorithms=["HS256"],
                )
                return token["email"]
            else:
                if api_key != AGIXT_API_KEY:
                    raise HTTPException(status_code=401, detail="Invalid API Key")
                return "USER"
        except Exception as e:
            raise HTTPException(status_code=401, detail="Invalid API Key")
    else:
        return "USER"
