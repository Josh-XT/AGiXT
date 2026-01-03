"""
Claude/Anthropic OAuth Extension for AGiXT

This extension provides OAuth integration with Anthropic's authentication system,
allowing users to authenticate with their Claude/Anthropic accounts and have
AGiXT manage their credentials securely.

Claude Code uses OAuth 2.0 with PKCE for authentication:
1. User is redirected to Anthropic's authorization page
2. User logs in with their Anthropic account
3. Authorization code is exchanged for access/refresh tokens
4. Tokens are stored and managed by AGiXT

Environment Variables Required:
- ANTHROPIC_CLIENT_ID: OAuth client ID from Anthropic Console
- ANTHROPIC_CLIENT_SECRET: OAuth client secret from Anthropic Console

Note: As of 2024, Anthropic's OAuth is primarily used for Claude.ai and Claude Code.
The API (api.anthropic.com) uses API keys, but Claude Code uses OAuth tokens.
"""

import os
import time
import json
import hashlib
import secrets
import base64
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import requests
from fastapi import HTTPException
from Extensions import Extensions
from Globals import getenv
from DB import (
    get_session,
    User,
    UserOAuth,
    OAuthProvider,
    get_new_id,
)

# OAuth Configuration for Anthropic/Claude
# These endpoints are for Claude's OAuth system
SCOPES = [
    "user:read",           # Read user profile
    "conversations:read",  # Read conversations
    "conversations:write", # Write conversations  
    "models:read",         # Access to models
    "usage:read",          # Read usage stats
]

# Anthropic OAuth endpoints (Claude)
AUTHORIZE = "https://claude.ai/oauth/authorize"
TOKEN_ENDPOINT = "https://claude.ai/oauth/token"
USERINFO_ENDPOINT = "https://claude.ai/api/auth/session"

# PKCE is required for Claude OAuth
PKCE_REQUIRED = True


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge"""
    # Generate a random code verifier
    code_verifier = secrets.token_urlsafe(64)[:128]
    
    # Create SHA256 hash and base64url encode it
    code_challenge = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge).decode().rstrip("=")
    
    return code_verifier, code_challenge


class AnthropicSSO:
    """
    Anthropic/Claude OAuth SSO Handler
    
    Handles OAuth authentication flow for Claude/Anthropic accounts.
    This allows users to authenticate with their Claude account and
    have AGiXT manage their Claude Code sessions.
    """
    
    def __init__(
        self,
        access_token: str = None,
        refresh_token: str = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("ANTHROPIC_CLIENT_ID")
        self.client_secret = getenv("ANTHROPIC_CLIENT_SECRET")
        self.user_info = self.get_user_info() if access_token else None
    
    def get_new_token(self) -> Dict[str, Any]:
        """Refresh the access token using the refresh token"""
        if not self.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="No refresh token available. Please re-authenticate.",
            )
        
        try:
            response = requests.post(
                TOKEN_ENDPOINT,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=30,
            )
            
            if response.status_code != 200:
                logging.error(f"Token refresh failed: {response.text}")
                raise HTTPException(
                    status_code=401,
                    detail="Failed to refresh token. Please re-authenticate.",
                )
            
            token_data = response.json()
            
            if "access_token" in token_data:
                self.access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]
            
            return token_data
            
        except requests.RequestException as e:
            logging.error(f"Token refresh request failed: {e}")
            raise HTTPException(
                status_code=401,
                detail="Token refresh failed. Please re-authenticate.",
            )
    
    def get_user_info(self) -> Dict[str, Any]:
        """Get user information from Claude/Anthropic"""
        if not self.access_token:
            raise HTTPException(
                status_code=401,
                detail="No access token available.",
            )
        
        try:
            # Try to get session/user info
            response = requests.get(
                USERINFO_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                },
                timeout=30,
            )
            
            if response.status_code == 401:
                # Try to refresh token
                self.get_new_token()
                response = requests.get(
                    USERINFO_ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Accept": "application/json",
                    },
                    timeout=30,
                )
            
            if response.status_code != 200:
                logging.error(f"Failed to get user info: {response.text}")
                raise HTTPException(
                    status_code=400,
                    detail="Failed to get user info from Anthropic.",
                )
            
            data = response.json()
            
            # Parse user info from Claude response
            user = data.get("user", data)
            
            return {
                "email": user.get("email", user.get("id", "")),
                "first_name": user.get("name", "").split()[0] if user.get("name") else "",
                "last_name": user.get("name", "").split()[-1] if user.get("name") else "",
                "anthropic_id": user.get("id"),
                "plan": user.get("plan", "free"),
            }
            
        except requests.RequestException as e:
            logging.error(f"User info request failed: {e}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Anthropic.",
            )


def sso(code: str, redirect_uri: str = None, code_verifier: str = None) -> AnthropicSSO:
    """
    Exchange authorization code for tokens
    
    Args:
        code: Authorization code from OAuth callback
        redirect_uri: Redirect URI used in authorization
        code_verifier: PKCE code verifier (required)
    
    Returns:
        AnthropicSSO instance with tokens
    """
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")
    
    client_id = getenv("ANTHROPIC_CLIENT_ID")
    client_secret = getenv("ANTHROPIC_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Anthropic OAuth not configured. Set ANTHROPIC_CLIENT_ID and ANTHROPIC_CLIENT_SECRET.",
        )
    
    # Clean up the code
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
    )
    
    # Build token request
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    
    # Add PKCE verifier if provided
    if code_verifier:
        token_data["code_verifier"] = code_verifier
    
    try:
        response = requests.post(
            TOKEN_ENDPOINT,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data=token_data,
            timeout=30,
        )
        
        if response.status_code != 200:
            logging.error(f"Token exchange failed: {response.text}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to exchange code for token: {response.text}",
            )
        
        tokens = response.json()
        
        return AnthropicSSO(
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
        )
        
    except requests.RequestException as e:
        logging.error(f"Token exchange request failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to exchange authorization code.",
        )


class anthropic_oauth(Extensions):
    """
    Anthropic OAuth Extension for AGiXT
    
    This extension provides OAuth integration with Anthropic/Claude,
    allowing users to connect their Claude accounts to AGiXT.
    
    Once connected, AGiXT can:
    - Manage Claude Code sessions
    - Access Claude API on behalf of the user
    - Sync conversations and preferences
    
    To use:
    1. Register an OAuth app at console.anthropic.com
    2. Set ANTHROPIC_CLIENT_ID and ANTHROPIC_CLIENT_SECRET
    3. Users authenticate via the OAuth flow
    4. AGiXT stores and refreshes tokens automatically
    """
    
    CATEGORY = "Authentication"
    friendly_name = "Anthropic/Claude OAuth"
    
    def __init__(
        self,
        ANTHROPIC_CLIENT_ID: str = "",
        ANTHROPIC_CLIENT_SECRET: str = "",
        **kwargs,
    ):
        self.client_id = ANTHROPIC_CLIENT_ID or getenv("ANTHROPIC_CLIENT_ID", "")
        self.client_secret = ANTHROPIC_CLIENT_SECRET or getenv("ANTHROPIC_CLIENT_SECRET", "")
        
        self.user = kwargs.get("user", "")
        self.user_id = kwargs.get("user_id", "")
        self.api_key = kwargs.get("api_key", "")
        self.agent_name = kwargs.get("agent_name", "gpt4free")
        
        # Store PKCE verifiers temporarily (in production, use session storage)
        self._pkce_verifiers: Dict[str, str] = {}
        
        self.commands = {
            "Get Anthropic OAuth URL": self.get_auth_url,
            "Check Anthropic Connection": self.check_connection,
            "Get Claude User Info": self.get_user_info,
            "Disconnect Anthropic Account": self.disconnect,
            "Refresh Anthropic Token": self.refresh_token,
            "Get Claude Access Token": self.get_access_token,
        }
    
    async def get_auth_url(self, state: str = "") -> str:
        """
        Get the OAuth authorization URL for Anthropic/Claude.
        
        Users should be redirected to this URL to authenticate with their
        Anthropic account.
        
        Args:
            state: Optional state parameter for CSRF protection
        
        Returns:
            str: Authorization URL to redirect user to
        """
        if not self.client_id:
            return "Error: ANTHROPIC_CLIENT_ID not configured."
        
        redirect_uri = getenv("APP_URI", "http://localhost:7437") + "/oauth/anthropic/callback"
        
        # Generate PKCE pair
        code_verifier, code_challenge = generate_pkce_pair()
        
        # Store verifier for later (keyed by state)
        if not state:
            state = secrets.token_urlsafe(32)
        self._pkce_verifiers[state] = code_verifier
        
        # Build authorization URL
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        auth_url = f"{AUTHORIZE}?{query_string}"
        
        return f"""**Anthropic OAuth Authorization**

Click the link below to connect your Claude account:

[Connect Claude Account]({auth_url})

After authorizing, you'll be redirected back to AGiXT with your account connected.

**Note:** This allows AGiXT to:
- Access Claude on your behalf
- Manage Claude Code sessions
- Sync your conversations (with permission)
"""
    
    async def check_connection(self) -> str:
        """
        Check if the user has connected their Anthropic account.
        
        Returns:
            str: Connection status
        """
        if not self.user_id:
            return "Error: User not authenticated with AGiXT."
        
        session = get_session()
        try:
            # Find Anthropic OAuth provider
            provider = (
                session.query(OAuthProvider)
                .filter(OAuthProvider.name == "anthropic")
                .first()
            )
            
            if not provider:
                return "Anthropic OAuth provider not registered. Connect your account first."
            
            # Check for user's OAuth connection
            user_oauth = (
                session.query(UserOAuth)
                .filter(UserOAuth.user_id == self.user_id)
                .filter(UserOAuth.provider_id == provider.id)
                .first()
            )
            
            if not user_oauth:
                return "No Anthropic account connected. Use 'Get Anthropic OAuth URL' to connect."
            
            # Check token expiry
            if user_oauth.token_expires_at and user_oauth.token_expires_at < datetime.utcnow():
                return f"""**Anthropic Account Connected** (Token Expired)

- Account: {user_oauth.account_name}
- Connected: {user_oauth.created_at.strftime('%Y-%m-%d')}
- Status: Token expired, refresh needed

Use 'Refresh Anthropic Token' to get a new token.
"""
            
            return f"""**Anthropic Account Connected** ✓

- Account: {user_oauth.account_name}
- Connected: {user_oauth.created_at.strftime('%Y-%m-%d')}
- Token Expires: {user_oauth.token_expires_at.strftime('%Y-%m-%d %H:%M') if user_oauth.token_expires_at else 'Unknown'}
- Status: Active
"""
        finally:
            session.close()
    
    async def get_user_info(self) -> str:
        """
        Get the connected Claude user's information.
        
        Returns:
            str: User information
        """
        access_token = await self._get_stored_token()
        if not access_token:
            return "No Anthropic account connected."
        
        try:
            sso_handler = AnthropicSSO(access_token=access_token)
            info = sso_handler.get_user_info()
            
            return f"""**Claude User Information**

- Email: {info.get('email', 'N/A')}
- Name: {info.get('first_name', '')} {info.get('last_name', '')}
- Anthropic ID: {info.get('anthropic_id', 'N/A')}
- Plan: {info.get('plan', 'N/A')}
"""
        except Exception as e:
            return f"Error getting user info: {str(e)}"
    
    async def disconnect(self) -> str:
        """
        Disconnect the Anthropic account from AGiXT.
        
        Returns:
            str: Confirmation message
        """
        if not self.user_id:
            return "Error: User not authenticated."
        
        session = get_session()
        try:
            provider = (
                session.query(OAuthProvider)
                .filter(OAuthProvider.name == "anthropic")
                .first()
            )
            
            if not provider:
                return "No Anthropic connection found."
            
            user_oauth = (
                session.query(UserOAuth)
                .filter(UserOAuth.user_id == self.user_id)
                .filter(UserOAuth.provider_id == provider.id)
                .first()
            )
            
            if not user_oauth:
                return "No Anthropic account connected."
            
            session.delete(user_oauth)
            session.commit()
            
            return "Anthropic account disconnected successfully."
        except Exception as e:
            session.rollback()
            return f"Error disconnecting: {str(e)}"
        finally:
            session.close()
    
    async def refresh_token(self) -> str:
        """
        Refresh the Anthropic OAuth token.
        
        Returns:
            str: Refresh status
        """
        if not self.user_id:
            return "Error: User not authenticated."
        
        session = get_session()
        try:
            provider = (
                session.query(OAuthProvider)
                .filter(OAuthProvider.name == "anthropic")
                .first()
            )
            
            if not provider:
                return "No Anthropic connection found."
            
            user_oauth = (
                session.query(UserOAuth)
                .filter(UserOAuth.user_id == self.user_id)
                .filter(UserOAuth.provider_id == provider.id)
                .first()
            )
            
            if not user_oauth or not user_oauth.refresh_token:
                return "No refresh token available. Please reconnect your account."
            
            # Refresh the token
            sso_handler = AnthropicSSO(
                access_token=user_oauth.access_token,
                refresh_token=user_oauth.refresh_token,
            )
            
            new_tokens = sso_handler.get_new_token()
            
            # Update stored tokens
            user_oauth.access_token = new_tokens.get("access_token", user_oauth.access_token)
            if "refresh_token" in new_tokens:
                user_oauth.refresh_token = new_tokens["refresh_token"]
            if "expires_in" in new_tokens:
                user_oauth.token_expires_at = datetime.utcnow() + timedelta(seconds=new_tokens["expires_in"])
            
            session.commit()
            
            return "Token refreshed successfully."
        except Exception as e:
            session.rollback()
            return f"Error refreshing token: {str(e)}"
        finally:
            session.close()
    
    async def get_access_token(self) -> str:
        """
        Get the current Claude access token for API use.
        
        This can be used by other extensions/tools that need to make
        authenticated requests to Claude on behalf of the user.
        
        Returns:
            str: Access token or error message
        """
        token = await self._get_stored_token()
        if not token:
            return "No Anthropic account connected. Use 'Get Anthropic OAuth URL' to connect."
        
        return f"Access token retrieved. Use this for Claude API calls:\n\n`{token[:20]}...{token[-10:]}`"
    
    async def _get_stored_token(self) -> Optional[str]:
        """Get the stored access token for the current user"""
        if not self.user_id:
            return None
        
        session = get_session()
        try:
            provider = (
                session.query(OAuthProvider)
                .filter(OAuthProvider.name == "anthropic")
                .first()
            )
            
            if not provider:
                return None
            
            user_oauth = (
                session.query(UserOAuth)
                .filter(UserOAuth.user_id == self.user_id)
                .filter(UserOAuth.provider_id == provider.id)
                .first()
            )
            
            if not user_oauth:
                return None
            
            # Check if token needs refresh
            if user_oauth.token_expires_at and user_oauth.token_expires_at < datetime.utcnow():
                if user_oauth.refresh_token:
                    try:
                        sso_handler = AnthropicSSO(
                            access_token=user_oauth.access_token,
                            refresh_token=user_oauth.refresh_token,
                        )
                        new_tokens = sso_handler.get_new_token()
                        user_oauth.access_token = new_tokens.get("access_token", user_oauth.access_token)
                        if "refresh_token" in new_tokens:
                            user_oauth.refresh_token = new_tokens["refresh_token"]
                        if "expires_in" in new_tokens:
                            user_oauth.token_expires_at = datetime.utcnow() + timedelta(seconds=new_tokens["expires_in"])
                        session.commit()
                    except:
                        pass
            
            return user_oauth.access_token
        finally:
            session.close()
