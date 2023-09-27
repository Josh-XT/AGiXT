import os
from fastapi import Header, HTTPException
from dotenv import load_dotenv

load_dotenv()
AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", None)


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
