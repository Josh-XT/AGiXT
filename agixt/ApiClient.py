import os
import logging
import jwt
import hashlib
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


def validate_personal_access_token(token: str):
    """
    Validate a Personal Access Token and return the associated user's email.

    Args:
        token: The full PAT token string (e.g., agixt_abc123...)

    Returns:
        str: The user's email if valid

    Raises:
        HTTPException: If the token is invalid, expired, or revoked
    """
    from DB import get_session, PersonalAccessToken, User
    from MagicalAuth import hash_pat_token

    # Hash the token using HMAC-SHA256 for secure comparison
    token_hash = hash_pat_token(token)

    session = get_session()
    try:
        # Look up the token by its hash
        pat = (
            session.query(PersonalAccessToken)
            .filter(PersonalAccessToken.token_hash == token_hash)
            .first()
        )

        if not pat:
            raise HTTPException(status_code=401, detail="Invalid API Key")

        # Check if token is revoked
        if pat.is_revoked:
            raise HTTPException(status_code=401, detail="API Key has been revoked")

        # Check if token is expired
        if pat.expires_at and pat.expires_at < datetime.utcnow():
            raise HTTPException(status_code=401, detail="API Key has expired")

        # Get the user associated with this token
        user = session.query(User).filter(User.id == pat.user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API Key")

        # Update last_used_at
        pat.last_used_at = datetime.utcnow()
        session.commit()

        return user.email
    finally:
        session.close()


def verify_api_key(authorization: str = Header(None)):
    USING_JWT = True if getenv("USING_JWT").lower() == "true" else False
    AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", "")
    DEFAULT_USER = getenv("DEFAULT_USER")
    authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    if DEFAULT_USER == "" or DEFAULT_USER is None or DEFAULT_USER == "None":
        DEFAULT_USER = "user"

    # Check for Personal Access Token (PAT) format
    if authorization and authorization.startswith("agixt_"):
        return validate_personal_access_token(authorization)

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
                    raise HTTPException(status_code=401, detail="Invalid API Key")
                return DEFAULT_USER
        if authorization != AGIXT_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API Key")
    else:
        return DEFAULT_USER


def get_api_client(authorization: str = Header(None)):
    """
    Get an internal API client for backend-to-backend calls.

    This returns an InternalClient that implements the same interface as AGiXTSDK
    but calls internal methods directly without HTTP round-trips.

    Args:
        authorization: The API key/JWT token from the request header

    Returns:
        InternalClient: A client that can be used like AGiXTSDK but without HTTP overhead
    """
    from InternalClient import InternalClient

    authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    return InternalClient(api_key=authorization)


def is_admin(email: str = "USER", api_key: str = None):
    """
    Check if a user has admin-level access.
    Delegates to MagicalAuth.is_admin() for proper role-based checking.
    """
    from MagicalAuth import is_admin as magical_is_admin

    return magical_is_admin(email=email, api_key=api_key)
