import os
from agixtsdk import AGiXTSDK
from dotenv import load_dotenv
from fastapi import Header, HTTPException

load_dotenv()
AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", None)
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
    # Check if the API key is set up in the environment
    if AGIXT_API_KEY:
        # If no authorization header is provided, raise an error
        if authorization is None:
            raise HTTPException(
                status_code=400, detail="Authorization header is missing"
            )
        scheme, _, api_key = authorization.partition(" ")
        # If the scheme isn't "Bearer", raise an error
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=400, detail="Authorization scheme is not Bearer"
            )
        # If the provided API key doesn't match the expected one, raise an error
        if api_key != AGIXT_API_KEY:
            raise HTTPException(status_code=403, detail="Invalid API Key")
        return api_key
    else:
        return 1
