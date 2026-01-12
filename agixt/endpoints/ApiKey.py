"""
Personal Access Token (API Key) Management Endpoints

These endpoints allow users to create, list, revoke, and regenerate personal access tokens
similar to GitHub's personal access tokens. Users can select specific scopes, agents, and
companies the token has access to, with the limitation that they can only grant permissions
they themselves have.
"""

from fastapi import APIRouter, Header, Depends, HTTPException
from MagicalAuth import MagicalAuth, verify_api_key, validate_personal_access_token
from Models import (
    PersonalAccessTokenCreate,
    PersonalAccessTokenResponse,
    PersonalAccessTokenCreatedResponse,
    PersonalAccessTokenListResponse,
    AvailableScopesResponse,
    AvailableAgentsResponse,
    AvailableCompaniesResponse,
    Detail,
)
from typing import List
from Globals import getenv
import logging

app = APIRouter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


@app.post(
    "/v1/api-keys",
    response_model=PersonalAccessTokenCreatedResponse,
    summary="Create a new personal access token",
    tags=["API Keys"],
)
async def create_api_key(
    token_data: PersonalAccessTokenCreate,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Create a new personal access token (API key) with specified scopes and access.

    **Important**: The actual token value is only shown once at creation time.
    Make sure to copy and store it securely.

    - **name**: A friendly name for the token (e.g., "CI/CD Pipeline", "Local Development")
    - **scopes**: List of scope names this token has access to
    - **agent_ids**: List of agent IDs this token can access (empty = all user's agents)
    - **company_ids**: List of company IDs this token can access (empty = all user's companies)
    - **expiration**: When the token expires - "1_day", "7_days", "30_days", "90_days", "1_year", "never"
    """
    auth = MagicalAuth(token=authorization)
    result = auth.create_personal_access_token(
        name=token_data.name,
        scopes=token_data.scopes,
        agent_ids=token_data.agent_ids or [],
        company_ids=token_data.company_ids or [],
        expiration=token_data.expiration,
    )
    return result


@app.get(
    "/v1/api-keys",
    response_model=PersonalAccessTokenListResponse,
    summary="List all personal access tokens",
    tags=["API Keys"],
)
async def list_api_keys(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    List all personal access tokens for the current user.

    Note: The actual token values are never returned for security.
    Only the token prefix (first 16 characters) is shown for identification.
    """
    auth = MagicalAuth(token=authorization)
    tokens = auth.list_personal_access_tokens()
    return {"tokens": tokens}


@app.get(
    "/v1/api-keys/{token_id}",
    response_model=PersonalAccessTokenResponse,
    summary="Get a specific personal access token",
    tags=["API Keys"],
)
async def get_api_key(
    token_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Get details of a specific personal access token.

    Note: The actual token value is never returned for security.
    """
    auth = MagicalAuth(token=authorization)
    token = auth.get_personal_access_token(token_id)
    return token


@app.delete(
    "/v1/api-keys/{token_id}",
    response_model=Detail,
    summary="Revoke a personal access token",
    tags=["API Keys"],
)
async def revoke_api_key(
    token_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Revoke (delete) a personal access token.

    Once revoked, the token can no longer be used to authenticate.
    This action cannot be undone.
    """
    auth = MagicalAuth(token=authorization)
    result = auth.revoke_personal_access_token(token_id)
    return result


@app.post(
    "/v1/api-keys/{token_id}/regenerate",
    response_model=PersonalAccessTokenCreatedResponse,
    summary="Regenerate a personal access token",
    tags=["API Keys"],
)
async def regenerate_api_key(
    token_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Regenerate a personal access token with a new value.

    This creates a new token value while keeping all the same settings
    (scopes, agent access, company access, expiration).

    The old token value will immediately stop working.

    **Important**: The new token value is only shown once.
    Make sure to copy and store it securely.
    """
    auth = MagicalAuth(token=authorization)
    result = auth.regenerate_personal_access_token(token_id)
    return result


@app.get(
    "/v1/api-keys/available/scopes",
    response_model=AvailableScopesResponse,
    summary="Get available scopes for token creation",
    tags=["API Keys"],
)
async def get_available_scopes(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Get all scopes the current user can grant to a personal access token.

    Users can only grant scopes they themselves have access to.
    Scopes are returned grouped by category for easier UI organization.
    """
    auth = MagicalAuth(token=authorization)
    result = auth.get_available_scopes_for_token_creation()
    return result


@app.get(
    "/v1/api-keys/available/agents",
    response_model=AvailableAgentsResponse,
    summary="Get available agents for token creation",
    tags=["API Keys"],
)
async def get_available_agents(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Get all agents the current user can grant access to for a personal access token.

    If no agents are specified when creating a token, the token will have access
    to all agents the user can access.
    """
    auth = MagicalAuth(token=authorization)
    agents = auth.get_available_agents_for_token_creation()
    return {"agents": agents}


@app.get(
    "/v1/api-keys/available/companies",
    response_model=AvailableCompaniesResponse,
    summary="Get available companies for token creation",
    tags=["API Keys"],
)
async def get_available_companies(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Get all companies the current user can grant access to for a personal access token.

    If no companies are specified when creating a token, the token will have access
    to all companies the user can access.
    """
    auth = MagicalAuth(token=authorization)
    companies = auth.get_available_companies_for_token_creation()
    return {"companies": companies}


@app.post(
    "/v1/api-keys/validate",
    summary="Validate a personal access token",
    tags=["API Keys"],
)
async def validate_api_key_endpoint(
    token: str,
):
    """
    Validate a personal access token and return its associated user and scopes.

    This endpoint is used internally to validate tokens during authentication.
    It does not require authentication itself.

    Note: This endpoint is rate-limited to prevent brute force attacks.
    """
    result = validate_personal_access_token(token)
    if not result["valid"]:
        # Do not expose internal validation error details to the client
        raise HTTPException(status_code=401, detail="Invalid token")

    # Don't return all details for security - just confirm validity
    return {
        "valid": True,
        "user_id": result.get("user_id", ""),
        "scopes": result.get("scopes", []),
    }
