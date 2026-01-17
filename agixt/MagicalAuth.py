from decimal import Decimal
from DB import (
    User,
    FailedLogins,
    UserOAuth,
    OAuthProvider,
    UserPreferences,
    get_session,
    Company,
    UserCompany,
    Invitation,
    default_roles,
    default_scopes,
    TokenBlacklist,
    PaymentTransaction,
    CompanyTokenUsage,
    ExtensionCategory,
    Scope,
    CustomRole,
    CustomRoleScope,
    UserCustomRole,
    DefaultRoleScope,
    PersonalAccessToken,
    PersonalAccessTokenAgentAccess,
    PersonalAccessTokenCompanyAccess,
    CompanyExtensionCommand,
    CompanyExtensionSetting,
    TrialDomain,
)
from payments.pricing import PriceService
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from sqlalchemy import text
from sendgrid.helpers.mail import Mail
from sendgrid import SendGridAPIClient
from Models import (
    UserInfo,
    Register,
    Login,
    CompanyResponse,
    InvitationResponse,
    InvitationCreate,
    UserResponse,
)
from typing import List, Optional
from fastapi import Header, HTTPException
from Globals import getenv, get_default_agent
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime, timedelta
from fastapi import HTTPException
from InternalClient import InternalClient
from middleware import log_silenced_exception
import importlib
import pyotp
import logging
import traceback
import requests
import pytz
import jwt
import json
import uuid
import os
import urllib.parse
from ExtensionsHub import (
    find_extension_files,
    import_extension_module,
    get_extension_class_name,
)
from SharedCache import shared_cache


logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)

# Cache TTLs for SharedCache
# SharedCache handles cross-worker synchronization via Redis
_stripe_check_cache_ttl = 300  # 5 minutes
_user_company_cache_ttl = 10  # 10 seconds
_user_id_cache_ttl = 60  # 60 seconds
_token_validation_cache_ttl = 5  # 5 seconds


def hash_pat_token(token: str) -> str:
    """
    Securely hash a Personal Access Token using PBKDF2-HMAC-SHA256.

    Uses AGIXT_API_KEY as the salt, making the hash computationally expensive
    and resistant to brute-force attacks even if the database is compromised.

    Args:
        token: The PAT token string to hash

    Returns:
        str: The PBKDF2 hex digest of the token
    """
    import hashlib

    salt = os.getenv("AGIXT_API_KEY", "").encode()
    # PBKDF2 with 100,000 iterations provides strong brute-force resistance
    # while maintaining reasonable validation performance
    dk = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=token.encode(),
        salt=salt,
        iterations=100000,
    )
    return dk.hex()


def _serialize_user_dict(user_dict: dict) -> dict:
    """Convert user dict to JSON-serializable format (handles datetime fields)."""
    from datetime import datetime

    result = {}
    for key, value in user_dict.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def _deserialize_user_dict(cached_dict: dict) -> dict:
    """Convert cached user dict back from JSON format (handles datetime fields)."""
    from datetime import datetime

    result = {}
    datetime_fields = {"created_at", "updated_at", "tos_accepted_at"}
    for key, value in cached_dict.items():
        if key in datetime_fields and value is not None and isinstance(value, str):
            try:
                result[key] = datetime.fromisoformat(value)
            except ValueError:
                result[key] = value
        else:
            result[key] = value
    return result


def get_token_validation_cached(token: str):
    """Get cached token validation result if still valid (uses SharedCache)."""
    import hashlib

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cached = shared_cache.get(f"token_validation:{token_hash}")
    if cached:
        return _deserialize_user_dict(cached)
    return None


def set_token_validation_cache(token: str, user_dict: dict):
    """Cache token validation result (uses SharedCache)."""
    import hashlib

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    serialized = _serialize_user_dict(user_dict)
    shared_cache.set(
        f"token_validation:{token_hash}", serialized, ttl=_token_validation_cache_ttl
    )


def invalidate_token_validation_cache(token: str = None):
    """Invalidate token validation cache. If token is None, clear all (uses SharedCache)."""
    import hashlib

    if token is None:
        shared_cache.delete_pattern("token_validation:*")
    else:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        shared_cache.delete(f"token_validation:{token_hash}")


def get_user_id_cached(email: str):
    """Get cached user ID from email if still valid (uses SharedCache)."""
    return shared_cache.get(f"user_id:{email}")


def set_user_id_cache(email: str, user_id: str):
    """Cache user ID from email lookup (uses SharedCache)."""
    shared_cache.set(f"user_id:{email}", user_id, ttl=_user_id_cache_ttl)


def get_user_company_cached(user_id: str):
    """Get cached user company ID if still valid (uses SharedCache)."""
    return shared_cache.get(f"user_company:{user_id}")


def set_user_company_cache(user_id: str, company_id: str):
    """Cache user company ID (uses SharedCache)."""
    shared_cache.set(f"user_company:{user_id}", company_id, ttl=_user_company_cache_ttl)


def invalidate_user_company_cache(user_id: str = None):
    """Invalidate user company cache. If user_id is None, clear all (uses SharedCache)."""
    if user_id is None:
        shared_cache.delete_pattern("user_company:*")
    else:
        shared_cache.delete(f"user_company:{user_id}")


# User scopes cache TTL - 60 seconds (short enough to catch role changes quickly)
_user_scopes_cache_ttl = 60


def get_user_scopes_cached(user_id: str, company_id: str):
    """Get cached user scopes if still valid (uses SharedCache)."""
    cache_key = f"user_scopes:{user_id}:{company_id}"
    cached = shared_cache.get(cache_key)
    if cached is not None:
        # Convert list back to set
        return set(cached) if isinstance(cached, list) else None
    return None


def set_user_scopes_cache(user_id: str, company_id: str, scopes: set):
    """Cache user scopes (uses SharedCache). Converts set to list for JSON serialization."""
    cache_key = f"user_scopes:{user_id}:{company_id}"
    # Convert set to list for JSON serialization
    shared_cache.set(cache_key, list(scopes), ttl=_user_scopes_cache_ttl)


def invalidate_user_scopes_cache(user_id: str = None, company_id: str = None):
    """
    Invalidate user scopes cache.
    - If both are None: clear all user scopes caches
    - If only user_id: clear all scopes for that user across all companies
    - If only company_id: clear all users' scopes in that company
    - If both: clear specific user/company combo
    """
    if user_id is None and company_id is None:
        shared_cache.delete_pattern("user_scopes:*")
    elif user_id is not None and company_id is None:
        shared_cache.delete_pattern(f"user_scopes:{user_id}:*")
    elif user_id is None and company_id is not None:
        shared_cache.delete_pattern(f"user_scopes:*:{company_id}")
    else:
        shared_cache.delete(f"user_scopes:{user_id}:{company_id}")


def promote_superadmin_if_needed(session, user_id: str, email: str, company_id: str):
    """
    Check if the user's email matches SUPERADMIN_EMAIL and promote them to super admin (role 0).

    This is called after a user is associated with a company to ensure the configured
    superadmin email always has role 0 access.

    Args:
        session: Database session
        user_id: The user's ID
        email: The user's email address
        company_id: The company ID to check/update the role for
    """
    superadmin_email = getenv("SUPERADMIN_EMAIL").lower()
    if not superadmin_email or email.lower() != superadmin_email:
        return

    # Check if user already has role 0 in this company
    user_company = (
        session.query(UserCompany)
        .filter(
            UserCompany.user_id == user_id,
            UserCompany.company_id == company_id,
        )
        .first()
    )

    if user_company and user_company.role_id != 0:
        logging.info(
            f"Promoting user {email} to super admin (role 0) in company {company_id} "
            f"(was role {user_company.role_id}) due to SUPERADMIN_EMAIL configuration"
        )
        user_company.role_id = 0
        session.commit()
        # Invalidate caches since role changed
        invalidate_user_scopes_cache(user_id=user_id, company_id=str(company_id))


"""
Required environment variables:

- AGIXT_API_KEY: Encryption key to encrypt and decrypt data
- APP_URI: URL to send in the email for the user to click on
- AGIXT_URI: URL to the AGiXT server
- APP_NAME: Name of the app
- AGENT_NAME: Name of the agent
- TZ: Timezone
- LOG_LEVEL: Log level
- LOG_FORMAT: Log format
- DEFAULT_USER: Default user email
- STRIPE_API_KEY: Stripe API key
- REGISTRATION_DISABLED: Registration disabled flag
- APP_URI: App URI
- SUPERADMIN_EMAIL: Email address to automatically promote to super admin (role 0)
"""


def send_email(email: str, subject: str, body: str, return_details: bool = False):
    """
    Send an email using the configured email provider.

    Provider selection:
    - If EMAIL_PROVIDER is set to a specific provider, use that provider
    - If EMAIL_PROVIDER is 'auto' (default), try providers in order: sendgrid, mailgun, microsoft, google

    Args:
        email: Recipient email address
        subject: Email subject
        body: HTML email body
        return_details: If True, return dict with success, provider, and error info

    Returns:
        bool: True if email was sent successfully, False otherwise (when return_details=False)
        dict: {"success": bool, "provider": str, "error": str} (when return_details=True)
    """
    provider = getenv("EMAIL_PROVIDER").lower() if getenv("EMAIL_PROVIDER") else "auto"
    result = {"success": False, "provider": None, "error": None}

    # Define provider check functions - each returns (success, error_message) or None if not configured
    def try_sendgrid():
        sendgrid_api_key = getenv("SENDGRID_API_KEY")
        sendgrid_from_email = getenv("SENDGRID_FROM_EMAIL")
        if not sendgrid_api_key or not sendgrid_from_email:
            missing = []
            if not sendgrid_api_key:
                missing.append("SENDGRID_API_KEY")
            if not sendgrid_from_email:
                missing.append("SENDGRID_FROM_EMAIL")
            if provider == "sendgrid":
                logging.warning(
                    f"[Email] SendGrid selected but missing: {', '.join(missing)}"
                )
            return None, f"Missing configuration: {', '.join(missing)}"
        try:
            message = Mail(
                from_email=sendgrid_from_email,
                to_emails=email,
                subject=subject,
                html_content=body,
            )
            response = SendGridAPIClient(sendgrid_api_key).send(message)
            if response.status_code == 202:
                logging.debug(f"[Email] Sent via SendGrid to {email}")
                return True, None
            error_msg = f"SendGrid returned status {response.status_code}"
            logging.warning(f"[Email] {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"SendGrid error: {str(e)}"
            logging.error(f"[Email] {error_msg}")
            return False, error_msg

    def try_mailgun():
        mailgun_api_key = getenv("MAILGUN_API_KEY")
        mailgun_domain = getenv("MAILGUN_DOMAIN")
        mailgun_from_email = getenv("MAILGUN_FROM_EMAIL")
        if not mailgun_api_key or not mailgun_domain or not mailgun_from_email:
            missing = []
            if not mailgun_api_key:
                missing.append("MAILGUN_API_KEY")
            if not mailgun_domain:
                missing.append("MAILGUN_DOMAIN")
            if not mailgun_from_email:
                missing.append("MAILGUN_FROM_EMAIL")
            if provider == "mailgun":
                logging.warning(
                    f"[Email] Mailgun selected but missing: {', '.join(missing)}"
                )
            return None, f"Missing configuration: {', '.join(missing)}"
        try:
            response = requests.post(
                f"https://api.mailgun.net/v3/{mailgun_domain}/messages",
                auth=("api", mailgun_api_key),
                data={
                    "from": mailgun_from_email,
                    "to": email,
                    "subject": subject,
                    "html": body,
                },
            )
            if response.status_code == 200:
                logging.debug(f"[Email] Sent via Mailgun to {email}")
                return True, None
            error_msg = (
                f"Mailgun returned status {response.status_code}: {response.text}"
            )
            logging.warning(f"[Email] {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Mailgun error: {str(e)}"
            logging.error(f"[Email] {error_msg}")
            return False, error_msg

    def try_microsoft():
        """Send email using Microsoft Graph API with app-only authentication."""
        ms_client_id = getenv("MICROSOFT_CLIENT_ID")
        ms_client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        ms_email = getenv("MICROSOFT_EMAIL_ADDRESS")
        if not ms_client_id or not ms_client_secret or not ms_email:
            missing = []
            if not ms_client_id:
                missing.append("MICROSOFT_CLIENT_ID (OAuth settings)")
            if not ms_client_secret:
                missing.append("MICROSOFT_CLIENT_SECRET (OAuth settings)")
            if not ms_email:
                missing.append("MICROSOFT_EMAIL_ADDRESS (Email settings)")
            if provider == "microsoft":
                logging.warning(
                    f"[Email] Microsoft selected but missing: {', '.join(missing)}"
                )
            return None, f"Missing configuration: {', '.join(missing)}"
        try:
            # Get OAuth token using client credentials flow
            tenant_id = getenv("MICROSOFT_TENANT_ID") or "common"
            token_url = (
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            )
            token_response = requests.post(
                token_url,
                data={
                    "client_id": ms_client_id,
                    "client_secret": ms_client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
            )
            if token_response.status_code != 200:
                error_msg = f"Microsoft token error: {token_response.text}"
                logging.error(f"[Email] {error_msg}")
                return False, error_msg

            access_token = token_response.json().get("access_token")

            # Send email via Graph API
            email_data = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": body},
                    "toRecipients": [{"emailAddress": {"address": email}}],
                },
                "saveToSentItems": "true",
            }

            # Use /users/{email}/sendMail for app-only auth
            send_url = f"https://graph.microsoft.com/v1.0/users/{ms_email}/sendMail"
            response = requests.post(
                send_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=email_data,
            )

            if response.status_code == 202:
                logging.debug(f"[Email] Sent via Microsoft to {email}")
                return True, None
            error_msg = (
                f"Microsoft returned status {response.status_code}: {response.text}"
            )
            logging.warning(f"[Email] {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Microsoft error: {str(e)}"
            logging.error(f"[Email] {error_msg}")
            return False, error_msg

    def try_google():
        """Send email using Gmail API with service account or app credentials."""
        google_client_id = getenv("GOOGLE_CLIENT_ID")
        google_client_secret = getenv("GOOGLE_CLIENT_SECRET")
        google_email = getenv("GOOGLE_EMAIL_ADDRESS")
        if not google_client_id or not google_client_secret or not google_email:
            missing = []
            if not google_client_id:
                missing.append("GOOGLE_CLIENT_ID (OAuth settings)")
            if not google_client_secret:
                missing.append("GOOGLE_CLIENT_SECRET (OAuth settings)")
            if not google_email:
                missing.append("GOOGLE_EMAIL_ADDRESS (Email settings)")
            if provider == "google":
                logging.warning(
                    f"[Email] Google selected but missing: {', '.join(missing)}"
                )
            return None, f"Missing configuration: {', '.join(missing)}"

        # Note: Google Gmail API requires user-delegated OAuth tokens with gmail.send scope
        # This is more complex than Microsoft's client credentials flow
        error_msg = "Google Gmail API requires user-delegated OAuth tokens. Consider using SendGrid, Mailgun, or Microsoft for system emails."
        logging.warning(f"[Email] {error_msg}")
        return False, error_msg

    # Provider map
    providers = {
        "sendgrid": try_sendgrid,
        "mailgun": try_mailgun,
        "microsoft": try_microsoft,
        "google": try_google,
    }

    def make_result(success, provider_name, error):
        if return_details:
            return {"success": success, "provider": provider_name, "error": error}
        return success

    try:
        if provider != "auto" and provider in providers:
            # Use specific provider
            success, error = providers[provider]()
            if success is None:
                logging.error(f"[Email] Provider '{provider}' is not configured")
                return make_result(False, provider, error)
            return make_result(success, provider, error)

        # Auto mode: try providers in order
        last_error = None
        for name, try_provider in providers.items():
            success, error = try_provider()
            if success is True:
                return make_result(True, name, None)
            elif success is False:
                # Provider was configured but failed
                last_error = error
                continue
            # success is None means provider not configured, try next

        # No providers configured or all failed
        if last_error:
            return make_result(False, None, last_error)

        no_config_error = (
            "No email provider configured. Configure one of: "
            "SendGrid (SENDGRID_API_KEY + SENDGRID_FROM_EMAIL), "
            "Mailgun (MAILGUN_API_KEY + MAILGUN_DOMAIN + MAILGUN_FROM_EMAIL), "
            "Microsoft (MICROSOFT_CLIENT_ID + MICROSOFT_CLIENT_SECRET + MICROSOFT_EMAIL_ADDRESS)"
        )
        logging.warning(f"[Email] {no_config_error}")
        return make_result(False, None, no_config_error)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logging.error(f"[Email] {error_msg}")
        return make_result(False, None, error_msg)


def is_email_configured():
    """
    Check if any email provider is properly configured.

    Returns:
        bool: True if at least one email provider is configured, False otherwise
    """
    # Check SendGrid
    if getenv("SENDGRID_API_KEY") and getenv("SENDGRID_FROM_EMAIL"):
        return True
    # Check Mailgun
    if (
        getenv("MAILGUN_API_KEY")
        and getenv("MAILGUN_DOMAIN")
        and getenv("MAILGUN_FROM_EMAIL")
    ):
        return True
    # Check Microsoft
    if (
        getenv("MICROSOFT_CLIENT_ID")
        and getenv("MICROSOFT_CLIENT_SECRET")
        and getenv("MICROSOFT_EMAIL_ADDRESS")
    ):
        return True
    # Check Google
    if (
        getenv("GOOGLE_CLIENT_ID")
        and getenv("GOOGLE_CLIENT_SECRET")
        and getenv("GOOGLE_EMAIL_ADDRESS")
    ):
        return True
    return False


def is_admin(email: str = "USER", api_key: str = None):
    """
    Check if a user has admin-level access (role_id <= 2: super_admin, tenant_admin, or company_admin).

    Args:
        email: The user's email address
        api_key: The API key/JWT token from the request

    Returns:
        bool: True if user has admin access, False otherwise
    """
    import os

    AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", "")
    if api_key is None:
        api_key = ""
    api_key = str(api_key).replace("Bearer ", "").replace("bearer ", "")

    # Check if using the master API key
    if AGIXT_API_KEY and api_key == AGIXT_API_KEY:
        return True

    # Check if user has admin flag set (legacy super admin)
    if is_agixt_admin(email=email, api_key=api_key):
        return True

    # Check if user has admin role (role_id <= 2) via JWT token
    try:
        auth = MagicalAuth(token=api_key)
        if auth.user_id:
            role_id = auth.get_user_role()
            if role_id is not None and role_id <= 2:
                return True
    except Exception:
        pass

    return False


def get_sso_provider(provider: str, code, redirect_uri=None, code_verifier=None):
    # Use recursive discovery to find all extension files
    extension_files = find_extension_files()
    for extension_file in extension_files:
        # Import the module using the helper function
        module = import_extension_module(extension_file)
        if module is None:
            continue

        # Get the expected class name from the module
        class_name = get_extension_class_name(os.path.basename(extension_file))

        # Check if this matches the provider we're looking for
        if os.path.basename(extension_file).replace(".py", "") == provider:
            if getattr(module, "PKCE_REQUIRED", False):
                if not code_verifier:
                    raise HTTPException(
                        status_code=400,
                        detail=f"PKCE required for {provider} but no code_verifier provided",
                    )
                return module.sso(
                    code=code, redirect_uri=redirect_uri, code_verifier=code_verifier
                )
            else:
                return module.sso(code=code, redirect_uri=redirect_uri)
    return None


def get_oauth_providers():
    providers = []
    # Use recursive discovery to find all extension files
    extension_files = find_extension_files()
    for extension_file in extension_files:
        # Import the module using the helper function
        module = import_extension_module(extension_file)
        if module is None:
            continue

        filename = os.path.basename(extension_file)
        module_name = filename.replace(".py", "")

        try:
            client_id = getenv(f"{module_name.upper()}_CLIENT_ID")
            if client_id:
                providers.append(
                    {
                        "name": module_name,
                        "scopes": " ".join(module.SCOPES),
                        "authorize": module.AUTHORIZE,
                        "client_id": client_id,
                        "pkce_required": module.PKCE_REQUIRED,
                    }
                )
        except Exception as e:
            log_silenced_exception(
                e, f"get_sso_providers: loading provider {extension_file}"
            )
    return providers


def get_sso_instance(provider: str):
    # Use recursive discovery to find all extension files
    extension_files = find_extension_files()
    for extension_file in extension_files:
        # Import the module using the helper function
        module = import_extension_module(extension_file)
        if module is None:
            continue

        filename = os.path.basename(extension_file)
        module_name = filename.replace(".py", "")

        if module_name == provider:
            provider_class = getattr(module, f"{provider.capitalize()}SSO")
            return provider_class

    # Prevent infinite recursion - if we're already looking for microsoft and can't find it,
    # return None instead of recursing
    if provider == "microsoft":
        return None

    return get_sso_instance(provider="microsoft")


def is_agixt_admin(email: str = "", api_key: str = ""):
    if api_key == os.getenv("AGIXT_API_KEY", ""):
        return True
    api_key = str(api_key).replace("Bearer ", "").replace("bearer ", "")
    session = get_session()
    try:
        user = session.query(User).filter_by(email=email).first()
    except:
        session.close()
        return False
    if not user:
        session.close()
        return False
    if user.admin is True:
        session.close()
        return True
    session.close()
    return False


def get_sso_credentials(user_id):
    session = get_session()
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        session.close()
        raise HTTPException(status_code=404, detail="User not found.")
    user_oauth = session.query(UserOAuth).filter(UserOAuth.user_id == user_id).all()
    if not user_oauth:
        session.close()
        return {}
    credentials = {}
    for oauth in user_oauth:
        provider = (
            session.query(OAuthProvider)
            .filter(OAuthProvider.id == oauth.provider_id)
            .first()
        )
        credentials.update(
            {f"{str(provider.name).upper()}_ACCESS_TOKEN": oauth.access_token}
        )
    session.close()
    return credentials


def get_admin_user():
    session = get_session()
    user = session.query(User).filter(User.admin == True).first()
    return user


def verify_api_key(authorization: str = Header(None)):
    AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", "")
    authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    if AGIXT_API_KEY:
        if authorization == AGIXT_API_KEY:
            return get_admin_user()
        try:
            if authorization == AGIXT_API_KEY:
                return get_admin_user()

            # Check if this is a Personal Access Token (starts with "agixt_")
            if authorization.startswith("agixt_"):
                pat_validation = validate_personal_access_token(authorization)
                if not pat_validation["valid"]:
                    raise HTTPException(
                        status_code=401,
                        detail=pat_validation.get(
                            "error", "Invalid personal access token"
                        ),
                    )
                # Return user info from PAT validation
                db = get_session()
                user = (
                    db.query(User).filter(User.id == pat_validation["user_id"]).first()
                )
                if not user:
                    db.close()
                    raise HTTPException(
                        status_code=401, detail="User not found for token"
                    )
                user_dict = user.__dict__.copy()
                user_dict.pop("_sa_instance_state", None)
                # Add PAT-specific info to the user dict for downstream use
                user_dict["_pat_scopes"] = pat_validation.get("scopes", [])
                user_dict["_pat_agent_ids"] = pat_validation.get("agent_ids", [])
                user_dict["_pat_company_ids"] = pat_validation.get("company_ids", [])
                db.close()
                return user_dict

            # Check cache first for JWT tokens (short TTL for security)
            cached_user = get_token_validation_cached(authorization)
            if cached_user is not None:
                return cached_user

            # Check if token is blacklisted before validating
            db = get_session()
            blacklisted_token = (
                db.query(TokenBlacklist)
                .filter(TokenBlacklist.token == authorization)
                .first()
            )
            if blacklisted_token:
                db.close()
                raise HTTPException(
                    status_code=401,
                    detail="Token has been revoked. Please log in again.",
                )

            token = jwt.decode(
                jwt=authorization,
                key=AGIXT_API_KEY,
                algorithms=["HS256"],
                leeway=timedelta(hours=5),
            )
            user = db.query(User).filter(User.id == token["sub"]).first()
            # return user dict
            user_dict = user.__dict__
            user_dict.pop("_sa_instance_state")
            db.close()
            # Cache the validation result for a short time
            set_token_validation_cache(authorization, user_dict.copy())
            return user_dict
        except Exception as e:
            logging.info(f"Error verifying API Key: {str(e)}")
            raise HTTPException(status_code=401, detail="Invalid API Key")
    else:
        logging.error(
            "AGiXT API Key is missing. Please set the AGIXT_API_KEY environment variable."
        )
        raise HTTPException(status_code=401, detail="API Key is missing.")


def require_scope(*required_scopes):
    """
    FastAPI dependency factory to require specific scopes.
    Use as: dependencies=[Depends(require_scope("agents:read"))]

    Args:
        *required_scopes: One or more scope names that are required.
                          If multiple are provided, user needs at least one.

    Returns:
        A dependency function that validates scope access.
    """

    def scope_checker(authorization: str = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
        auth = MagicalAuth(token=token)

        if len(required_scopes) == 1:
            if not auth.has_scope(required_scopes[0]):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required scope: {required_scopes[0]}",
                )
        else:
            if not auth.has_any_scope(list(required_scopes)):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required one of: {', '.join(required_scopes)}",
                )

        return auth

    return scope_checker


def require_all_scopes(*required_scopes):
    """
    FastAPI dependency factory to require ALL specified scopes.
    Use as: dependencies=[Depends(require_all_scopes("agents:read", "agents:write"))]

    Args:
        *required_scopes: Scope names that are ALL required.

    Returns:
        A dependency function that validates scope access.
    """

    def scope_checker(authorization: str = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
        auth = MagicalAuth(token=token)

        if not auth.has_all_scopes(list(required_scopes)):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required all of: {', '.join(required_scopes)}",
            )

        return auth

    return scope_checker


def get_user_id(user):
    """Get user ID from user (can be email string or user dict from verify_api_key)."""
    # Handle dict from verify_api_key
    if isinstance(user, dict):
        if "id" in user:
            return user["id"]
        elif "email" in user:
            user = user["email"]
        else:
            raise HTTPException(status_code=404, detail="User not found in dict.")

    # Check cache first for email lookups
    cached = get_user_id_cached(user)
    if cached is not None:
        return cached

    # Handle string (email)
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    if user_data is None:
        session.close()
        raise HTTPException(status_code=404, detail=f"User {user} not found.")
    try:
        user_id = user_data.id
        # Cache the result
        set_user_id_cache(user, user_id)
    except Exception as e:
        session.close()
        raise HTTPException(status_code=404, detail=f"User {user} not found.")
    session.close()
    return user_id


def get_user_company_id(user):
    """Get the company_id for a user (can be email string or user dict from verify_api_key)."""
    # Handle dict from verify_api_key
    if isinstance(user, dict):
        user_id = user.get("id")
        if user_id:
            # Check cache first
            cached = get_user_company_cached(str(user_id))
            if cached is not None:
                return cached if cached != "__NONE__" else None
            # Look up company from UserCompany table
            session = get_session()
            try:
                user_company = (
                    session.query(UserCompany)
                    .filter(UserCompany.user_id == user_id)
                    .first()
                )
                if user_company and user_company.company_id is not None:
                    company_id_str = str(user_company.company_id)
                    if company_id_str.lower() in ["none", "null", ""]:
                        set_user_company_cache(str(user_id), "__NONE__")
                        return None
                    set_user_company_cache(str(user_id), company_id_str)
                    return company_id_str
                set_user_company_cache(str(user_id), "__NONE__")
                return None
            finally:
                session.close()
        elif "email" in user:
            user = user["email"]
        else:
            return None

    # Handle string (email) - look up user first, then company
    session = get_session()
    try:
        user_data = session.query(User).filter(User.email == user).first()
        if user_data is None:
            return None
        # Check cache for this user_id
        cached = get_user_company_cached(str(user_data.id))
        if cached is not None:
            return cached if cached != "__NONE__" else None
        user_company = (
            session.query(UserCompany)
            .filter(UserCompany.user_id == user_data.id)
            .first()
        )
        if user_company and user_company.company_id is not None:
            company_id_str = str(user_company.company_id)
            if company_id_str.lower() in ["none", "null", ""]:
                set_user_company_cache(str(user_data.id), "__NONE__")
                return None
            set_user_company_cache(str(user_data.id), company_id_str)
            return company_id_str
        set_user_company_cache(str(user_data.id), "__NONE__")
        return None
    finally:
        session.close()


def get_user_company_id_by_email(email: str):
    """Get company_id for a user by their email address"""
    try:
        user_id = get_user_id(email)
        auth = MagicalAuth()
        auth.email = email
        return auth.get_user_company_id()
    except:
        return None


def get_user_by_email(email: str):
    session = get_session()
    try:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            session.close()
            raise HTTPException(status_code=404, detail="User not found.")
        user_dict = user.__dict__
        user_dict.pop("_sa_instance_state")
        session.close()
        return user_dict
    finally:
        session.close()


def impersonate_user(email: str):
    # Get token for the user
    AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", "")
    token = jwt.encode(
        {
            "sub": str(get_user_id(email)),
            "email": email,
        },
        AGIXT_API_KEY,
        algorithm="HS256",
    )
    return token


def encrypt(key: str, data: str):
    return jwt.encode({"data": data}, key, algorithm="HS256")


def decrypt(key: str, data: str):
    return jwt.decode(
        data,
        key,
        algorithms=["HS256"],
        leeway=timedelta(hours=5),
    )["data"]


from DB import Agent as AgentModel, AgentSetting as AgentSettingModel


def get_agents(email, company=None):
    from DB import Extension, Command, AgentCommand

    session = get_session()
    agents = session.query(AgentModel).filter(AgentModel.user.has(email=email)).all()
    output = []
    for agent in agents:
        # Check if the agent is in the output already
        if agent.name in [a["name"] for a in output]:
            continue
        # Get the agent settings `company_id` if defined
        company_id = None
        agent_settings = (
            session.query(AgentSettingModel)
            .filter(AgentSettingModel.agent_id == agent.id)
            .all()
        )

        # Check for agentonboarded11182025 setting
        onboarded = False
        for setting in agent_settings:
            if setting.name == "company_id":
                company_id = setting.value
            elif setting.name == "agentonboarded11182025":
                onboarded = True

        if company_id and company:
            # Ensure both are strings for comparison (PostgreSQL UUID compatibility)
            if str(company_id) != str(company):
                continue
        if not company_id:
            auth = MagicalAuth(token=impersonate_user(email))
            company_id = auth.company_id
            # add to agent settings
            agent_setting = AgentSettingModel(
                agent_id=agent.id, name="company_id", value=company_id
            )
            session.add(agent_setting)
            session.commit()

        # Retroactive onboarding: Enable essential abilities if not already onboarded
        if not onboarded:
            try:
                # Get all extensions in the Core Abilities category
                core_abilities_category = (
                    session.query(ExtensionCategory)
                    .filter(ExtensionCategory.name == "Core Abilities")
                    .first()
                )

                extensions_to_enable = []
                if core_abilities_category:
                    extensions_to_enable = (
                        session.query(Extension)
                        .filter(Extension.category_id == core_abilities_category.id)
                        .all()
                    )

                # Enable all commands from these extensions for this agent
                enabled_count = 0
                for extension in extensions_to_enable:
                    commands = (
                        session.query(Command)
                        .filter(Command.extension_id == extension.id)
                        .all()
                    )
                    for command in commands:
                        # Check if command is already enabled for this agent
                        existing = (
                            session.query(AgentCommand)
                            .filter(
                                AgentCommand.agent_id == agent.id,
                                AgentCommand.command_id == command.id,
                            )
                            .first()
                        )

                        if not existing:
                            agent_command = AgentCommand(
                                agent_id=agent.id, command_id=command.id, state=True
                            )
                            session.add(agent_command)
                            enabled_count += 1
                        else:
                            # Enable it if it was disabled
                            existing.state = True
                            enabled_count += 1

                # Mark as onboarded
                onboarded_setting = AgentSettingModel(
                    agent_id=agent.id, name="agentonboarded11182025", value="true"
                )
                session.add(onboarded_setting)
                session.commit()

            except Exception as e:
                session.rollback()
                logging.error(
                    f"Error during retroactive onboarding for agent {agent.name}: {str(e)}"
                )

        output.append(
            {
                "name": agent.name,
                "id": agent.id,
                "status": False,
                "company_id": company_id,
            }
        )
    session.close()
    return output


class MagicalAuth:
    def __init__(self, token: str = None):
        encryption_key = os.getenv("AGIXT_API_KEY", "")
        self.link = getenv("APP_URI")
        self.encryption_key = encryption_key
        token = (
            str(token)
            .replace("%2B", "+")
            .replace("%2F", "/")
            .replace("%3D", "=")
            .replace("%20", " ")
            .replace("%3A", ":")
            .replace("%3F", "?")
            .replace("%26", "&")
            .replace("%23", "#")
            .replace("%3B", ";")
            .replace("%40", "@")
            .replace("%21", "!")
            .replace("%24", "$")
            .replace("%27", "'")
            .replace("%28", "(")
            .replace("%29", ")")
            .replace("%2A", "*")
            .replace("%2C", ",")
            .replace("%3B", ";")
            .replace("%5B", "[")
            .replace("%5D", "]")
            .replace("%7B", "{")
            .replace("%7D", "}")
            .replace("%7C", "|")
            .replace("%5C", "\\")
            .replace("%5E", "^")
            .replace("%60", "`")
            .replace("%7E", "~")
            .replace("Bearer ", "")
            .replace("bearer ", "")
            if token
            else None
        )
        try:
            # Decode jwt
            decoded = jwt.decode(
                jwt=token,
                key=self.encryption_key,
                algorithms=["HS256"],
                leeway=timedelta(hours=5),
            )
            self.email = decoded["email"]
            self.user_id = decoded["sub"]
            self.token = token
            self.company_id = self.get_user_company_id()
        except:
            self.email = None
            self.token = None
            self.user_id = None
            self.company_id = None
        if token == encryption_key:
            self.email = getenv("DEFAULT_USER")
            self.user_id = get_user_id(self.email)
            self.token = token
            self.company_id = self.get_user_company_id()

    def validate_user(self):
        if self.user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token. Please log in.")
        return True

    def is_super_admin(self) -> bool:
        """
        Check if the current user has role 0 (super_admin) in any company.
        Super admins have server-wide access to all companies.

        Returns:
            bool: True if user is a super admin, False otherwise
        """
        if self.user_id is None:
            return False
        with get_session() as db:
            user_company = (
                db.query(UserCompany)
                .filter(
                    UserCompany.user_id == self.user_id,
                    UserCompany.role_id == 0,
                )
                .first()
            )
            return user_company is not None

    def get_user_data_optimized(self, ip_address: str = None) -> dict:
        """
        Optimized single-query method to fetch all user data for /v1/user endpoint.

        This combines login validation, preferences, companies, agents, and scopes
        into a single database session, dramatically reducing round-trips.

        Returns dict with:
        - user: User object
        - preferences: dict of user preferences
        - companies: list of company dicts with agents and scopes included
        - is_super_admin: bool

        Raises HTTPException on auth failures.
        """
        import threading
        from Agent import get_agents_lightweight
        from DB import default_role_scopes as db_default_role_scopes

        if self.user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token. Please log in.")

        session = get_session()
        try:
            # === 1. Validate token (check blacklist) ===
            blacklisted = (
                session.query(TokenBlacklist)
                .filter(TokenBlacklist.token == self.token)
                .first()
            )
            if blacklisted:
                raise HTTPException(
                    status_code=401,
                    detail="Token has been revoked. Please log in again.",
                )

            # === 2. Get user with single query ===
            user = session.query(User).filter(User.id == self.user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # === 3. Get user preferences ===
            user_prefs_list = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == self.user_id)
                .all()
            )
            user_preferences = {x.pref_key: x.pref_value for x in user_prefs_list}

            # Set defaults
            if "input_tokens" not in user_preferences:
                user_preferences["input_tokens"] = 0
            if "output_tokens" not in user_preferences:
                user_preferences["output_tokens"] = 0
            if "phone_number" not in user_preferences:
                user_preferences["phone_number"] = ""

            # === 4. Get user companies with JOIN (single query) ===
            user_companies = (
                session.query(UserCompany)
                .options(joinedload(UserCompany.company))
                .filter(UserCompany.user_id == self.user_id)
                .all()
            )

            # === 4.5. Check if this user should be promoted to super admin ===
            # This ensures SUPERADMIN_EMAIL takes effect for existing users
            superadmin_email = getenv("SUPERADMIN_EMAIL", "").lower()
            if superadmin_email and user.email.lower() == superadmin_email:
                for uc in user_companies:
                    if uc.role_id != 0:
                        logging.info(
                            f"Promoting user {user.email} to super admin (role 0) in company {uc.company_id} "
                            f"(was role {uc.role_id}) due to SUPERADMIN_EMAIL configuration"
                        )
                        uc.role_id = 0
                        session.commit()
                        invalidate_user_scopes_cache(
                            user_id=str(self.user_id), company_id=str(uc.company_id)
                        )

            # Check if super admin
            is_super_admin = any(uc.role_id == 0 for uc in user_companies)

            # === 5. Billing check (fast, synchronous) ===
            # First, check the pricing model from extensions hub
            from ExtensionsHub import ExtensionsHub

            hub = ExtensionsHub()
            pricing_config = hub.get_pricing_config()
            pricing_model = (
                pricing_config.get("pricing_model") if pricing_config else "per_token"
            )
            is_seat_based = pricing_model in [
                "per_user",
                "per_capacity",
                "per_location",
            ]

            wallet_address = getenv("PAYMENT_WALLET_ADDRESS", "")
            price_service = PriceService()
            try:
                token_price = price_service.get_token_price()
            except Exception:
                token_price = 0 if is_seat_based else 1

            # Billing is enabled if:
            # - Token-based: TOKEN_PRICE_PER_MILLION_USD > 0
            # - Seat-based: pricing.json has paid tiers
            token_billing_enabled = token_price > 0 and not is_seat_based
            seat_billing_enabled = (
                is_seat_based
                and pricing_config
                and any(
                    tier.get("price_per_unit") is not None
                    or tier.get("custom_pricing", False)
                    for tier in pricing_config.get("tiers", [])
                )
            )
            billing_enabled = token_billing_enabled or seat_billing_enabled

            wallet_paywall_enabled = (
                bool(wallet_address)
                and str(wallet_address).lower() != "none"
                and token_billing_enabled  # Wallet paywall only for token-based billing
            )

            # For token-based billing with wallet paywall
            # Super admins (role 0) are exempt from paywall
            if wallet_paywall_enabled and not is_super_admin:
                has_balance = self._has_sufficient_token_balance(
                    session, user_companies
                )
                if not has_balance:
                    user.is_active = False
                    session.commit()
                    raise HTTPException(
                        status_code=402,
                        detail={
                            "message": "Insufficient token balance. Please top up your tokens.",
                            "customer_session": {
                                "client_secret": None,
                                "company_id": self.company_id,
                            },
                            "wallet_address": wallet_address,
                            "token_price_per_million_usd": float(token_price),
                        },
                    )
                user_preferences["wallet_address"] = wallet_address
                user_preferences["token_price_per_million_usd"] = float(token_price)

            # For seat-based billing, check if user has valid subscription or trial credits
            # Super admins (role 0) are exempt from paywall
            elif seat_billing_enabled and not is_super_admin:
                has_balance = self._has_sufficient_token_balance(
                    session, user_companies
                )
                if not has_balance:
                    user.is_active = False
                    session.commit()
                    unit_name = pricing_config.get("unit_name", "seat")
                    unit_plural = pricing_config.get("unit_name_plural", "seats")
                    raise HTTPException(
                        status_code=402,
                        detail={
                            "message": f"Subscription required. Please subscribe to continue using the service.",
                            "pricing_model": pricing_model,
                            "unit_name": unit_name,
                            "unit_name_plural": unit_plural,
                            "customer_session": {
                                "client_secret": None,
                                "company_id": self.company_id,
                            },
                        },
                    )

            # === 6. User requirements check ===
            user_requirements = self.registration_requirements()
            missing_requirements = []
            if user_requirements:
                for key, value in user_requirements.items():
                    if key not in user_preferences and key != "stripe_id":
                        missing_requirements.append({key: value})

            if (
                "verify_email" not in user_preferences
                and getenv("EMAIL_VERIFICATION_ENABLED").lower() == "true"
            ):
                missing_requirements.append({"verify_email": True})
                threading.Thread(
                    target=self._send_email_verification_async, daemon=True
                ).start()
            elif "verify_email" in user_preferences:
                del user_preferences["verify_email"]

            if missing_requirements:
                user_preferences["missing_requirements"] = missing_requirements

            # Clean up sensitive fields
            for key in ["email", "first_name", "last_name"]:
                if key in user_preferences:
                    del user_preferences[key]

            # === 7. Get agents for all companies (batch query) ===
            company_ids = [str(uc.company_id) for uc in user_companies]
            default_agent_id = user_preferences.get("agent_id")

            agents_by_company = {}
            if company_ids:
                agents_by_company = get_agents_lightweight(
                    user_id=str(self.user_id),
                    company_ids=company_ids,
                    default_agent_id=default_agent_id,
                    include_commands=True,
                )

            # === 8. Get scopes for all companies (batch) ===
            # Pre-fetch all scope data we need for all companies
            all_default_role_scopes = (
                session.query(DefaultRoleScope, Scope)
                .join(Scope, DefaultRoleScope.scope_id == Scope.id)
                .all()
            )
            role_to_scopes = {}
            for drs, scope in all_default_role_scopes:
                if drs.role_id not in role_to_scopes:
                    role_to_scopes[drs.role_id] = set()
                role_to_scopes[drs.role_id].add(scope.name)

            # All scopes for super admin
            all_scopes = None
            if is_super_admin:
                all_scopes_query = session.query(Scope).all()
                all_scopes = {s.name for s in all_scopes_query}

            # Pre-fetch custom role scopes for this user across all companies
            custom_scopes_query = (
                session.query(UserCustomRole.company_id, Scope.name)
                .join(CustomRole, CustomRole.id == UserCustomRole.custom_role_id)
                .join(CustomRoleScope, CustomRoleScope.custom_role_id == CustomRole.id)
                .join(Scope, Scope.id == CustomRoleScope.scope_id)
                .filter(
                    UserCustomRole.user_id == self.user_id,
                    CustomRole.is_active == True,
                )
                .all()
            )
            custom_scopes_by_company = {}
            for company_id, scope_name in custom_scopes_query:
                cid = str(company_id)
                if cid not in custom_scopes_by_company:
                    custom_scopes_by_company[cid] = set()
                custom_scopes_by_company[cid].add(scope_name)

            # Pre-fetch extension configurations for ext:* wildcard expansion
            ext_configs_query = (
                session.query(
                    CompanyExtensionCommand.company_id,
                    CompanyExtensionCommand.extension_name,
                )
                .filter(CompanyExtensionCommand.company_id.in_(company_ids))
                .distinct()
                .all()
            )
            ext_settings_query = (
                session.query(
                    CompanyExtensionSetting.company_id,
                    CompanyExtensionSetting.extension_name,
                )
                .filter(CompanyExtensionSetting.company_id.in_(company_ids))
                .distinct()
                .all()
            )
            ext_by_company = {cid: set() for cid in company_ids}
            for company_id, ext_name in ext_configs_query:
                ext_by_company[str(company_id)].add(ext_name)
            for company_id, ext_name in ext_settings_query:
                ext_by_company[str(company_id)].add(ext_name)

            # Pre-fetch ext scopes for wildcard expansion
            ext_scopes_all = session.query(Scope).filter(Scope.name.like("ext:%")).all()

            # === 9. Build companies response with scopes ===
            companies = []
            for uc in user_companies:
                company = uc.company
                if not company:
                    continue

                cid = str(company.id)
                role_id = uc.role_id

                # Calculate scopes for this company
                if is_super_admin or role_id == 0:
                    company_scopes = all_scopes
                else:
                    company_scopes = set(role_to_scopes.get(role_id, set()))

                    # Handle wildcards from default_role_scopes definition
                    if role_id in db_default_role_scopes:
                        has_ext_wildcard = "ext:*" in db_default_role_scopes[role_id]

                        for pattern in db_default_role_scopes[role_id]:
                            # Include ALL wildcard patterns (including ext:*) for frontend scope checking
                            if (
                                pattern.endswith(":*")
                                or ":*:" in pattern
                                or pattern == "*"
                            ):
                                company_scopes.add(pattern)

                        # Expand ext:* to configured extensions only (for backend authorization)
                        if has_ext_wildcard:
                            configured_exts = ext_by_company.get(cid, set())
                            if configured_exts:
                                for scope in ext_scopes_all:
                                    parts = scope.name.split(":")
                                    if len(parts) >= 2 and parts[1] in configured_exts:
                                        company_scopes.add(scope.name)

                    # Add custom role scopes
                    company_scopes.update(custom_scopes_by_company.get(cid, set()))

                company_dict = {
                    "id": cid,
                    "company_id": (
                        str(company.company_id) if company.company_id else None
                    ),
                    "name": company.name,
                    "agent_name": company.agent_name,
                    "status": company.status,
                    "address": company.address,
                    "phone_number": company.phone_number,
                    "email": company.email,
                    "website": company.website,
                    "city": company.city,
                    "state": company.state,
                    "zip_code": company.zip_code,
                    "country": company.country,
                    "notes": company.notes,
                    "user_limit": company.user_limit,
                    "token_balance": company.token_balance,
                    "token_balance_usd": company.token_balance_usd,
                    "tokens_used_total": company.tokens_used_total,
                    "role_id": role_id,
                    "primary": cid == str(self.company_id),
                    "agents": agents_by_company.get(cid, []),
                    "scopes": list(company_scopes) if company_scopes else [],
                }
                companies.append(company_dict)

            # === 10. Background Stripe check (non-blocking) ===
            billing_paused = getenv("BILLING_PAUSED", "false").lower() == "true"
            api_key = getenv("STRIPE_API_KEY")
            if (
                not billing_paused
                and api_key
                and api_key.lower() != "none"
                and user.email != getenv("DEFAULT_USER")
                and not user.email.endswith(".xt")
            ):
                user_email = user.email
                user_id = self.user_id
                stripe_id = user_preferences.get("stripe_id")
                company_ids_for_stripe = [uc.company_id for uc in user_companies]

                def _background_stripe_check():
                    try:
                        self._background_stripe_subscription_check(
                            api_key,
                            user_email,
                            user_id,
                            stripe_id,
                            company_ids_for_stripe,
                        )
                    except Exception as e:
                        logging.debug(f"Background Stripe check failed: {e}")

                threading.Thread(target=_background_stripe_check, daemon=True).start()

            return {
                "user": user,
                "preferences": user_preferences,
                "companies": companies,
                "is_super_admin": is_super_admin,
            }

        finally:
            session.close()

    def get_user_scopes(self, company_id: str = None) -> set:
        """
        Get all scopes available to the current user for a specific company.
        This combines scopes from their default role and any custom roles.
        Also includes wildcard patterns from default_role_scopes for proper
        frontend scope checking (e.g., ext:* for company admins).

        Results are cached for 60 seconds to improve performance since
        permission checks happen frequently.

        Args:
            company_id: The company to check scopes for. Defaults to user's current company.

        Returns:
            set: A set of scope names the user has access to.
        """
        from DB import default_role_scopes as db_default_role_scopes

        if self.user_id is None:
            return set()

        if not company_id:
            company_id = self.company_id

        # Check cache first
        cached_scopes = get_user_scopes_cached(self.user_id, company_id)
        if cached_scopes is not None:
            return cached_scopes

        scopes = set()

        with get_session() as db:
            # Get user's role in this company
            user_company = (
                db.query(UserCompany)
                .filter(
                    UserCompany.user_id == self.user_id,
                    UserCompany.company_id == company_id,
                )
                .first()
            )

            if not user_company:
                return scopes

            role_id = user_company.role_id

            # Super admin gets all scopes that exist in the database
            # This ensures they only see menu items for extensions that are actually installed
            # (Extensions register their scopes when they load)
            if role_id == 0:
                all_scopes = db.query(Scope).all()
                return {s.name for s in all_scopes}

            # Get scopes from default role (expanded individual scopes)
            default_role_scopes_db = (
                db.query(Scope)
                .join(DefaultRoleScope, DefaultRoleScope.scope_id == Scope.id)
                .filter(DefaultRoleScope.role_id == role_id)
                .all()
            )
            scopes.update(s.name for s in default_role_scopes_db)

            # Handle wildcard patterns from default_role_scopes definition
            # Include wildcard patterns directly so frontend can perform proper scope checking
            if role_id in db_default_role_scopes:
                has_ext_wildcard = "ext:*" in db_default_role_scopes[role_id]

                for pattern in db_default_role_scopes[role_id]:
                    # Include wildcard patterns (*, ext:*, etc.) so frontend can check them
                    if pattern.endswith(":*") or ":*:" in pattern or pattern == "*":
                        scopes.add(pattern)

                # If role has ext:* wildcard, also expand to specific extensions configured for this company
                # This provides both the wildcard for frontend matching AND specific scopes for backend checks
                if has_ext_wildcard:
                    # Get extension names that are configured for this company
                    # (via CompanyExtensionCommand or CompanyExtensionSetting)
                    configured_extensions = set()

                    # Get from CompanyExtensionCommand
                    ext_commands = (
                        db.query(CompanyExtensionCommand.extension_name)
                        .filter(CompanyExtensionCommand.company_id == company_id)
                        .distinct()
                        .all()
                    )
                    configured_extensions.update(ec[0] for ec in ext_commands)

                    # Get from CompanyExtensionSetting
                    ext_settings = (
                        db.query(CompanyExtensionSetting.extension_name)
                        .filter(CompanyExtensionSetting.company_id == company_id)
                        .distinct()
                        .all()
                    )
                    configured_extensions.update(es[0] for es in ext_settings)

                    # Add ext scopes only for configured extensions
                    if configured_extensions:
                        # Get all ext:* scopes from DB that match configured extensions
                        ext_scopes = (
                            db.query(Scope).filter(Scope.name.like("ext:%")).all()
                        )
                        for scope in ext_scopes:
                            # Parse the scope name to get extension name
                            # Format: ext:extension_name:... or ext:extension_name:feature:action
                            parts = scope.name.split(":")
                            if len(parts) >= 2:
                                ext_name = parts[1]
                                if ext_name in configured_extensions:
                                    scopes.add(scope.name)

            # Get scopes from custom roles assigned to this user in this company
            custom_role_scopes = (
                db.query(Scope)
                .join(CustomRoleScope, CustomRoleScope.scope_id == Scope.id)
                .join(CustomRole, CustomRole.id == CustomRoleScope.custom_role_id)
                .join(UserCustomRole, UserCustomRole.custom_role_id == CustomRole.id)
                .filter(
                    UserCustomRole.user_id == self.user_id,
                    UserCustomRole.company_id == company_id,
                    CustomRole.is_active == True,
                )
                .all()
            )
            scopes.update(s.name for s in custom_role_scopes)

        # Cache the computed scopes for future calls
        set_user_scopes_cache(self.user_id, company_id, scopes)
        return scopes

    def has_scope(self, scope: str, company_id: str = None) -> bool:
        """
        Check if the user has a specific scope in a company.

        Args:
            scope: The scope to check (e.g., 'agents:read', 'ext:github:issues:read')
            company_id: The company to check in. Defaults to user's current company.

        Returns:
            bool: True if the user has the scope, False otherwise.
        """
        if self.user_id is None:
            return False

        # Super admins have all scopes
        if self.is_super_admin():
            return True

        user_scopes = self.get_user_scopes(company_id)

        # Check global wildcard - user has all permissions
        if "*" in user_scopes:
            return True

        # Check exact match
        if scope in user_scopes:
            return True

        # Parse the scope to check
        parts = scope.split(":")

        # Handle extension-specific scopes
        if parts[0] == "ext" and len(parts) >= 3:
            ext_name = parts[1]

            # Check if user has ext:* (all extension scopes)
            if "ext:*" in user_scopes:
                return True

            # Handle 3-part extension scopes (ext:name:action)
            if len(parts) == 3:
                action = parts[2]

                # Check if user has ext:*:action (e.g., ext:*:read for all extensions read access)
                if f"ext:*:{action}" in user_scopes:
                    return True

                # Check if user has ext:name:* (all actions for specific extension)
                if f"ext:{ext_name}:*" in user_scopes:
                    return True

            # Handle 4-part deep extension scopes (ext:name:feature:action)
            elif len(parts) == 4:
                feature = parts[2]
                action = parts[3]

                # Check if user has ext:*:feature:action (all extensions, same feature)
                if f"ext:*:{feature}:{action}" in user_scopes:
                    return True

                # Check if user has ext:*:*:action (all extensions, all features, same action)
                if f"ext:*:*:{action}" in user_scopes:
                    return True

                # Check if user has ext:name:* (all actions for specific extension)
                if f"ext:{ext_name}:*" in user_scopes:
                    return True

                # Check if user has ext:name:feature:* (all actions for specific feature)
                if f"ext:{ext_name}:{feature}:*" in user_scopes:
                    return True

                # Check if user has ext:name:*:action (specific extension, all features, specific action)
                if f"ext:{ext_name}:*:{action}" in user_scopes:
                    return True

                # Check if user has the simpler ext:name:execute scope (grants all execute for that extension)
                if action == "execute" and f"ext:{ext_name}:execute" in user_scopes:
                    return True

                # Check if user has ext:name:read (grants all read features for that extension)
                if action == "read" and f"ext:{ext_name}:read" in user_scopes:
                    return True

        # Check standard wildcard patterns (e.g., if user has 'agents:*', they have 'agents:read')
        if len(parts) >= 2:
            resource = parts[0]
            if f"{resource}:*" in user_scopes:
                return True

        return False

    def has_any_scope(self, scopes: list, company_id: str = None) -> bool:
        """
        Check if the user has any of the specified scopes.

        Args:
            scopes: List of scope names to check.
            company_id: The company to check in. Defaults to user's current company.

        Returns:
            bool: True if the user has at least one of the scopes.
        """
        for scope in scopes:
            if self.has_scope(scope, company_id):
                return True
        return False

    def has_all_scopes(self, scopes: list, company_id: str = None) -> bool:
        """
        Check if the user has all of the specified scopes.

        Args:
            scopes: List of scope names to check.
            company_id: The company to check in. Defaults to user's current company.

        Returns:
            bool: True if the user has all of the scopes.
        """
        for scope in scopes:
            if not self.has_scope(scope, company_id):
                return False
        return True

    def require_scope(self, scope: str, company_id: str = None):
        """
        Require a specific scope, raising an HTTPException if not authorized.

        Args:
            scope: The scope to require.
            company_id: The company to check in. Defaults to user's current company.

        Raises:
            HTTPException: 403 if user doesn't have the required scope.
        """
        if not self.has_scope(scope, company_id):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required scope: {scope}",
            )

    def require_any_scope(self, scopes: list, company_id: str = None):
        """
        Require at least one of the specified scopes.

        Args:
            scopes: List of scope names to check.
            company_id: The company to check in. Defaults to user's current company.

        Raises:
            HTTPException: 403 if user doesn't have any of the required scopes.
        """
        if not self.has_any_scope(scopes, company_id):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required one of: {', '.join(scopes)}",
            )

    def user_exists(self, email: str = None):
        self.email = (
            str(email)
            .replace("%2B", "+")
            .replace("%2F", "/")
            .replace("%3D", "=")
            .replace("%20", " ")
            .replace("%3A", ":")
            .replace("%3F", "?")
            .replace("%26", "&")
            .replace("%23", "#")
            .replace("%3B", ";")
            .replace("%40", "@")
            .replace("%21", "!")
            .replace("%24", "$")
            .replace("%27", "'")
            .replace("%28", "(")
            .replace("%29", ")")
            .replace("%2A", "*")
            .replace("%2C", ",")
            .replace("%3B", ";")
            .replace("%5B", "[")
            .replace("%5D", "]")
            .replace("%7B", "{")
            .replace("%7D", "}")
            .replace("%7C", "|")
            .replace("%5C", "\\")
            .replace("%5E", "^")
            .replace("%60", "`")
            .replace("%7E", "~")
        )
        self.email = email.lower()
        session = get_session()
        # Only consider active users as "existing" - inactive users can re-register
        user = (
            session.query(User)
            .filter(User.email == self.email, User.is_active == True)
            .first()
        )
        if not user:
            self.send_email_code()
            self.send_sms_code()
            session.close()
            return False
        session.close()
        return True

    def user_exists_any(self, email: str) -> bool:
        """
        Check if a user exists with this email, regardless of active status.
        """
        self.email = email.lower()
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        session.close()
        return user is not None

    def reactivate_user_with_invitation(
        self,
        email: str,
        invitation_id: str,
        first_name: str = None,
        last_name: str = None,
    ) -> dict:
        """
        Reactivate an inactive user and add them to the invited company.
        """
        email = email.lower()
        with get_session() as session:
            # Get the invitation
            invitation = (
                session.query(Invitation).filter(Invitation.id == invitation_id).first()
            )

            if not invitation:
                return {"error": "Invalid invitation"}

            # Get the inactive user
            user = (
                session.query(User)
                .filter(User.email == email, User.is_active == False)
                .first()
            )

            if not user:
                return {"error": "User not found"}

            # Update user info if provided
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name

            # Reactivate the user
            user.is_active = True

            # Check if user is already in this company
            existing_membership = (
                session.query(UserCompany)
                .filter(
                    UserCompany.user_id == user.id,
                    UserCompany.company_id == invitation.company_id,
                )
                .first()
            )

            if existing_membership:
                session.commit()
                return {"already_in_company": True, "user_id": str(user.id)}

            # Add user to the new company
            new_membership = UserCompany(
                user_id=user.id,
                company_id=invitation.company_id,
                role_id=invitation.role_id,
            )
            session.add(new_membership)

            # Mark invitation as accepted
            invitation.is_accepted = True
            session.commit()

            # Invalidate cache
            invalidate_user_company_cache(str(user.id))

            # Generate login link for the user
            totp = pyotp.TOTP(user.mfa_token)
            otp_uri = totp.provisioning_uri(name=email, issuer_name=getenv("APP_NAME"))
            login = Login(email=email, token=totp.now())
            magic_link = self.send_magic_link(
                ip_address="user_reactivation", login=login, send_link=False
            )

            return {
                "reactivated": True,
                "added_to_company": True,
                "otp_uri": otp_uri,
                "magic_link": magic_link,
                "message": "Your account has been reactivated and you have been added to the company.",
            }

    def handle_existing_user_invitation(self, email: str, invitation_id: str) -> dict:
        """
        Handle registration attempt for a user that already exists.
        If they're not in the invited company, add them to it.
        If they're already in the company, return a conflict indicator.
        """
        email = email.lower()
        with get_session() as session:
            # Get the invitation
            invitation = (
                session.query(Invitation).filter(Invitation.id == invitation_id).first()
            )

            if not invitation:
                return {"error": "Invalid invitation"}

            # Get the existing user
            user = (
                session.query(User)
                .filter(User.email == email, User.is_active == True)
                .first()
            )

            if not user:
                return {"error": "User not found"}

            # Check if user is already in this company
            existing_membership = (
                session.query(UserCompany)
                .filter(
                    UserCompany.user_id == user.id,
                    UserCompany.company_id == invitation.company_id,
                )
                .first()
            )

            if existing_membership:
                return {"already_in_company": True, "user_id": str(user.id)}

            # Add user to the new company
            new_membership = UserCompany(
                user_id=user.id,
                company_id=invitation.company_id,
                role_id=invitation.role_id,
            )
            session.add(new_membership)

            # Mark invitation as accepted
            invitation.is_accepted = True
            session.commit()

            # Invalidate cache
            invalidate_user_company_cache(str(user.id))

            # Generate login link for the user
            totp = pyotp.TOTP(user.mfa_token)
            login = Login(email=email, token=totp.now())
            magic_link = self.send_magic_link(
                ip_address="invitation_acceptance", login=login, send_link=False
            )

            return {
                "added_to_company": True,
                "magic_link": magic_link,
                "message": "You have been added to the company. Use the link to log in.",
            }

    def add_failed_login(self, ip_address):
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        if user is not None:
            failed_login = FailedLogins(user_id=user.id, ip_address=ip_address)
            session.add(failed_login)
            session.commit()
        session.close()

    def count_failed_logins(self):
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        if user is None:
            session.close()
            return 0
        failed_logins = (
            session.query(FailedLogins)
            .filter(FailedLogins.user_id == self.user_id)
            .filter(FailedLogins.created_at >= datetime.now() - timedelta(hours=24))
            .count()
        )
        session.close()
        return failed_logins

    def send_magic_link(
        self,
        ip_address,
        login: Login,
        referrer=None,
        send_link: bool = False,
    ):
        self.email = login.email.lower()
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        if user is None:
            session.close()
            raise HTTPException(status_code=404, detail="User not found")

        # Clear the current token and user_id to ensure fresh generation
        self.token = None
        self.user_id = None

        if not pyotp.TOTP(user.mfa_token).verify(login.token, valid_window=60):
            self.add_failed_login(ip_address=ip_address)
            session.close()
            raise HTTPException(
                status_code=401, detail="Invalid MFA token. Please try again."
            )

        # --- Start Calculation ---

        # 1. Get the timezone name from the environment variable
        tz_name = getenv("TZ")
        if not tz_name:
            print("Warning: TZ environment variable not set. Defaulting to UTC.")
            tz_name = "UTC"  # Default to UTC if not set

        # 2. Get the timezone object
        try:
            server_tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            print(f"Warning: Timezone '{tz_name}' not found. Defaulting to UTC.")
            server_tz = ZoneInfo("UTC")  # Default to UTC if invalid

        # 3. Get the current time *in the server's timezone*
        now = datetime.now(server_tz)

        # 4. Calculate the next month and year based on the current aware time
        current_year = now.year
        current_month = now.month

        next_month = current_month + 1
        next_year = current_year
        if next_month > 12:
            next_month = 1
            next_year += 1

        # 5. Create the expiration datetime for the first day of the next month
        #    at midnight *in the server's timezone*.
        #    Crucially, associate the timezone directly during creation.
        expiration = datetime(
            year=next_year,
            month=next_month,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=server_tz,  # Associate the server's timezone
        )
        # --- End Calculation ---

        # Generate a completely new JWT token for the user
        # Include 'iat' (issued at) to ensure each token is unique
        new_token = jwt.encode(
            {
                "sub": str(user.id),
                "email": self.email,
                "admin": user.admin,
                "exp": expiration,
                "iat": datetime.now().timestamp(),  # This makes each token unique
            },
            self.encryption_key,
            algorithm="HS256",
        )

        # Set the new token as the current token
        self.token = new_token
        self.user_id = str(user.id)
        token = (
            self.token.replace("+", "%2B")
            .replace("/", "%2F")
            .replace("=", "%3D")
            .replace(" ", "%20")
            .replace(":", "%3A")
            .replace("?", "%3F")
            .replace("&", "%26")
            .replace("#", "%23")
            .replace(";", "%3B")
            .replace("@", "%40")
            .replace("!", "%21")
            .replace("$", "%24")
            .replace("'", "%27")
            .replace("(", "%28")
            .replace(")", "%29")
            .replace("*", "%2A")
            .replace(",", "%2C")
            .replace(";", "%3B")
            .replace("[", "%5B")
            .replace("]", "%5D")
            .replace("{", "%7B")
            .replace("}", "%7D")
            .replace("|", "%7C")
            .replace("\\", "%5C")
            .replace("^", "%5E")
            .replace("`", "%60")
            .replace("~", "%7E")
        )
        if referrer is not None:
            self.link = referrer
        magic_link = f"{self.link}?token={token}"
        if send_link:
            email_send = send_email(
                email=self.email,
                subject="Magic Link",
                body=f"<a href='{magic_link}'>Click here to log in</a>",
            )
            if not email_send:
                session.close()
                return magic_link
            # Upon clicking the link, the front end will call the login method and save the email and encrypted_id in the session
            session.close()
            return f"A login link has been sent to {self.email}, please check your email and click the link to log in. The link will expire in 24 hours."
        return magic_link

    def login(self, ip_address):
        """ "
        Login method to verify the token and return the user object

        :param ip_address: IP address of the user
        :return: User object
        """
        failures = self.count_failed_logins()
        if failures >= 100:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts today. Please try again tomorrow.",
            )
        session = get_session()

        # Check if token is blacklisted before validation
        blacklisted_token = (
            session.query(TokenBlacklist)
            .filter(TokenBlacklist.token == self.token)
            .first()
        )
        if blacklisted_token:
            session.close()
            raise HTTPException(
                status_code=401,
                detail="Token has been revoked. Please log in again.",
            )

        try:
            user_info = jwt.decode(
                jwt=self.token,
                key=self.encryption_key,
                algorithms=["HS256"],
                leeway=timedelta(hours=5),
            )
        except:
            self.add_failed_login(ip_address=ip_address)
            session.close()
            raise HTTPException(
                status_code=401,
                detail="Invalid login token. Please log out and try again.",
            )
        user_id = user_info["sub"]
        user = session.query(User).filter(User.id == user_id).first()
        if user is None:
            session.close()
            raise HTTPException(status_code=404, detail="User not found")
        if str(user.id) == str(user_id):
            # Check if this user should be promoted to super admin
            superadmin_email = getenv("SUPERADMIN_EMAIL").lower()
            if superadmin_email and user.email.lower() == superadmin_email:
                # Check all user companies and promote to role 0 if not already
                user_companies = (
                    session.query(UserCompany)
                    .filter(UserCompany.user_id == user_id)
                    .all()
                )
                for uc in user_companies:
                    if uc.role_id != 0:
                        logging.info(
                            f"Promoting user {user.email} to super admin (role 0) in company {uc.company_id} "
                            f"(was role {uc.role_id}) due to SUPERADMIN_EMAIL configuration"
                        )
                        uc.role_id = 0
                        session.commit()
                        invalidate_user_scopes_cache(
                            user_id=str(user_id), company_id=str(uc.company_id)
                        )
            session.close()
            return user
        session.close()
        self.add_failed_login(ip_address=ip_address)
        raise HTTPException(
            status_code=401,
            detail="Invalid login token. Please log out and try again.",
        )

    def refresh_oauth_token(self, provider: str, force_refresh: bool = False):
        """Refresh OAuth token if expired or forced

        Args:
            provider: OAuth provider name
            force_refresh: Force refresh even if token appears valid

        Returns:
            str: New access token
        """
        session = get_session()
        try:
            provider_record = (
                session.query(OAuthProvider)
                .filter(OAuthProvider.name == provider)
                .first()
            )
            if not provider_record:
                raise HTTPException(status_code=404, detail="Provider not found")

            user_oauth = (
                session.query(UserOAuth)
                .filter(UserOAuth.user_id == self.user_id)
                .filter(UserOAuth.provider_id == provider_record.id)
                .first()
            )

            if not user_oauth:
                raise HTTPException(
                    status_code=404, detail="OAuth connection not found"
                )

            # Check if refresh token is available
            if not user_oauth.refresh_token:
                logging.warning(f"No refresh token available for {provider} provider")
                # Special case for providers that don't support refresh tokens
                if provider.lower() in ["github"]:
                    raise HTTPException(
                        status_code=401,
                        detail=f"{provider} tokens are long-lived and don't support refresh. If you're experiencing authentication issues, please re-authenticate.",
                    )
                else:
                    raise HTTPException(
                        status_code=401,
                        detail=f"No refresh token available for {provider}. Please re-authenticate.",
                    )

            # Determine if token needs refresh
            needs_refresh = force_refresh
            if not needs_refresh and user_oauth.token_expires_at:
                # Refresh if token expires within the next 5 minutes
                needs_refresh = (
                    user_oauth.token_expires_at <= datetime.now() + timedelta(minutes=5)
                )
            elif not needs_refresh and not user_oauth.token_expires_at:
                # If we don't know when it expires, assume it might be expired
                logging.warning(
                    f"No expiration time stored for {provider} token, attempting refresh"
                )
                needs_refresh = True

            if needs_refresh:
                try:
                    sso_instance = get_sso_instance(provider)(
                        access_token=user_oauth.access_token,
                        refresh_token=user_oauth.refresh_token,
                    )
                    new_tokens = sso_instance.get_new_token()

                    # Handle different response formats from providers
                    if isinstance(new_tokens, str):
                        # Some providers just return the access token as a string
                        user_oauth.access_token = new_tokens
                    elif isinstance(new_tokens, dict):
                        # Standard OAuth response format
                        if "access_token" in new_tokens:
                            user_oauth.access_token = new_tokens["access_token"]
                        else:
                            raise ValueError("No access_token in refresh response")

                        # Update refresh token if provided (some providers rotate refresh tokens)
                        if "refresh_token" in new_tokens:
                            user_oauth.refresh_token = new_tokens["refresh_token"]

                        # Update expiration time if provided
                        if "expires_in" in new_tokens:
                            user_oauth.token_expires_at = datetime.now() + timedelta(
                                seconds=int(new_tokens["expires_in"])
                            )
                        elif "expires_at" in new_tokens:
                            user_oauth.token_expires_at = datetime.fromtimestamp(
                                new_tokens["expires_at"]
                            )
                    else:
                        raise ValueError(
                            f"Unexpected token response format: {type(new_tokens)}"
                        )

                    session.commit()
                    return user_oauth.access_token

                except Exception as e:
                    session.rollback()
                    logging.error(f"Failed to refresh {provider} token: {str(e)}")
                    raise HTTPException(
                        status_code=401,
                        detail=f"Failed to refresh {provider} token. Please re-authenticate. Error: {str(e)}",
                    )
            else:
                # Token is still valid, return existing token
                return user_oauth.access_token

        finally:
            session.close()

    def get_oauth_functions(self, provider: str):
        """Get OAuth functions with automatic token refresh handling

        Args:
            provider: OAuth provider name

        Returns:
            SSO instance with valid access token
        """
        session = get_session()
        try:
            user = session.query(User).filter(User.id == self.user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            provider_record = (
                session.query(OAuthProvider)
                .filter(OAuthProvider.name == provider)
                .first()
            )
            if not provider_record:
                raise HTTPException(status_code=404, detail="Provider not found")

            user_oauth = (
                session.query(UserOAuth)
                .filter(UserOAuth.user_id == self.user_id)
                .filter(UserOAuth.provider_id == provider_record.id)
                .first()
            )
            if not user_oauth:
                raise HTTPException(status_code=404, detail="User OAuth not found")

            # Always check and refresh token if needed before creating the SSO instance
            try:
                access_token = self.refresh_oauth_token(provider)
            except HTTPException as e:
                # If refresh fails, the user needs to re-authenticate
                session.close()
                raise e

            # Create SSO instance with fresh token and refresh token for future use
            session.close()
            return get_sso_instance(provider.name)(
                access_token=access_token, refresh_token=user_oauth.refresh_token
            )

        except HTTPException:
            session.close()
            raise
        except Exception as e:
            session.close()
            logging.error(f"Error getting OAuth functions for {provider}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error accessing {provider} OAuth functions: {str(e)}",
            )

    def oauth_api_call(self, provider: str, api_call_func, *args, **kwargs):
        """Execute an OAuth API call with automatic token refresh retry

        Args:
            provider: OAuth provider name
            api_call_func: Function to call that makes the API request
            *args, **kwargs: Arguments to pass to the API call function

        Returns:
            Result of the API call
        """
        max_retries = 2

        for attempt in range(max_retries):
            try:
                # Get OAuth functions (this will refresh token if needed)
                oauth_functions = self.get_oauth_functions(provider)

                # Execute the API call
                return api_call_func(oauth_functions, *args, **kwargs)

            except HTTPException as e:
                # If it's an auth error and we haven't tried refreshing yet, try once more
                if (
                    e.status_code == 401 or e.status_code == 403
                ) and attempt < max_retries - 1:
                    try:
                        # Force refresh the token
                        self.refresh_oauth_token(provider, force_refresh=True)
                        continue  # Retry the call
                    except Exception as refresh_error:
                        logging.error(f"Token refresh failed: {str(refresh_error)}")
                        raise HTTPException(
                            status_code=401,
                            detail=f"Authentication failed for {provider}. Please re-authenticate.",
                        )
                else:
                    # Re-raise the original exception if not an auth error or max retries reached
                    raise e

            except Exception as e:
                # Handle non-HTTP exceptions that might indicate token issues
                error_str = str(e).lower()
                if (
                    any(
                        keyword in error_str
                        for keyword in [
                            "unauthorized",
                            "forbidden",
                            "invalid_token",
                            "token_expired",
                        ]
                    )
                    and attempt < max_retries - 1
                ):
                    try:
                        # Force refresh the token
                        self.refresh_oauth_token(provider, force_refresh=True)
                        continue  # Retry the call
                    except Exception as refresh_error:
                        logging.error(f"Token refresh failed: {str(refresh_error)}")
                        raise HTTPException(
                            status_code=401,
                            detail=f"Authentication failed for {provider}. Please re-authenticate.",
                        )
                else:
                    # Re-raise the original exception
                    raise e

        # Should not reach here, but just in case
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete OAuth API call for {provider} after {max_retries} attempts",
        )

    def refresh_all_oauth_tokens(self):
        """Proactively refresh all OAuth tokens that are expiring soon

        Returns:
            dict: Results of refresh attempts for each provider
        """
        session = get_session()
        results = {}

        try:
            user_oauth_connections = (
                session.query(UserOAuth).filter(UserOAuth.user_id == self.user_id).all()
            )

            for user_oauth in user_oauth_connections:
                provider_record = (
                    session.query(OAuthProvider)
                    .filter(OAuthProvider.id == user_oauth.provider_id)
                    .first()
                )

                if not provider_record:
                    continue

                provider_name = provider_record.name

                try:
                    # Check if token needs refresh (expires within 10 minutes)
                    needs_refresh = False
                    if user_oauth.token_expires_at:
                        needs_refresh = (
                            user_oauth.token_expires_at
                            <= datetime.now() + timedelta(minutes=10)
                        )

                    if needs_refresh and user_oauth.refresh_token:
                        new_token = self.refresh_oauth_token(provider_name)
                        results[provider_name] = {
                            "status": "refreshed",
                            "message": "Token refreshed successfully",
                        }
                    elif not user_oauth.refresh_token:
                        results[provider_name] = {
                            "status": "warning",
                            "message": "No refresh token available",
                        }
                    else:
                        results[provider_name] = {
                            "status": "valid",
                            "message": "Token still valid",
                        }

                except Exception as e:
                    logging.error(
                        f"Failed to refresh token for {provider_name}: {str(e)}"
                    )
                    results[provider_name] = {"status": "error", "message": str(e)}

            return results

        finally:
            session.close()

    def get_oauth_token_status(self):
        """Get the status of all OAuth tokens for the user

        Returns:
            dict: Status information for each OAuth connection
        """
        session = get_session()

        try:
            user_oauth_connections = (
                session.query(UserOAuth)
                .options(joinedload(UserOAuth.provider))
                .filter(UserOAuth.user_id == self.user_id)
                .all()
            )

            status_info = {}

            for user_oauth in user_oauth_connections:
                provider_name = user_oauth.provider.name

                token_status = {
                    "provider": provider_name,
                    "has_access_token": bool(user_oauth.access_token),
                    "has_refresh_token": bool(user_oauth.refresh_token),
                    "expires_at": (
                        user_oauth.token_expires_at.isoformat()
                        if user_oauth.token_expires_at
                        else None
                    ),
                    "is_expired": False,
                    "expires_soon": False,
                }

                if user_oauth.token_expires_at:
                    now = datetime.now()
                    token_status["is_expired"] = user_oauth.token_expires_at <= now
                    token_status["expires_soon"] = (
                        user_oauth.token_expires_at <= now + timedelta(minutes=10)
                    )

                status_info[provider_name] = token_status

            return status_info

        finally:
            session.close()

    def check_user_limit(self, company_id: str) -> bool:
        """Check if a company can add more users based on billing model.

        For seat-based billing:
            - per_user (XT Systems): Checks if current user count < user_limit (paid seats)
            - per_capacity (NurseXT): user_limit represents paid beds - doesn't limit users
            - per_location (UltraEstimate): Checks if child company count < user_limit (paid locations)

        For token-based billing (per_token):
            - Checks if company has a positive token balance

        Returns:
            True = company can add users/locations
            False = company cannot add users/locations (limit reached or no balance)
        """
        from ExtensionsHub import ExtensionsHub

        # Check if billing is enabled
        price_service = PriceService()
        token_price = price_service.get_token_price()

        # Get pricing config to determine billing model
        hub = ExtensionsHub()
        pricing_config = hub.get_pricing_config()
        pricing_model = (
            pricing_config.get("pricing_model") if pricing_config else "per_token"
        )

        # Check if billing is disabled
        billing_enabled = token_price > 0 or (
            pricing_config and pricing_config.get("tiers")
        )

        if not billing_enabled:
            # Billing is disabled, allow all operations
            return True

        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            # Get the root parent company for billing purposes
            # Child companies consume from their root parent
            root_company_id = self.get_root_parent_company(company_id, session=session)
            if str(root_company_id) != str(company_id):
                billing_company = (
                    session.query(Company).filter(Company.id == root_company_id).first()
                )
                if not billing_company:
                    billing_company = company
            else:
                billing_company = company

            # user_limit represents paid capacity on root parent company
            paid_limit = billing_company.user_limit or 0

            # For per_user billing (XT Systems): count users against paid seats
            if pricing_model == "per_user":
                current_user_count = (
                    session.query(UserCompany)
                    .filter(UserCompany.company_id == company_id)
                    .count()
                )
                if current_user_count < paid_limit:
                    return True
                # Fallback to token balance
                if billing_company.token_balance and billing_company.token_balance > 0:
                    return True
                return False

            # For per_capacity billing (NurseXT): beds are declared capacity, not user limit
            # Users are unlimited - the capacity (beds) is just what they pay for
            elif pricing_model == "per_capacity":
                # Check they have paid for some capacity or have token balance
                if paid_limit > 0:
                    return True
                if billing_company.token_balance and billing_company.token_balance > 0:
                    return True
                return False

            # For per_location billing (UltraEstimate): count child companies as locations
            elif pricing_model == "per_location":
                # Count child companies under the root parent (each child = 1 location)
                child_company_count = (
                    session.query(Company)
                    .filter(Company.company_id == billing_company.id)
                    .count()
                )
                # The root company itself counts as 1 location
                total_locations = child_company_count + 1
                if total_locations <= paid_limit:
                    return True
                # Fallback to token balance
                if billing_company.token_balance and billing_company.token_balance > 0:
                    return True
                return False

            # For token-based billing, check root parent company's token balance
            if billing_company.token_balance and billing_company.token_balance > 0:
                return True

            return False
        finally:
            session.close()

    def _has_active_payment_transaction(self, session, user_companies) -> bool:
        direct_payment = (
            session.query(PaymentTransaction)
            .filter(PaymentTransaction.status == "completed")
            .filter(PaymentTransaction.user_id == self.user_id)
            .first()
        )
        if direct_payment:
            return True

        company_ids = {
            user_company.company_id
            for user_company in user_companies
            if getattr(user_company, "company_id", None)
        }
        if company_ids:
            company_payment = (
                session.query(PaymentTransaction)
                .filter(PaymentTransaction.status == "completed")
                .filter(PaymentTransaction.company_id.in_(list(company_ids)))
                .first()
            )
            if company_payment:
                return True
        return False

    def _has_sufficient_token_balance(self, session, user_companies) -> bool:
        """Check if any of the user's companies (or their root parents) have a positive token balance or valid subscription.

        For token-based billing: checks token_balance > 0
        For seat-based billing: checks token_balance_usd > 0 (trial credits) or active subscription

        Child companies inherit billing from their root parent company.
        """
        from ExtensionsHub import ExtensionsHub

        company_ids = {
            user_company.company_id
            for user_company in user_companies
            if getattr(user_company, "company_id", None)
        }
        if not company_ids:
            return False

        # Expand company_ids to include root parent companies
        # Child companies consume from their root parent
        all_company_ids = set(company_ids)
        for cid in company_ids:
            root_id = self.get_root_parent_company(str(cid), session=session)
            if root_id:
                all_company_ids.add(root_id)

        # Get pricing model
        hub = ExtensionsHub()
        pricing_config = hub.get_pricing_config()
        pricing_model = (
            pricing_config.get("pricing_model") if pricing_config else "per_token"
        )
        is_seat_based = pricing_model in ["per_user", "per_capacity", "per_location"]

        if is_seat_based:
            # For seat-based billing, check:
            # 1. Trial credits (token_balance_usd > 0)
            # 2. Active subscription (stripe_subscription_id exists and auto_topup_enabled)
            company_with_credits = (
                session.query(Company)
                .filter(Company.id.in_(list(all_company_ids)))
                .filter(
                    (Company.token_balance_usd > 0)  # Has trial credits
                    | (
                        (Company.stripe_subscription_id != None)
                        & (Company.auto_topup_enabled == True)
                    )  # Has subscription
                )
                .first()
            )
            if company_with_credits:
                return True
        else:
            # For token-based billing, check token_balance on all companies including parents
            company_with_balance = (
                session.query(Company)
                .filter(Company.id.in_(list(all_company_ids)))
                .filter(Company.token_balance > 0)
                .first()
            )
            if company_with_balance:
                return True

        return False

    def check_billing_balance(self):
        """
        Pre-check if the user has sufficient token balance before running inference.
        Raises HTTPException 402 if billing is enabled and balance is insufficient.
        Should be called before any billable operation (inference, etc).
        Super admins (role 0) are exempt from billing checks.
        """
        # Check if billing is enabled
        price_service = PriceService()
        token_price = price_service.get_token_price()
        billing_enabled = token_price > 0

        if not billing_enabled:
            # Billing is disabled, allow all operations
            return True

        # Get wallet address for the 402 response
        wallet_address = getenv("PAYMENT_WALLET_ADDRESS", "")

        session = get_session()
        try:
            # Get user's companies
            user_companies = (
                session.query(UserCompany)
                .filter(UserCompany.user_id == self.user_id)
                .all()
            )

            # Super admins (role 0) are exempt from paywall
            is_super_admin = any(uc.role_id == 0 for uc in user_companies)
            if is_super_admin:
                return True

            # Check if any company has sufficient balance
            if self._has_sufficient_token_balance(session, user_companies):
                return True

            # No sufficient balance found - raise 402
            raise HTTPException(
                status_code=402,
                detail={
                    "message": "Insufficient token balance. Please top up your tokens to continue.",
                    "customer_session": {"client_secret": None},
                    "wallet_address": wallet_address,
                    "token_price_per_million_usd": float(token_price),
                },
            )
        finally:
            session.close()

    def register(
        self, new_user: Register, invitation_id: str = None, verify_email: bool = False
    ):
        new_user.email = new_user.email.lower()
        self.email = new_user.email
        mfa_token = pyotp.random_base32()
        try:
            session = get_session()
            # Check if user already exists
            existing_user = session.query(User).filter(User.email == self.email).first()
            if existing_user:
                session.close()
                return {"error": "User already exists", "status_code": 409}

            # Check for invitation
            invitation = (
                session.query(Invitation).filter(Invitation.email == self.email).first()
            )

            # Determine if paywall is enabled for this instance
            # Paywall is enabled if token billing is configured (TOKEN_PRICE_PER_MILLION_USD > 0)
            price_service = PriceService()
            try:
                token_price = price_service.get_token_price()
            except Exception:
                token_price = Decimal("0")
            token_billing_enabled = token_price > 0

            stripe_configured = (
                getenv("STRIPE_API_KEY")
                and str(getenv("STRIPE_API_KEY")).lower() != "none"
                and token_billing_enabled
            )
            wallet_address = getenv("PAYMENT_WALLET_ADDRESS", "")
            wallet_paywall_enabled = (
                bool(wallet_address)
                and str(wallet_address).lower() != "none"
                and token_billing_enabled
            )
            paywall_enabled = stripe_configured or wallet_paywall_enabled

            # Create new user
            # Set is_active=False if paywall is enabled (requires payment)
            # Set is_active=True if no paywall (free instance)
            new_user_db = User(
                email=self.email,
                first_name=new_user.first_name,
                last_name=new_user.last_name,
                mfa_token=mfa_token,
                is_active=not paywall_enabled,  # False if paywall enabled, True if free instance
            )
            session.add(new_user_db)
            session.commit()
            session.flush()  # Flush to get the new user's ID
            self.user_id = str(new_user_db.id)
            company_id = None
            if invitation:
                # User was invited - use invitation details
                verify_email = True
                company_id = invitation.company_id
                role_id = invitation.role_id
                invitation.is_accepted = True
                # Create user-company association
                user_company = UserCompany(
                    user_id=new_user_db.id,
                    company_id=company_id,
                    role_id=role_id,
                )
                session.add(user_company)
                session.commit()
                # Check if this user should be promoted to super admin
                promote_superadmin_if_needed(
                    session=session,
                    user_id=str(new_user_db.id),
                    email=self.email,
                    company_id=str(company_id),
                )
                # Invalidate user company cache since company membership changed
                invalidate_user_company_cache(str(new_user_db.id))
                # Create agent directly without login overhead
                agixt = InternalClient(api_key=None, user=new_user.email)
                agixt._user = new_user.email
                default_agent = get_default_agent()
                if company_id is not None:
                    default_agent["settings"]["company_id"] = str(invitation.company_id)
                company = (
                    session.query(Company).filter(Company.id == company_id).first()
                )
                agixt.add_agent(
                    agent_name=company.agent_name,
                    settings=default_agent["settings"],
                    commands=default_agent["commands"],
                    training_urls=default_agent.get("training_urls", []),
                )
            else:
                # If email ends in .xt, skip this part
                if not self.email.endswith(".xt"):
                    # Create a new company for the user
                    company_name = (
                        f"{new_user.first_name}'s Team"
                        if new_user.first_name
                        else "My Team"
                    )
                    if new_user.first_name:
                        if new_user.first_name.endswith("s"):
                            company_name = f"{new_user.first_name}' Team"
                        else:
                            company_name = f"{new_user.first_name}'s Team"
                    new_company = self.create_company_with_agent(name=company_name)

                    # Grant trial credits for business domains
                    try:
                        from TrialService import grant_trial_credits

                        success, message, credits = grant_trial_credits(
                            company_id=new_company["id"],
                            user_id=str(new_user_db.id),
                            email=self.email,
                        )
                        if success:
                            logging.info(
                                f"Trial credits granted for {self.email}: {message}"
                            )
                        else:
                            logging.debug(
                                f"Trial credits not granted for {self.email}: {message}"
                            )
                    except Exception as e:
                        logging.warning(f"Error checking trial eligibility: {e}")

            # Add default user preferences
            default_preferences = [
                ("timezone", getenv("TZ")),
                ("input_tokens", "0"),
                ("output_tokens", "0"),
                ("verify_email", "true" if verify_email else "false"),
            ]
            for pref_key, pref_value in default_preferences:
                user_preference = UserPreferences(
                    user_id=new_user_db.id,
                    pref_key=pref_key,
                    pref_value=pref_value,
                )
                session.add(user_preference)
            session.commit()
            session.close()
            return {"mfa_token": mfa_token, "status_code": 200}

        except Exception as e:
            logging.error(f"Unexpected error during registration: {str(e)}")
            logging.error(traceback.format_exc())
            return {
                "error": f"An unexpected error occurred: {str(e)}",
                "status_code": 500,
            }

    def update_user(self, **kwargs):
        self.validate_user()
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        allowed_keys = list(UserInfo.__annotations__.keys())
        user_preferences = (
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == self.user_id)
            .all()
        )
        if "subscription" in kwargs:
            del kwargs["subscription"]
        if "email" in kwargs:
            del kwargs["email"]
        if "input_tokens" in kwargs:
            del kwargs["input_tokens"]
        if "output_tokens" in kwargs:
            del kwargs["output_tokens"]
        for key, value in kwargs.items():
            if "password" in key.lower():
                value = encrypt(self.encryption_key, value)
            if "api_key" in key.lower():
                value = encrypt(self.encryption_key, value)
            if "_secret" in key.lower():
                value = encrypt(self.encryption_key, value)
            if key == "phone_number":
                # Remove anything that isn't a number
                value = "".join([x for x in value if x.isdigit()])
            if key in allowed_keys:
                setattr(user, key, value)
            else:
                # Check if there is a user preference record, create one if not, update if so.
                user_preference = next(
                    (x for x in user_preferences if x.pref_key == key),
                    None,
                )
                if user_preference is None:
                    user_preference = UserPreferences(
                        user_id=self.user_id,
                        pref_key=key,
                        pref_value=value,
                    )
                    session.add(user_preference)
                else:
                    user_preference.pref_value = str(value)
        session.commit()
        session.close()
        return "User updated successfully."

    def delete_company(self, company_id):
        """
        Delete a company and remove all associated records.

        Authorization:
        - Super admins can delete any company (via has_scope)
        - Users with 'company:delete' scope can delete companies they have access to
        """
        self.validate_user()

        # Check if user has company:delete scope (super admins automatically pass via has_scope)
        if not self.has_scope("company:delete", company_id):
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. You do not have permission to delete this company.",
            )

        session = get_session()
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            session.close()
            raise HTTPException(status_code=404, detail="Company not found")

        try:
            # Delete in order of dependencies (most dependent first)

            # Import all models needed for cascade delete
            from DB import (
                CompanyChain,
                CompanyChainStep,
                CompanyChainStepArgument,
                CompanyPrompt,
                CompanyPromptCategory,
                CompanyPromptArgument,
                CompanyExtensionCommand,
                CompanyExtensionSetting,
                CustomRole,
                UserCustomRole,
                Invitation,
                WebhookOutgoing,
                CompanyTokenUsage,
                PaymentTransaction,
                TrialDomain,
            )

            # Clear parent reference on child companies (set their company_id to null)
            # This prevents orphaned child companies from pointing to a deleted parent
            session.query(Company).filter(Company.company_id == company_id).update(
                {"company_id": None}, synchronize_session=False
            )

            # Get all company chains first
            company_chains = (
                session.query(CompanyChain)
                .filter(CompanyChain.company_id == company_id)
                .all()
            )
            for chain in company_chains:
                # Delete chain step arguments
                session.query(CompanyChainStepArgument).filter(
                    CompanyChainStepArgument.chain_step_id.in_(
                        session.query(CompanyChainStep.id).filter(
                            CompanyChainStep.chain_id == chain.id
                        )
                    )
                ).delete(synchronize_session=False)
                # Delete chain steps
                session.query(CompanyChainStep).filter(
                    CompanyChainStep.chain_id == chain.id
                ).delete(synchronize_session=False)
            # Delete chains
            session.query(CompanyChain).filter(
                CompanyChain.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete company prompt arguments (depends on prompts)
            session.query(CompanyPromptArgument).filter(
                CompanyPromptArgument.prompt_id.in_(
                    session.query(CompanyPrompt.id).filter(
                        CompanyPrompt.company_id == company_id
                    )
                )
            ).delete(synchronize_session=False)
            # Delete company prompts (depends on categories)
            session.query(CompanyPrompt).filter(
                CompanyPrompt.company_id == company_id
            ).delete(synchronize_session=False)
            session.query(CompanyPromptCategory).filter(
                CompanyPromptCategory.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete extension settings and commands
            session.query(CompanyExtensionCommand).filter(
                CompanyExtensionCommand.company_id == company_id
            ).delete(synchronize_session=False)
            session.query(CompanyExtensionSetting).filter(
                CompanyExtensionSetting.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete custom roles
            session.query(CustomRole).filter(
                CustomRole.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete invitations
            session.query(Invitation).filter(
                Invitation.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete webhooks
            session.query(WebhookOutgoing).filter(
                WebhookOutgoing.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete token usage records
            session.query(CompanyTokenUsage).filter(
                CompanyTokenUsage.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete payment transactions
            session.query(PaymentTransaction).filter(
                PaymentTransaction.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete trial domains
            session.query(TrialDomain).filter(
                TrialDomain.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete user company relationships
            session.query(UserCompany).filter(
                UserCompany.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete user custom role assignments for this company
            session.query(UserCustomRole).filter(
                UserCustomRole.company_id == company_id
            ).delete(synchronize_session=False)

            # Delete extension tables that may have company_id FK (using raw SQL since these are dynamically loaded)
            extension_tables = [
                "Ticket",
                "TicketStatus",
                "TicketPriority",
                "TicketType",
                "TicketTemplate",
                "TicketNote",
                "ActivityLog",
                "Contact",
                "Asset",
                "AssetTemplate",
                "AssetItem",
                "AssetFile",
                "approved_ip_range",
                "Secret",
                "SecretItem",
                "Integration",
                "webhook_outgoing",
            ]
            for table in extension_tables:
                try:
                    session.execute(
                        text(f"DELETE FROM {table} WHERE company_id = :company_id"),
                        {"company_id": company_id},
                    )
                except Exception:
                    # Table may not exist or may not have company_id column
                    pass

            # Finally delete the company
            session.delete(company)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

        return "Company deleted successfully"

    def delete_user_from_company(self, company_id: str, target_user_id: str):
        self.validate_user()
        session = get_session()

        # Check if user has permission to delete users from this company
        if not self.has_scope("users:delete", company_id):
            session.close()
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions to remove users.",
            )

        user_company = (
            session.query(UserCompany)
            .filter(UserCompany.company_id == company_id)
            .filter(UserCompany.user_id == target_user_id)
            .first()
        )

        if not user_company:
            raise HTTPException(
                status_code=404, detail="User not found in the specified company"
            )

        # Prevent self-deletion for users with management permissions
        if str(target_user_id) == str(self.user_id) and self.has_scope(
            "users:delete", company_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Users with management permissions cannot remove themselves",
            )

        session.delete(user_company)
        session.commit()
        # Invalidate user company cache since company membership changed
        invalidate_user_company_cache(str(target_user_id))

        return "User removed from company successfully"

    def delete_user(self):
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        user.is_active = False
        session.commit()
        session.close()
        return "User deleted successfully"

    def registration_requirements(self):
        if not os.path.exists("registration_requirements.json"):
            requirements = {}
        else:
            with open("registration_requirements.json", "r") as file:
                requirements = json.load(file)
        if not requirements:
            requirements = {}
        if "stripe_id" not in requirements:
            requirements["stripe_id"] = "None"
        return requirements

    def get_subscribed_products(self, stripe_api_key, user_email):
        """
        Finds ANY active Stripe subscriptions for a given user email.

        This function works by:
        1. Finding all Stripe Customer objects associated with the provided email.
        2. Listing all subscriptions for each found customer.
        3. Filtering for subscriptions that are 'active'.
        4. Returning a list of all active subscriptions found across all matching customers.

        Args:
            stripe_api_key (str): The Stripe API key.
            user_email (str): The email address of the user to check subscriptions for.

        Returns:
            List[stripe.Subscription]: A list of active Stripe Subscription objects.
                                       Returns an empty list if no active subscriptions
                                       are found or if an error occurs.
        """
        import stripe
        import traceback

        if not stripe:
            return []

        stripe.api_key = stripe_api_key
        all_active_subscriptions = []

        try:
            # Step 1: Find customer(s) by email
            customers = stripe.Customer.list(email=user_email, limit=100)

            if not customers.data:
                return []

            # Step 2 & 3: Check active subscriptions for each customer
            for customer in customers.data:
                try:
                    # List subscriptions that should grant access (active, trialing, or past_due in grace period)
                    # We check multiple statuses because:
                    # - "active": paid and active
                    # - "trialing": in trial period (should have access)
                    # - "past_due": payment failed but still in grace period (should have temporary access)
                    for status in ["active", "trialing", "past_due"]:
                        subscriptions_list = stripe.Subscription.list(
                            customer=customer.id,
                            status=status,
                            limit=100,  # Safeguard limit
                        )

                        # Add all found subscriptions to our main list
                        for subscription in subscriptions_list.data:
                            # Avoid adding duplicates
                            if subscription.id not in [
                                sub.id for sub in all_active_subscriptions
                            ]:
                                all_active_subscriptions.append(subscription)

                except stripe.error.StripeError as se_sub:
                    logging.error(
                        f"Stripe API error listing subscriptions for customer {customer.id}: {se_sub}"
                    )
                    if hasattr(se_sub, "error") and se_sub.error:
                        logging.error(
                            f"Stripe error details: code={se_sub.error.code}, param={se_sub.error.param}, type={se_sub.error.type}"
                        )
                except Exception as e_sub:
                    logging.error(
                        f"Unexpected error processing subscriptions for customer {customer.id}: {e_sub}"
                    )
                    logging.error(traceback.format_exc())

            # Step 5: Return the combined list
            return all_active_subscriptions

        except stripe.error.StripeError as se_cust:
            logging.error(
                f"Stripe API error finding customers for email {user_email}: {se_cust}"
            )
            return []
        except Exception as e_cust:
            logging.error(
                f"General error during subscription check for email {user_email}: {e_cust}"
            )
            logging.error(traceback.format_exc())
            return []

    def update_user_role(self, company_id: str, user_id: str, role_id: int):
        if user_id == self.user_id:
            raise HTTPException(
                status_code=403, detail="You cannot change your own role."
            )
        session = get_session()

        # Check if user has permission to manage roles
        if not self.has_scope("users:roles", company_id):
            session.close()
            raise HTTPException(
                status_code=403, detail="User does not have permission to update roles"
            )

        user_company = (
            session.query(UserCompany)
            .filter(UserCompany.user_id == user_id)
            .filter(UserCompany.company_id == company_id)
            .first()
        )
        try:
            role_id = int(role_id)
        except:
            role_id = 3

        # Users can only assign roles at or below their own level
        caller_role = self.get_user_role(company_id)
        if caller_role is not None and role_id < caller_role:
            session.close()
            raise HTTPException(
                status_code=403,
                detail="User does not have permission to assign this role",
            )
        if user_company:
            user_company.role_id = role_id
            session.commit()
            # Invalidate user scopes cache since their role changed
            invalidate_user_scopes_cache(user_id=user_id, company_id=company_id)
        else:
            session.close()
            raise HTTPException(
                status_code=404, detail="User not found in the specified company"
            )
        session.close()
        return "User role updated successfully."

    def get_user_preferences_lightweight(self):
        """
        Get basic user preferences without billing/subscription checks.
        Use this for fast user profile fetches where billing isn't critical.
        For billing-sensitive operations, use get_user_preferences() instead.
        """
        session = get_session()
        try:
            user_preferences = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == self.user_id)
                .all()
            )
            prefs = {x.pref_key: x.pref_value for x in user_preferences}

            # Set defaults
            if "input_tokens" not in prefs:
                prefs["input_tokens"] = 0
            if "output_tokens" not in prefs:
                prefs["output_tokens"] = 0
            if "phone_number" not in prefs:
                prefs["phone_number"] = ""

            # Remove sensitive/duplicate fields
            for key in ["email", "first_name", "last_name"]:
                prefs.pop(key, None)

            return prefs
        finally:
            session.close()

    def get_user_preferences_smart(self):
        """
        Smart user preferences fetch with optimized billing checks:
        - Fast token balance check (DB query) is synchronous
        - If no tokens AND billing enabled → 402 immediately (synchronous)
        - If user has tokens → Return quickly, Stripe checks run in background

        This is ideal for the /v1/user endpoint where speed is critical but
        we still need to enforce the token balance paywall.
        """
        import asyncio
        import threading

        session = get_session()
        try:
            # Fast queries first
            user = session.query(User).filter(User.id == self.user_id).first()
            user_preferences = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == self.user_id)
                .all()
            )
            user_preferences = {x.pref_key: x.pref_value for x in user_preferences}
            user_companies = (
                session.query(UserCompany)
                .filter(UserCompany.user_id == self.user_id)
                .all()
            )

            # Set defaults
            if "input_tokens" not in user_preferences:
                user_preferences["input_tokens"] = 0
            if "output_tokens" not in user_preferences:
                user_preferences["output_tokens"] = 0
            if "phone_number" not in user_preferences:
                user_preferences["phone_number"] = ""

            # Get billing config
            wallet_address = getenv("PAYMENT_WALLET_ADDRESS", "")
            price_service = PriceService()
            try:
                token_price = price_service.get_token_price()
            except Exception:
                token_price = 1

            billing_enabled = token_price > 0
            wallet_paywall_enabled = (
                bool(wallet_address)
                and str(wallet_address).lower() != "none"
                and billing_enabled
            )

            # CRITICAL: Fast token balance check - this MUST be synchronous
            # If user has no tokens and billing is enabled, block with 402
            if wallet_paywall_enabled:
                has_sufficient_balance = self._has_sufficient_token_balance(
                    session, user_companies
                )
                if not has_sufficient_balance:
                    # No tokens and billing enabled - enforce paywall immediately
                    user.is_active = False
                    session.commit()
                    logging.info(
                        f"{self.email} has insufficient token balance at {self.company_id}"
                    )
                    raise HTTPException(
                        status_code=402,
                        detail={
                            "message": "Insufficient token balance. Please top up your tokens.",
                            "customer_session": {
                                "client_secret": None,
                                "company_id": self.company_id,
                            },
                            "wallet_address": wallet_address,
                            "token_price_per_million_usd": float(token_price),
                        },
                    )
                # User has tokens - add wallet info to response
                user_preferences["wallet_address"] = wallet_address
                user_preferences["token_price_per_million_usd"] = float(token_price)

            # User requirements check (fast)
            user_requirements = self.registration_requirements()
            missing_requirements = []
            if user_requirements:
                for key, value in user_requirements.items():
                    if key not in user_preferences and key != "stripe_id":
                        missing_requirements.append({key: value})

            if (
                "verify_email" not in user_preferences
                and getenv("EMAIL_VERIFICATION_ENABLED").lower() == "true"
            ):
                missing_requirements.append({"verify_email": True})
                # Don't block on sending email verification - do it async
                threading.Thread(
                    target=self._send_email_verification_async, daemon=True
                ).start()
            elif "verify_email" in user_preferences:
                del user_preferences["verify_email"]

            if missing_requirements:
                user_preferences["missing_requirements"] = missing_requirements

            # Clean up sensitive fields
            for key in ["email", "first_name", "last_name", "missing_requirements"]:
                if key in user_preferences and key != "missing_requirements":
                    del user_preferences[key]

            # Background Stripe subscription check - only if billing is not paused
            # This doesn't block the response since user already has token balance
            billing_paused = getenv("BILLING_PAUSED", "false").lower() == "true"
            api_key = getenv("STRIPE_API_KEY")
            if (
                not billing_paused
                and api_key
                and api_key.lower() != "none"
                and user.email != getenv("DEFAULT_USER")
                and not user.email.endswith(".xt")
            ):
                # Fire-and-forget Stripe check in background thread
                user_email = user.email
                user_id = self.user_id
                stripe_id = user_preferences.get("stripe_id")
                company_ids = [uc.company_id for uc in user_companies]

                def _background_stripe_check():
                    try:
                        self._background_stripe_subscription_check(
                            api_key, user_email, user_id, stripe_id, company_ids
                        )
                    except Exception as e:
                        logging.debug(f"Background Stripe check failed: {e}")

                threading.Thread(target=_background_stripe_check, daemon=True).start()

            return user_preferences
        finally:
            session.close()

    def _send_email_verification_async(self):
        """Send email verification link in background"""
        try:
            self.send_email_verification_link()
        except Exception as e:
            logging.debug(f"Background email verification failed: {e}")

    def _background_stripe_subscription_check(
        self,
        api_key: str,
        user_email: str,
        user_id: str,
        stripe_id: str,
        company_ids: list,
    ):
        """
        Background Stripe subscription check.
        Updates user's is_active status and stripe_id preference if needed.
        This runs async and doesn't block the response.
        Uses SharedCache to prevent API spam across workers.
        """
        import stripe

        # Check SharedCache first to avoid Stripe API spam
        cache_key = f"stripe_check:{user_id}"
        cached_result = shared_cache.get(cache_key)
        if cached_result is not None:
            # Cache is still valid, skip Stripe API call
            logging.debug(f"Stripe check cache hit for {user_email}")
            return

        stripe.api_key = api_key

        session = get_session()
        try:
            has_subscription = False

            # Check user's own subscription
            if stripe_id:
                relevant_subscriptions = self.get_subscribed_products(
                    api_key, user_email
                )
                if relevant_subscriptions:
                    has_subscription = True

            # Check company admin subscriptions if user doesn't have one
            if not has_subscription and company_ids:
                for company_id in company_ids:
                    company_admins = (
                        session.query(User)
                        .join(UserCompany, User.id == UserCompany.user_id)
                        .filter(UserCompany.company_id == company_id)
                        .filter(UserCompany.role_id <= 2)
                        .all()
                    )
                    for admin in company_admins:
                        admin_prefs = (
                            session.query(UserPreferences)
                            .filter(UserPreferences.user_id == admin.id)
                            .filter(UserPreferences.pref_key == "stripe_id")
                            .first()
                        )
                        if admin_prefs:
                            admin_subscriptions = self.get_subscribed_products(
                                api_key, admin.email
                            )
                            if admin_subscriptions:
                                has_subscription = True
                                break
                    if has_subscription:
                        break

            # Cache the result in SharedCache
            shared_cache.set(cache_key, has_subscription, ttl=_stripe_check_cache_ttl)

            # Update user active status based on subscription
            if has_subscription:
                user = session.query(User).filter(User.id == user_id).first()
                if user and not user.is_active:
                    user.is_active = True
                    session.commit()
                    logging.debug(f"User {user_email} marked active via subscription")
        except Exception as e:
            logging.debug(f"Background Stripe check error: {e}")
        finally:
            session.close()

    def get_user_preferences(self):
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        user_preferences = (
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == self.user_id)
            .all()
        )
        user_preferences = {x.pref_key: x.pref_value for x in user_preferences}
        user_companies = (
            session.query(UserCompany).filter(UserCompany.user_id == self.user_id).all()
        )
        wallet_address = getenv("PAYMENT_WALLET_ADDRESS", "")

        # Determine if billing is enabled globally (token price > 0)
        price_service = PriceService()
        try:
            token_price = price_service.get_token_price()
        except Exception:
            # If pricing service fails for any reason, default to billing enabled
            token_price = 1
        billing_enabled = token_price > 0

        # Token billing is the primary (and only) billing model
        token_billing_enabled = token_price > 0

        # Wallet paywall is enabled when token billing is enabled and wallet address is set
        wallet_paywall_enabled = (
            bool(wallet_address)
            and str(wallet_address).lower() != "none"
            and token_billing_enabled
        )
        has_active_subscription = False
        user_requirements = self.registration_requirements()
        if not user_preferences:
            user_preferences = {}
        if "input_tokens" not in user_preferences:
            user_preferences["input_tokens"] = 0
        if "output_tokens" not in user_preferences:
            user_preferences["output_tokens"] = 0

        # Check if user has sufficient token balance when token billing is enabled
        # This is the primary billing check - don't skip it based on is_active
        has_sufficient_balance = False
        if wallet_paywall_enabled:
            has_sufficient_balance = self._has_sufficient_token_balance(
                session, user_companies
            )
            if not has_sufficient_balance:
                # User has no token balance and billing is enabled - enforce paywall
                user.is_active = False
                session.commit()
                session.close()
                logging.info(
                    f"{self.email} has insufficient token balance at {self.company_id}"
                )
                raise HTTPException(
                    status_code=402,
                    detail={
                        "message": f"Insufficient token balance. Please top up your tokens.",
                        "customer_session": {
                            "client_secret": None,
                            "company_id": self.company_id,
                        },
                        "wallet_address": wallet_address,
                        "token_price_per_million_usd": float(token_price),
                    },
                )

        # If user has sufficient token balance, mark as active
        has_active_subscription = has_sufficient_balance

        # Legacy: If user is already marked as active and we're not doing token billing, trust that status
        if not wallet_paywall_enabled and user.is_active:
            has_active_subscription = True

        if user.email != getenv("DEFAULT_USER"):
            api_key = getenv("STRIPE_API_KEY")
            billing_paused = getenv("BILLING_PAUSED", "false").lower() == "true"
            # Only proceed with Stripe checks if billing is not paused and we haven't already confirmed active subscription via token balance
            if (
                not billing_paused
                and not has_active_subscription
                and api_key != ""
                and api_key is not None
                and str(api_key).lower() != "none"
            ):
                import stripe

                stripe.api_key = api_key
                if not user.email.endswith(".xt"):
                    # Check if this user has their own subscription first
                    if "stripe_id" in user_preferences:
                        relevant_subscriptions = self.get_subscribed_products(
                            api_key, user.email
                        )
                        if relevant_subscriptions:
                            has_active_subscription = True

                    # Only check company subscriptions if the user doesn't have their own
                    if not has_active_subscription:
                        for user_company in user_companies:
                            # Get the company admins
                            company_admins = (
                                session.query(User)
                                .join(
                                    UserCompany, User.id == UserCompany.user_id
                                )  # Add proper JOIN
                                .filter(
                                    UserCompany.company_id == user_company.company_id
                                )
                                .filter(UserCompany.role_id <= 2)
                                .all()
                            )
                            for company_admin in company_admins:
                                company_admin_preferences = (
                                    session.query(UserPreferences)
                                    .filter(UserPreferences.user_id == company_admin.id)
                                    .all()
                                )
                                company_admin_preferences = {
                                    x.pref_key: x.pref_value
                                    for x in company_admin_preferences
                                }
                                if "stripe_id" in company_admin_preferences:
                                    # add to users preferences
                                    user_preferences["stripe_id"] = (
                                        company_admin_preferences["stripe_id"]
                                    )
                                    # check if it has an active subscription
                                    relevant_subscriptions = (
                                        self.get_subscribed_products(
                                            api_key,
                                            company_admin.email,
                                        )
                                    )
                                    if relevant_subscriptions:
                                        has_active_subscription = True
                                        break
                        if not has_active_subscription:
                            if (
                                "stripe_id" not in user_preferences
                                or not user_preferences["stripe_id"].startswith("cus_")
                            ):
                                # Only create Stripe customers / enforce paywall when billing is enabled
                                if billing_enabled:
                                    customer = stripe.Customer.create(email=user.email)
                                    user_preferences["stripe_id"] = customer.id
                                    user_preference = UserPreferences(
                                        user_id=self.user_id,
                                        pref_key="stripe_id",
                                        pref_value=customer.id,
                                    )
                                    session.add(user_preference)
                                    session.commit()
                                    raise HTTPException(
                                        status_code=402,
                                        detail={
                                            "message": "No active subscriptions.",
                                            "customer_id": customer.id,
                                        },
                                    )
                                else:
                                    logging.info(
                                        f"Subscription billing disabled; skipping subscription paywall for user {self.user_id}"
                                    )
                            else:
                                relevant_subscriptions = self.get_subscribed_products(
                                    api_key, user.email
                                )
                                if not relevant_subscriptions:
                                    logging.info(
                                        f"No active subscriptions for this app detected."
                                    )
                                    # Only enforce subscription locking when billing enabled
                                    if billing_enabled:
                                        if getenv("STRIPE_PRICING_TABLE_ID"):
                                            c_session = stripe.CustomerSession.create(
                                                customer=user_preferences["stripe_id"],
                                                components={
                                                    "pricing_table": {"enabled": True}
                                                },
                                            )
                                        else:
                                            c_session = ""

                                        user = (
                                            session.query(User)
                                            .filter(User.id == self.user_id)
                                            .first()
                                        )
                                        user.is_active = False
                                        session.commit()
                                        session.close()
                                        raise HTTPException(
                                            status_code=402,
                                            detail={
                                                "message": f"No active subscriptions.",
                                                "customer_session": c_session,
                                                "customer_id": user_preferences[
                                                    "stripe_id"
                                                ],
                                            },
                                        )
                                    else:
                                        logging.info(
                                            f"Subscription billing disabled; skipping subscription enforcement for user {self.user_id}"
                                        )
        if "email" in user_preferences:
            del user_preferences["email"]
        if "first_name" in user_preferences:
            del user_preferences["first_name"]
        if "last_name" in user_preferences:
            del user_preferences["last_name"]
        if "phone_number" not in user_preferences:
            user_preferences["phone_number"] = ""
        if "missing_requirements" in user_preferences:
            del user_preferences["missing_requirements"]
        missing_requirements = []
        if user_requirements:
            for key, value in user_requirements.items():
                if key not in user_preferences:
                    if key != "stripe_id":
                        missing_requirements.append({key: value})
        if "verify_email" not in user_preferences:
            if getenv("EMAIL_VERIFICATION_ENABLED").lower() == "true":
                missing_requirements.append({"verify_email": True})
                self.send_email_verification_link()
        else:
            del user_preferences["verify_email"]
        if missing_requirements:
            user_preferences["missing_requirements"] = missing_requirements
        if wallet_paywall_enabled:
            user_preferences.setdefault("wallet_address", wallet_address)
            user_preferences.setdefault(
                "token_price_per_million_usd", float(token_price)
            )
        session.close()
        return user_preferences

    def send_email_code(self):
        # Check if any email provider is configured
        if not is_email_configured():
            return False
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        if user is None:
            session.close()
            return False
        totp = pyotp.TOTP(user.mfa_token)
        code = totp.now()
        app_name = getenv("APP_NAME")
        try:
            email_send = send_email(
                email=self.email,
                subject=f"{app_name} Verification Code",
                body=f"This code expires in 60 seconds. Your verification code is: {code}",
            )
        except Exception as e:
            logging.error(f"Error sending email code: {str(e)}")
            session.close()
            return False
        if not email_send:
            session.close()
            return False
        session.close()
        return True

    def send_sms_code(self):
        """
        Send an SMS verification code to the user's phone number
        """
        if not getenv("TWILIO_ACCOUNT_SID") or not getenv("TWILIO_AUTH_TOKEN"):
            return False
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        if not user:
            session.close()
            return False
        user_preferences = (
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == user.id)
            .all()
        )
        try:
            # Check verify_sms to see if it is verified
            # Currently disabled until we implement UI for SMS verification
            # It will just try to send to a valid 10 digit phone number
            """
            verify_sms = next(
                (x for x in user_preferences if x.pref_key == "verify_sms"), None
            )
            if not verify_sms:
                return False
            """
            # Check if phone_number is in the preferences
            phone_number_preference = next(
                (x for x in user_preferences if x.pref_key == "phone_number"),
                None,
            )
            if phone_number_preference:
                if len(phone_number_preference.pref_value) < 10:
                    session.close()
                    return False
                # If it isn't a valid phone number, return False
                try:
                    int(phone_number_preference.pref_value)
                except:
                    session.close()
                    return False
                # Send SMS with the pyotp code
                totp = pyotp.TOTP(user.mfa_token)
                code = totp.now()
                from twilio.rest import Client  # type: ignore

                client = Client(
                    getenv("TWILIO_ACCOUNT_SID"), getenv("TWILIO_AUTH_TOKEN")
                )
                message = client.messages.create(
                    body=f"Your verification code is: {code}",
                    from_=getenv("TWILIO_PHONE_NUMBER"),
                    to=phone_number_preference.pref_value,
                )
                session.close()
                return True
        except Exception as e:
            logging.error(f"Error sending SMS code: {str(e)}")
            session.close()
            return False
        session.close()
        return False

    def verify_sms(self, code: str):
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        if not user:
            session.close()
            return False
        if not code:
            session.close()
            return False
        try:
            user_preferences = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == user.id)
                .filter(UserPreferences.pref_key == "sms_code")
                .first()
            )
            if user_preferences and user_preferences.pref_value == code:
                user_preferences = (
                    session.query(UserPreferences)
                    .filter(UserPreferences.user_id == user.id)
                    .filter(UserPreferences.pref_key == "verify_sms")
                    .first()
                )
                if not user_preferences:
                    user_preferences = UserPreferences(
                        user_id=user.id, pref_key="verify_sms", pref_value="True"
                    )
                    session.add(user_preferences)
                else:
                    user_preferences.pref_value = "True"
                session.commit()
                return True
        except Exception as e:
            logging.error(f"Error verifying SMS code: {str(e)}")
        finally:
            session.close()
        return False

    def send_email_verification_link(self):
        """
        Send a verification email to the user with a link to verify their email address.
        Uses the configured email provider (sendgrid, mailgun, microsoft, or google).
        Link will go to magic_link ?verify_email=Code associated with their account
        Just use the mfa_token encrypted with the user's email and the current date
        """
        # Get user's mfa token
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        if not user:
            session.close()
            return False
        # Check user preferences for verify_email
        user_preferences = (
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == user.id)
            .all()
        )
        found = False
        for preference in user_preferences:
            if preference.pref_key == "verify_email":
                # Check the date, if it's been less than 24 hours, don't send another email
                if preference.pref_value:
                    if str(preference.pref_value).lower() == "true":
                        session.close()
                        return True
                    if str(preference.pref_value).lower() != "false":
                        if datetime.now() - timedelta(
                            hours=24
                        ) < datetime.fromisoformat(preference.pref_value):
                            session.close()
                            return True
                    else:
                        # Update the date
                        preference.pref_value = str(datetime.now())
                        session.commit()
                        found = True
                        break
        if not found:
            # Add user preference for email verification as the current timestamp
            user_preference = UserPreferences(
                user_id=user.id,
                pref_key="verify_email",
                pref_value=str(datetime.now()),
            )
            session.add(user_preference)
            session.commit()
        encrypted_key = encrypt(f"{self.email}:{user.mfa_token}", user.mfa_token)
        # Make it url safe
        encrypted_key = (
            encrypted_key.replace("+", "%2B")
            .replace("/", "%2F")
            .replace("=", "%3D")
            .replace(" ", "%20")
            .replace(":", "%3A")
            .replace("?", "%3F")
            .replace("&", "%26")
            .replace("#", "%23")
            .replace(";", "%3B")
            .replace("@", "%40")
            .replace("!", "%21")
            .replace("$", "%24")
            .replace("'", "%27")
            .replace("(", "%28")
            .replace(")", "%29")
            .replace("*", "%2A")
            .replace(",", "%2C")
            .replace(";", "%3B")
            .replace("[", "%5B")
            .replace("]", "%5D")
            .replace("{", "%7B")
            .replace("}", "%7D")
            .replace("|", "%7C")
            .replace("\\", "%5C")
            .replace("^", "%5E")
            .replace("`", "%60")
            .replace("~", "%7E")
        )
        parsed_email = (
            self.email.replace("+", "%2B")
            .replace("/", "%2F")
            .replace("=", "%3D")
            .replace(" ", "%20")
            .replace(":", "%3A")
            .replace("?", "%3F")
            .replace("&", "%26")
            .replace("#", "%23")
            .replace(";", "%3B")
            .replace("@", "%40")
            .replace("!", "%21")
            .replace("$", "%24")
            .replace("'", "%27")
            .replace("(", "%28")
            .replace(")", "%29")
            .replace("*", "%2A")
            .replace(",", "%2C")
            .replace(";", "%3B")
            .replace("[", "%5B")
            .replace("]", "%5D")
            .replace("{", "%7B")
            .replace("}", "%7D")
            .replace("|", "%7C")
            .replace("\\", "%5C")
            .replace("^", "%5E")
            .replace("`", "%60")
            .replace("~", "%7E")
        )
        sent = send_email(
            email=self.email,
            subject="Verify your email address",
            body=f"Click the link below to verify your email address: <a href='{self.link}?verify_email={encrypted_key}&email={parsed_email}'>Verify Email</a>",
        )
        session.close()
        return sent

    def verify_email_address(self, code: str = None):
        """
        Set's the user's email to verified status
        """
        if not code:
            return False
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        if not user:
            session.close()
            return False
        code = (
            code.replace("%2B", "+")
            .replace("%2F", "/")
            .replace("%3D", "=")
            .replace("%20", " ")
            .replace("%3A", ":")
            .replace("%3F", "?")
            .replace("%26", "&")
            .replace("%23", "#")
            .replace("%3B", ";")
            .replace("%40", "@")
            .replace("%21", "!")
            .replace("%24", "$")
            .replace("%27", "'")
            .replace("%28", "(")
            .replace("%29", ")")
            .replace("%2A", "*")
            .replace("%2C", ",")
            .replace("%3B", ";")
            .replace("%5B", "[")
            .replace("%5D", "]")
            .replace("%7B", "{")
            .replace("%7D", "}")
            .replace("%7C", "|")
            .replace("%5C", "\\")
            .replace("%5E", "^")
            .replace("%60", "`")
            .replace("%7E", "~")
        )
        decrypted_code = decrypt(f"{self.email}:{user.mfa_token}", code)
        if decrypted_code != user.mfa_token:
            session.close()
            return False
        user_preferences = (
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == user.id)
            .all()
        )
        for preference in user_preferences:
            if preference.pref_key == "verify_email":
                preference.pref_value = "True"
                session.commit()
                session.close()
                return True
        # Create it if it doesn't exist and set it to True
        user_preference = UserPreferences(
            user_id=user.id,
            pref_key="verify_email",
            pref_value="True",
        )
        session.add(user_preference)
        session.commit()
        session.close()
        return True

    def verify_mfa(self, token: str):
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        if not user:
            session.close()
            return False
        if not token:
            session.close()
            return False
        try:
            is_valid = pyotp.TOTP(user.mfa_token).verify(token, valid_window=60)
            if is_valid:
                # Update verification status
                user_preferences = (
                    session.query(UserPreferences)
                    .filter(UserPreferences.user_id == user.id)
                    .filter(UserPreferences.pref_key == "verify_mfa")
                    .first()
                )
                if not user_preferences:
                    user_preferences = UserPreferences(
                        user_id=user.id, pref_key="verify_mfa", pref_value="True"
                    )
                    session.add(user_preferences)
                else:
                    user_preferences.pref_value = "True"
                session.commit()
                return True
        except Exception as e:
            logging.error(f"Error verifying MFA token: {str(e)}")
        finally:
            session.close()
        return False

    def reset_mfa(self):
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        if user:
            user.mfa_token = pyotp.random_base32()
            user_preferences = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == user.id)
                .filter(UserPreferences.pref_key == "verify_mfa")
                .first()
            )
            if user_preferences:
                user_preferences.pref_value = "False"
            session.commit()
        session.close()
        return "MFA has been reset."

    def get_decrypted_user_preferences(self):
        self.validate_user()
        user_preferences = self.get_user_preferences()
        if not user_preferences:
            return {}
        decrypted_preferences = {}
        for key, value in user_preferences.items():
            if (
                value != "password"
                and value != ""
                and value is not None
                and value != "string"
                and value != "text"
            ):
                if "password" in key.lower():
                    value = decrypt(self.encryption_key, value)
                elif "api_key" in key.lower():
                    value = decrypt(self.encryption_key, value)
                elif "_secret" in key.lower():
                    value = decrypt(self.encryption_key, value)
            decrypted_preferences[key] = value
        return decrypted_preferences

    def get_token_counts(self):
        session = get_session()
        user_preferences = (
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == self.user_id)
            .all()
        )
        input_tokens = 0
        output_tokens = 0
        found_input_tokens = False
        found_output_tokens = False
        for preference in user_preferences:
            if preference.pref_key == "input_tokens":
                input_tokens = int(preference.pref_value)
                found_input_tokens = True
            if preference.pref_key == "output_tokens":
                output_tokens = int(preference.pref_value)
                found_output_tokens = True
        if not found_input_tokens:
            user_preference = UserPreferences(
                user_id=self.user_id,
                pref_key="input_tokens",
                pref_value=str(input_tokens),
            )
            session.add(user_preference)
            session.commit()
        if not found_output_tokens:
            user_preference = UserPreferences(
                user_id=self.user_id,
                pref_key="output_tokens",
                pref_value=str(output_tokens),
            )
            session.add(user_preference)
            session.commit()
        session.close()
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}

    def get_root_parent_company(self, company_id: str, session=None) -> Optional[str]:
        """
        Get the root parent company ID by traversing the parent hierarchy.
        Child companies should consume tokens from their root parent company.

        Args:
            company_id: The company ID to start from
            session: Optional existing session to use

        Returns:
            The root parent company ID (company with no parent), or the original
            company_id if it's already a root company
        """
        close_session = False
        if session is None:
            session = get_session()
            close_session = True

        try:
            current_id = company_id
            visited = set()  # Prevent infinite loops

            while current_id:
                if current_id in visited:
                    # Circular reference detected, return current
                    logging.warning(
                        f"Circular parent reference detected for company {company_id}"
                    )
                    break
                visited.add(current_id)

                company = (
                    session.query(Company).filter(Company.id == current_id).first()
                )
                if not company:
                    break

                # company_id field is the parent company reference
                parent_id = company.company_id
                if not parent_id:
                    # This company has no parent, it's the root
                    return str(current_id)

                current_id = str(parent_id)

            return str(company_id)  # Fallback to original
        finally:
            if close_session:
                session.close()

    def increase_token_counts(self, input_tokens: int = 0, output_tokens: int = 0):
        self.validate_user()
        session = get_session()
        total_tokens = input_tokens + output_tokens

        try:
            # Check if billing is enabled
            price_service = PriceService()
            token_price = price_service.get_token_price()
            billing_enabled = token_price > 0

            # Get user's company
            user_company = (
                session.query(UserCompany)
                .filter(UserCompany.user_id == self.user_id)
                .first()
            )

            if user_company and billing_enabled:
                user_direct_company = (
                    session.query(Company)
                    .filter(Company.id == user_company.company_id)
                    .first()
                )

                if user_direct_company:
                    # Get the root parent company for billing purposes
                    # Child companies consume tokens from their root parent
                    root_company_id = self.get_root_parent_company(
                        str(user_direct_company.id), session=session
                    )

                    # If user's company is a child, get the root parent for billing
                    if str(root_company_id) != str(user_direct_company.id):
                        billing_company = (
                            session.query(Company)
                            .filter(Company.id == root_company_id)
                            .first()
                        )
                    else:
                        billing_company = user_direct_company

                    if billing_company:
                        # Check if billing company has sufficient balance
                        if billing_company.token_balance < total_tokens:
                            session.close()
                            raise HTTPException(
                                status_code=402,
                                detail="Insufficient token balance. Please top up your company's token balance.",
                            )

                        # Deduct from billing (root parent) company balance
                        billing_company.token_balance -= total_tokens
                        billing_company.tokens_used_total += total_tokens

                    # Record usage for audit trail (against user's direct company)
                    usage = CompanyTokenUsage(
                        company_id=user_direct_company.id,
                        user_id=self.user_id,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        total_tokens=total_tokens,
                    )
                    session.add(usage)

            # Still track per-user for analytics (existing logic)
            counts = self.get_token_counts()
            current_input_tokens = int(counts["input_tokens"])
            current_output_tokens = int(counts["output_tokens"])
            updated_input_tokens = current_input_tokens + input_tokens
            updated_output_tokens = current_output_tokens + output_tokens
            user_preferences = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == self.user_id)
                .all()
            )
            if not user_preferences:
                user_input_tokens = None
                user_output_tokens = None
            else:
                user_input_tokens = next(
                    (x for x in user_preferences if x.pref_key == "input_tokens"),
                    None,
                )
                user_output_tokens = next(
                    (x for x in user_preferences if x.pref_key == "output_tokens"),
                    None,
                )
            # Update input tokens
            if user_input_tokens is None:
                user_input_tokens = UserPreferences(
                    user_id=self.user_id,
                    pref_key="input_tokens",
                    pref_value=str(updated_input_tokens),
                )
                session.add(user_input_tokens)
            else:
                user_input_tokens.pref_value = str(updated_input_tokens)

            # Update output tokens
            if user_output_tokens is None:
                user_output_tokens = UserPreferences(
                    user_id=self.user_id,
                    pref_key="output_tokens",
                    pref_value=str(updated_output_tokens),
                )
                session.add(user_output_tokens)
            else:
                user_output_tokens.pref_value = str(updated_output_tokens)

            session.commit()
            return {
                "input_tokens": updated_input_tokens,
                "output_tokens": updated_output_tokens,
            }
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            logging.error(f"Error increasing token counts: {str(e)}")
            raise
        finally:
            session.close()

    def get_company_token_balance(self, company_id: str) -> dict:
        """Get company token balance and usage stats.

        For child companies, this also returns the parent company's balance info
        since child companies consume tokens from their root parent company.
        """
        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            low_balance_threshold = int(getenv("LOW_BALANCE_WARNING_THRESHOLD"))

            # Check if this is a child company (has a parent)
            root_company_id = self.get_root_parent_company(company_id, session=session)
            is_child_company = str(root_company_id) != str(company_id)

            result = {
                "token_balance": company.token_balance,
                "token_balance_usd": company.token_balance_usd,
                "tokens_used_total": company.tokens_used_total,
                "low_balance_warning": company.token_balance <= low_balance_threshold,
                "is_child_company": is_child_company,
            }

            # If this is a child company, include parent company balance info
            # since tokens are consumed from the parent
            if is_child_company:
                parent_company = (
                    session.query(Company).filter(Company.id == root_company_id).first()
                )
                if parent_company:
                    result["parent_company_id"] = str(root_company_id)
                    result["parent_company_name"] = parent_company.name
                    result["parent_token_balance"] = parent_company.token_balance
                    result["parent_token_balance_usd"] = (
                        parent_company.token_balance_usd
                    )
                    result["parent_tokens_used_total"] = (
                        parent_company.tokens_used_total
                    )
                    # Use parent's balance for the low balance warning since that's what's consumed
                    result["low_balance_warning"] = (
                        parent_company.token_balance <= low_balance_threshold
                    )

            return result
        finally:
            session.close()

    def should_show_low_balance_warning(self, company_id: str) -> bool:
        """Check if low balance warning should be shown to admin.

        For child companies, checks the root parent company's balance since
        that's where tokens are consumed from.
        """
        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                return False

            # Get the root parent company for billing purposes
            root_company_id = self.get_root_parent_company(company_id, session=session)
            if str(root_company_id) != str(company_id):
                billing_company = (
                    session.query(Company).filter(Company.id == root_company_id).first()
                )
                if not billing_company:
                    billing_company = company
            else:
                billing_company = company

            current_balance = billing_company.token_balance
            last_warning = billing_company.last_low_balance_warning or 0
            low_balance_threshold = int(getenv("LOW_BALANCE_WARNING_THRESHOLD"))
            warning_increment = int(getenv("TOKEN_WARNING_INCREMENT"))

            # Show warning if below threshold and dropped at least increment since last warning
            if (
                current_balance <= low_balance_threshold
                and (last_warning - current_balance) >= warning_increment
            ):
                return True
            return False
        finally:
            session.close()

    def dismiss_low_balance_warning(self, company_id: str):
        """Admin dismisses warning, record current balance.

        For child companies, updates the root parent company's warning state
        since that's where the balance is tracked.
        """
        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            # Get the root parent company for billing purposes
            root_company_id = self.get_root_parent_company(company_id, session=session)
            if str(root_company_id) != str(company_id):
                billing_company = (
                    session.query(Company).filter(Company.id == root_company_id).first()
                )
                if not billing_company:
                    billing_company = company
            else:
                billing_company = company

            billing_company.last_low_balance_warning = billing_company.token_balance
            session.commit()
        finally:
            session.close()

    def add_tokens_to_company(
        self, company_id: str, token_amount: int, amount_usd: float
    ):
        """Add tokens to company balance after successful payment"""
        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            company.token_balance += token_amount
            company.token_balance_usd += amount_usd
            session.commit()
        finally:
            session.close()

    def get_user_companies(self) -> List[str]:
        """Get list of company IDs that the user has access to"""
        session = get_session()
        user_companies = (
            session.query(UserCompany).filter(UserCompany.user_id == self.user_id).all()
        )
        response = [str(uc.company_id) for uc in user_companies]
        session.close()
        return response

    def get_accessible_company_ids(self, include_children: bool = True) -> List[str]:
        """
        Get list of all company IDs that the user has access to, including child companies
        where the user is an admin of the parent company.

        Args:
            include_children: If True, include child companies where user is admin of parent.

        Returns:
            List of company IDs the user can access.
        """
        # Start with direct company memberships
        direct_companies = self.get_user_companies()

        if not include_children:
            return direct_companies

        accessible = set(direct_companies)

        with get_session() as db:
            # For each company where user is admin (role_id <= 1), add all child companies
            admin_company_ids = []
            for company_id in direct_companies:
                user_company = (
                    db.query(UserCompany)
                    .filter(
                        UserCompany.user_id == self.user_id,
                        UserCompany.company_id == company_id,
                    )
                    .first()
                )
                # Role 0 = super admin, Role 1 = company admin
                if user_company and user_company.role_id <= 1:
                    admin_company_ids.append(company_id)

            # Get all child companies recursively for admin companies
            def get_child_companies(parent_id: str, visited: set) -> List[str]:
                if parent_id in visited:
                    return []
                visited.add(parent_id)

                children = (
                    db.query(Company).filter(Company.company_id == parent_id).all()
                )
                result = []
                for child in children:
                    child_id = str(child.id)
                    result.append(child_id)
                    # Recursively get grandchildren
                    result.extend(get_child_companies(child_id, visited))
                return result

            for admin_company_id in admin_company_ids:
                visited = set()
                child_ids = get_child_companies(admin_company_id, visited)
                accessible.update(child_ids)

        return list(accessible)

    def can_access_company(self, company_id: str) -> bool:
        """
        Check if the user can access a specific company.
        This includes direct membership OR being an admin of a parent company.

        Args:
            company_id: The company ID to check access for.

        Returns:
            True if user can access the company, False otherwise.
        """
        if company_id in self.get_user_companies():
            return True

        # Check if user is admin of any parent company in the hierarchy
        with get_session() as db:
            current_id = company_id
            visited = set()

            while current_id and current_id not in visited:
                visited.add(current_id)

                company = db.query(Company).filter(Company.id == current_id).first()
                if not company:
                    break

                parent_id = str(company.company_id) if company.company_id else None
                if not parent_id:
                    break

                # Check if user is admin of the parent company
                user_company = (
                    db.query(UserCompany)
                    .filter(
                        UserCompany.user_id == self.user_id,
                        UserCompany.company_id == parent_id,
                    )
                    .first()
                )
                if user_company and user_company.role_id <= 1:
                    return True

                current_id = parent_id

        return False

    def get_user_companies_with_roles(self) -> List[dict]:
        """
        Get list of company IDs that the user has access to.
        Optimized to use batch queries instead of N+1 pattern.
        """
        from Agent import get_agents_lightweight

        session = get_session()
        try:
            # Single query with JOIN to get user_companies and companies together
            user_companies = (
                session.query(UserCompany)
                .options(joinedload(UserCompany.company))
                .filter(UserCompany.user_id == self.user_id)
                .all()
            )

            if not user_companies:
                return []

            # Collect company IDs for batch agent query
            company_ids = [str(uc.company_id) for uc in user_companies]

            # Get default agent ID for this user
            default_agent_id = None
            try:
                pref = (
                    session.query(UserPreferences)
                    .filter(UserPreferences.user_id == self.user_id)
                    .filter(UserPreferences.pref_key == "agent_id")
                    .first()
                )
                if pref:
                    default_agent_id = str(pref.pref_value)
            except:
                pass

            # Get all agents for all companies in one batch query
            # Include commands to avoid separate /v1/agent/{id}/command calls from front end
            agents_by_company = get_agents_lightweight(
                user_id=str(self.user_id),
                company_ids=company_ids,
                default_agent_id=default_agent_id,
                include_commands=True,
            )

            response = []
            for uc in user_companies:
                company = uc.company
                if not company:
                    continue

                # Build company dict efficiently
                company_dict = {
                    "id": str(company.id),
                    "company_id": (
                        str(company.company_id) if company.company_id else None
                    ),
                    "name": company.name,
                    "agent_name": company.agent_name,
                    "status": company.status,
                    "address": company.address,
                    "phone_number": company.phone_number,
                    "email": company.email,
                    "website": company.website,
                    "city": company.city,
                    "state": company.state,
                    "zip_code": company.zip_code,
                    "country": company.country,
                    "notes": company.notes,
                    "user_limit": company.user_limit,
                    "token_balance": company.token_balance,
                    "token_balance_usd": company.token_balance_usd,
                    "tokens_used_total": company.tokens_used_total,
                    "role_id": uc.role_id,
                    "primary": str(company.id) == str(self.company_id),
                    "agents": agents_by_company.get(str(company.id), []),
                }
                response.append(company_dict)
            return response
        finally:
            session.close()

    def get_invitations(self, company_id=None):
        if not company_id:
            company_id = self.get_user_company_id()
        # Check if user can access this company (direct or via parent admin)
        if not self.can_access_company(str(company_id)):
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        with get_session() as db:
            invitations = (
                db.query(Invitation)
                .filter(Invitation.company_id == company_id)
                .filter(Invitation.is_accepted == False)
                .all()
            )
            response = []
            app_uri = getenv("APP_URI") or "http://localhost:3437"
            for invitation in invitations:
                # Get company name for the link
                company = (
                    db.query(Company)
                    .filter(Company.id == invitation.company_id)
                    .first()
                )
                company_name = company.name if company else ""
                company_encoded = (
                    urllib.parse.quote(company_name) if company_name else ""
                )
                invitation_link = f"{app_uri}?invitation_id={invitation.id}&email={invitation.email}&company={company_encoded}"
                response.append(
                    {
                        "id": str(invitation.id),
                        "email": invitation.email,
                        "company_id": str(invitation.company_id),
                        "role_id": invitation.role_id,
                        "inviter_id": str(invitation.inviter_id),
                        "created_at": invitation.created_at,
                        "is_accepted": invitation.is_accepted,
                        "invitation_link": invitation_link,
                    }
                )
            return response

    def delete_invitation(self, invitation_id: str):
        with get_session() as db:
            invitation = (
                db.query(Invitation).filter(Invitation.id == invitation_id).first()
            )
            if not invitation:
                raise HTTPException(status_code=404, detail="Invitation not found")
            # Check if user can access this company (direct or via parent admin)
            if not self.can_access_company(str(invitation.company_id)):
                raise HTTPException(
                    status_code=403,
                    detail="Unauthorized. Insufficient permissions.",
                )

            # Check if the invited user exists and is already part of the company
            user = db.query(User).filter(User.email == invitation.email).first()
            if user:
                # Remove user from company if they are part of it
                user_company = (
                    db.query(UserCompany)
                    .filter(UserCompany.user_id == user.id)
                    .filter(UserCompany.company_id == invitation.company_id)
                    .first()
                )
                if user_company:
                    db.delete(user_company)

            db.delete(invitation)
            db.commit()
            return "Invitation deleted successfully"

    def create_invitation(self, invitation: InvitationCreate) -> InvitationResponse:
        # Check if user can access the requested company (direct or via parent admin)
        if not self.can_access_company(str(invitation.company_id)):
            invitation.company_id = self.get_user_company_id()
        if getenv("STRIPE_API_KEY") != "":
            if not self.check_user_limit(invitation.company_id):
                raise HTTPException(
                    status_code=402,
                    detail="You've reached your user limit. Please upgrade your subscription.",
                )
        with get_session() as db:
            try:
                # Check if user has appropriate scope to create invitations
                # First check direct scope, then check if admin of parent company
                has_permission = self.has_scope("users:write", invitation.company_id)
                if not has_permission:
                    # Check if user is admin of a parent company
                    if str(invitation.company_id) not in self.get_user_companies():
                        # User doesn't have direct membership, check parent admin
                        has_permission = self.can_access_company(
                            str(invitation.company_id)
                        )

                if not has_permission:
                    raise HTTPException(
                        status_code=403,
                        detail="Unauthorized. Insufficient permissions.",
                    )
                if not invitation.role_id:
                    invitation.role_id = 3
                # Users can only invite users at or below their own role level
                user_role = self.get_user_role(invitation.company_id)
                if user_role is not None and int(invitation.role_id) < user_role:
                    raise HTTPException(
                        status_code=403,
                        detail="Unauthorized. Insufficient permissions.",
                    )
                # If the user exists, add them to the company with the desired role.
                user = (
                    db.query(User)
                    .filter(User.email == invitation.email)
                    .filter(User.is_active == True)
                    .first()
                )
                if user:
                    # check if this user is in this company already
                    user_company = (
                        db.query(UserCompany)
                        .filter(UserCompany.user_id == user.id)
                        .filter(UserCompany.company_id == invitation.company_id)
                        .first()
                    )
                    if user_company:
                        return InvitationResponse(
                            id="none",
                            invitation_link="none",
                            email=invitation.email,
                            company_id=str(invitation.company_id),
                            role_id=invitation.role_id,
                            inviter_id=str(self.user_id),
                            created_at=convert_time(
                                datetime.now(), user_id=self.user_id
                            ),
                            is_accepted=True,
                        )
                    user_company = UserCompany(
                        user_id=user.id,
                        company_id=invitation.company_id,
                        role_id=invitation.role_id,
                    )
                    db.add(user_company)
                    db.commit()
                    # Invalidate user company cache since company membership changed
                    invalidate_user_company_cache(str(user.id))
                    # send an email letting the user know they have been added to the company
                    company = (
                        db.query(Company)
                        .filter(Company.id == invitation.company_id)
                        .first()
                    )
                    company_name = company.name if company else "our platform"
                    company_id = company.id if company else None
                    default_agent = get_default_agent()
                    agixt = InternalClient()
                    agixt.login(
                        email=invitation.email, otp=pyotp.TOTP(user.mfa_token).now()
                    )
                    if company_id is not None:
                        default_agent["settings"]["company_id"] = str(
                            invitation.company_id
                        )
                    agixt.add_agent(
                        agent_name=company.agent_name,
                        settings=default_agent["settings"],
                        commands=default_agent["commands"],
                        training_urls=(
                            default_agent["training_urls"]
                            if "training_urls" in default_agent
                            else []
                        ),
                    )
                    app_uri = getenv("APP_URI")
                    app_name = getenv("APP_NAME")
                    email_send = send_email(
                        email=user.email,
                        subject=f"Added to {company_name} on {app_name}",
                        body=f"""
<h2>Added to {company_name} on {app_name}</h2>
<p>You have been added to {company_name} on {app_name}.</p>
<p>You can access the company by logging in to <a href="{app_uri}">{app_name}</a>.</p>

<p>You can access the company by logging in to {app_name}.</p>
""",
                    )
                    return InvitationResponse(
                        id="none",
                        invitation_link="none",
                        email=invitation.email,
                        company_id=str(invitation.company_id),
                        role_id=invitation.role_id,
                        inviter_id=str(self.user_id),
                        created_at=convert_time(datetime.now(), user_id=self.user_id),
                        is_accepted=True,
                    )
                # Check if invitation already exists
                existing_invitation = (
                    db.query(Invitation)
                    .filter(
                        Invitation.email == invitation.email,
                        Invitation.company_id == invitation.company_id,
                        Invitation.is_accepted == False,
                    )
                    .first()
                )

                if existing_invitation:
                    # Resend invitation email (unless skip_email is True)
                    if invitation.skip_email:
                        app_uri = getenv("APP_URI")
                        company = (
                            db.query(Company)
                            .filter(Company.id == invitation.company_id)
                            .first()
                        )
                        company_name = company.name if company else "our platform"
                        company_encoded = (
                            company_name.replace("+", "%2B")
                            .replace("/", "%2F")
                            .replace("=", "%3D")
                            .replace(" ", "%20")
                            .replace(":", "%3A")
                            .replace("?", "%3F")
                            .replace("&", "%26")
                            .replace("#", "%23")
                            .replace(";", "%3B")
                            .replace("@", "%40")
                        )
                        invitation_link = f"{app_uri}?invitation_id={existing_invitation.id}&email={existing_invitation.email}&company={company_encoded}"
                    else:
                        invitation_link = self.send_invitation_email(
                            existing_invitation
                        )
                    return InvitationResponse(
                        id=str(existing_invitation.id),
                        invitation_link=invitation_link,
                        email=existing_invitation.email,
                        company_id=str(existing_invitation.company_id),
                        role_id=existing_invitation.role_id,
                        inviter_id=str(existing_invitation.inviter_id),
                        created_at=convert_time(
                            existing_invitation.created_at, user_id=self.user_id
                        ),
                        is_accepted=existing_invitation.is_accepted,
                    )
                new_invitation = Invitation(
                    email=invitation.email.lower(),
                    company_id=invitation.company_id,
                    role_id=invitation.role_id,
                    inviter_id=self.user_id,
                )
                db.add(new_invitation)
                db.commit()
                db.refresh(new_invitation)

                # Send invitation email (unless skip_email is True)
                if invitation.skip_email:
                    app_uri = getenv("APP_URI")
                    company = (
                        db.query(Company)
                        .filter(Company.id == invitation.company_id)
                        .first()
                    )
                    company_name = company.name if company else "our platform"
                    company_encoded = (
                        company_name.replace("+", "%2B")
                        .replace("/", "%2F")
                        .replace("=", "%3D")
                        .replace(" ", "%20")
                        .replace(":", "%3A")
                        .replace("?", "%3F")
                        .replace("&", "%26")
                        .replace("#", "%23")
                        .replace(";", "%3B")
                        .replace("@", "%40")
                    )
                    invitation_link = f"{app_uri}?invitation_id={new_invitation.id}&email={new_invitation.email}&company={company_encoded}"
                else:
                    invitation_link = self.send_invitation_email(new_invitation)

                response = {
                    "id": str(new_invitation.id),
                    "invitation_link": invitation_link,
                    "email": new_invitation.email,
                    "company_id": str(new_invitation.company_id),
                    "role_id": new_invitation.role_id,
                    "inviter_id": str(new_invitation.inviter_id),
                    "created_at": convert_time(
                        new_invitation.created_at, user_id=self.user_id
                    ),
                    "is_accepted": new_invitation.is_accepted,
                }
                return InvitationResponse(**response)
            except SQLAlchemyError as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=str(e))

    def send_invitation_email(self, invitation: Invitation):
        with get_session() as db:
            company = (
                db.query(Company).filter(Company.id == invitation.company_id).first()
            )
            company_name = company.name if company else "our platform"
        app_uri = getenv("APP_URI")
        app_name = getenv("APP_NAME")
        company = (
            company_name.replace("+", "%2B")
            .replace("/", "%2F")
            .replace("=", "%3D")
            .replace(" ", "%20")
            .replace(":", "%3A")
            .replace("?", "%3F")
            .replace("&", "%26")
            .replace("#", "%23")
            .replace(";", "%3B")
            .replace("@", "%40")
            .replace("!", "%21")
            .replace("$", "%24")
            .replace("'", "%27")
            .replace("(", "%28")
            .replace(")", "%29")
            .replace("*", "%2A")
            .replace(",", "%2C")
            .replace(";", "%3B")
            .replace("[", "%5B")
            .replace("]", "%5D")
            .replace("{", "%7B")
            .replace("}", "%7D")
            .replace("|", "%7C")
            .replace("\\", "%5C")
            .replace("^", "%5E")
            .replace("`", "%60")
            .replace("~", "%7E")
        )
        invitation_link = f"{app_uri}?invitation_id={invitation.id}&email={invitation.email}&company={company}"
        email_send = send_email(
            email=invitation.email,
            subject=f"Invitation to join {company_name} on {app_name}",
            body=f"""
<h2>Invitation to join {company_name} on {app_name}</h2>
<p>You have been invited to join {company_name} on {app_name}.</p>
<p>Please click <a href="{invitation_link}">here</a> to accept the invitation and create your account.</p>
<p>This invitation link will expire once used.</p>
<p>If you did not expect this invitation, please ignore this email.</p>""",
        )
        return invitation_link

    def get_users_agent(self, user_id: str):
        session = get_session()
        user_preferences = (
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == user_id)
            .filter(UserPreferences.pref_key == "agent_name")
            .first()
        )
        if user_preferences and user_preferences.pref_value:
            return user_preferences.pref_value
        return getenv("AGENT_NAME")

    def accept_invitation(self, invitation_id: str) -> bool:
        with get_session() as db:
            try:
                invitation = (
                    db.query(Invitation).filter(Invitation.id == invitation_id).first()
                )
                if not invitation:
                    raise HTTPException(status_code=404, detail="Invitation not found")

                if invitation.is_accepted:
                    raise HTTPException(
                        status_code=400, detail="Invitation already accepted"
                    )

                invitation.is_accepted = True
                user_company = UserCompany(
                    user_id=self.user_id,
                    company_id=invitation.company_id,
                    role_id=invitation.role_id,
                )
                db.add(user_company)
                db.commit()
                # Invalidate user company cache since company membership changed
                invalidate_user_company_cache(str(self.user_id))
                return True
            except SQLAlchemyError as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=str(e))

    def get_user_company_id(self):
        # Check cache first
        if self.user_id:
            cached = get_user_company_cached(str(self.user_id))
            if cached is not None:
                return cached if cached != "__NONE__" else None
        try:
            with get_session() as db:
                user_company = (
                    db.query(UserCompany)
                    .filter(UserCompany.user_id == self.user_id)
                    .first()
                )
                if user_company and user_company.company_id is not None:
                    company_id_str = str(user_company.company_id)
                    # Don't return "None" string
                    if company_id_str.lower() in ["none", "null", ""]:
                        if self.user_id:
                            set_user_company_cache(str(self.user_id), "__NONE__")
                        return None
                    if self.user_id:
                        set_user_company_cache(str(self.user_id), company_id_str)
                    return company_id_str
                if self.user_id:
                    set_user_company_cache(str(self.user_id), "__NONE__")
                return None
        except Exception as e:
            return None

    def get_user_company(self, company_id):
        # Validate company_id before querying
        if not company_id or str(company_id).lower() in ["none", "null", ""]:
            return None

        with get_session() as db:
            # Make sure the company ID is in the list of users companies
            user_company = (
                db.query(UserCompany)
                .filter(UserCompany.user_id == self.user_id)
                .filter(UserCompany.company_id == company_id)
                .first()
            )
            if not user_company:
                return None
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                return None
            company_dict = company.__dict__
            company_dict.pop("_sa_instance_state")
            return company_dict

    def get_user_tenant_id(self):
        with get_session() as db:
            user_company = (
                db.query(UserCompany)
                .filter(UserCompany.user_id == self.user_id)
                .first()
            )
            return str(user_company.company_id) if user_company else None

    def get_user_role(self, company_id: str = None) -> int:
        if company_id is None:
            company_id = self.get_user_company_id()
        with get_session() as db:
            user_company = (
                db.query(UserCompany)
                .filter(
                    UserCompany.user_id == self.user_id,
                    UserCompany.company_id == company_id,
                )
                .first()
            )
            if user_company:
                return user_company.role_id

            # If no direct membership, check if user is admin of a parent company
            # Admin of parent company gets the same role in child companies
            current_id = company_id
            visited = set()

            while current_id and current_id not in visited:
                visited.add(current_id)

                company = db.query(Company).filter(Company.id == current_id).first()
                if not company:
                    break

                parent_id = str(company.company_id) if company.company_id else None
                if not parent_id:
                    break

                # Check if user is admin of the parent company
                parent_user_company = (
                    db.query(UserCompany)
                    .filter(
                        UserCompany.user_id == self.user_id,
                        UserCompany.company_id == parent_id,
                    )
                    .first()
                )
                if parent_user_company and parent_user_company.role_id <= 1:
                    return parent_user_company.role_id

                current_id = parent_id

            return None

    def convert_uuid_to_str(self, obj):
        if isinstance(obj, dict):
            return {k: self.convert_uuid_to_str(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_uuid_to_str(item) for item in obj]
        elif isinstance(obj, uuid.UUID):
            return str(obj)
        else:
            return obj

    def get_markdown_companies(self) -> str:
        """
                Similar to get_all_companies, we want to make a function that will get company names, ids, and any child companies names and IDs for the authenticated user. We'll want it to return in string format like:

        "The user has {len(companies including children}), they are as following:
        | Company ID | Company Name | Parent Company ID |"
        """
        self.validate_user()

        companies = self.get_all_companies()
        flattened_companies = []
        seen_company_ids = set()

        for company in companies:
            company_id_raw = company.get("id")
            company_id_value = str(company_id_raw) if company_id_raw is not None else ""
            if company_id_value not in seen_company_ids:
                parent_id_raw = company.get("company_id")
                parent_id_value = (
                    str(parent_id_raw) if parent_id_raw not in [None, ""] else "none"
                )
                flattened_companies.append(
                    {
                        "id": company_id_value,
                        "name": company.get("name", ""),
                        "parent_id": parent_id_value,
                    }
                )
                seen_company_ids.add(company_id_value)

            for child in company.get("children", []) or []:
                child_id_raw = child.get("id")
                child_id_value = str(child_id_raw) if child_id_raw is not None else ""
                if child_id_value in seen_company_ids:
                    continue
                child_parent_raw = child.get("company_id")
                child_parent_value = (
                    str(child_parent_raw)
                    if child_parent_raw not in [None, ""]
                    else "none"
                )
                flattened_companies.append(
                    {
                        "id": child_id_value,
                        "name": child.get("name", ""),
                        "parent_id": child_parent_value,
                    }
                )
                seen_company_ids.add(child_id_value)

        total_companies = len(flattened_companies)

        header_line = (
            f"The user has {total_companies} companies, they are as following:"
        )

        table_lines = [
            "| Company ID | Company Name | Parent Company ID |",
            "| --- | --- | --- |",
        ]

        for company in flattened_companies:
            company_id = str(company["id"]) if company["id"] is not None else ""
            company_name = str(company["name"]) if company["name"] is not None else ""
            parent_id = (
                str(company["parent_id"]) if company["parent_id"] is not None else ""
            )

            company_id = company_id.replace("|", "\\|")
            company_name = company_name.replace("|", "\\|")
            parent_id = parent_id.replace("|", "\\|")

            table_lines.append(f"| {company_id} | {company_name} | {parent_id} |")

        return "\n".join([header_line, *table_lines])

    def get_all_companies(self) -> List[CompanyResponse]:
        """
        Get all companies accessible to the current user with proper deduplication of users.

        Returns:
            List[CompanyResponse]: List of companies with their associated users
        """
        with get_session() as db:
            try:
                # Get all companies the user has access to
                user_companies = (
                    db.query(Company)
                    .join(UserCompany)
                    .filter(UserCompany.user_id == self.user_id)
                    .options(
                        joinedload(Company.users).joinedload(UserCompany.user),
                        joinedload(Company.users).joinedload(UserCompany.role),
                    )
                    .all()
                )
                result = []
                for company in user_companies:
                    # Use dictionary for deduplication based on user ID
                    unique_users = {}
                    # Check if user has permission to read users for this company
                    can_read_users = self.has_scope("users:read", str(company.id))
                    if can_read_users:
                        for user_company in company.users:
                            role_name = None
                            for role in default_roles:
                                if role["id"] == user_company.role_id:
                                    role_name = role["name"]
                                    break
                            if role_name is None:
                                role_name = "user"
                            user = user_company.user
                            user_id = str(user.id)
                            # Show inactive users with "Inactive" role so admins can manage them
                            display_role = role_name if user.is_active else "Inactive"
                            display_role_id = (
                                user_company.role_id if user.is_active else 0
                            )
                            if user_id not in unique_users:
                                unique_users[user_id] = UserResponse(
                                    id=user_id,
                                    email=user.email,
                                    first_name=user.first_name,
                                    last_name=user.last_name,
                                    role=display_role,
                                    role_id=display_role_id,
                                )

                    company_data = {
                        "id": str(company.id),
                        "name": company.name,
                        "company_id": (
                            str(company.company_id) if company.company_id else None
                        ),
                        "status": getattr(company, "status", True),
                        "address": getattr(company, "address", None),
                        "phone_number": getattr(company, "phone_number", None),
                        "email": getattr(company, "email", None),
                        "website": getattr(company, "website", None),
                        "city": getattr(company, "city", None),
                        "state": getattr(company, "state", None),
                        "zip_code": getattr(company, "zip_code", None),
                        "country": getattr(company, "country", None),
                        "notes": getattr(company, "notes", None),
                        "users": list(unique_users.values()),
                        "children": [],
                    }

                    # Handle child companies
                    if not company.company_id:  # This is a parent company
                        child_companies = (
                            db.query(Company)
                            .filter(Company.company_id == company.id)
                            .options(
                                joinedload(Company.users).joinedload(UserCompany.user),
                                joinedload(Company.users).joinedload(UserCompany.role),
                            )
                            .all()
                        )

                        for child in child_companies:
                            # Deduplicate users for child company
                            child_unique_users = {}
                            for user_company in child.users:
                                role_name = None
                                for role in default_roles:
                                    if role["id"] == user_company.role_id:
                                        role_name = role["name"]
                                        break
                                if role_name is None:
                                    role_name = "user"
                                user = user_company.user
                                user_id = str(user.id)
                                # Show inactive users with "Inactive" role so admins can manage them
                                display_role = (
                                    role_name if user.is_active else "Inactive"
                                )
                                display_role_id = (
                                    user_company.role_id if user.is_active else 0
                                )
                                if user_id not in child_unique_users:
                                    child_unique_users[user_id] = UserResponse(
                                        id=user_id,
                                        email=user.email,
                                        first_name=user.first_name,
                                        last_name=user.last_name,
                                        role=display_role,
                                        role_id=display_role_id,
                                    )

                            child_data = {
                                "id": str(child.id),
                                "name": child.name,
                                "company_id": str(child.company_id),
                                "status": getattr(child, "status", True),
                                "address": getattr(child, "address", None),
                                "phone_number": getattr(child, "phone_number", None),
                                "email": getattr(child, "email", None),
                                "website": getattr(child, "website", None),
                                "city": getattr(child, "city", None),
                                "state": getattr(child, "state", None),
                                "zip_code": getattr(child, "zip_code", None),
                                "country": getattr(child, "country", None),
                                "notes": getattr(child, "notes", None),
                                "users": list(child_unique_users.values()),
                            }
                            company_data["children"].append(child_data)

                    result.append(company_data)

                # Convert all UUID objects to strings
                return self.convert_uuid_to_str(result)

            except Exception as e:
                logging.error(f"Error in get_all_companies: {str(e)}")
                logging.error(traceback.format_exc())
                raise HTTPException(
                    status_code=500,
                    detail=f"An error occurred while fetching companies: {str(e)}",
                )

    def get_all_server_companies(
        self,
        search: str = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = None,
        sort_direction: str = "asc",
        filter_balance: str = None,
        filter_users: str = None,
    ) -> dict:
        """
        Get all companies on the server (super admin only).
        Supports search by company name, company ID, or user email.

        Args:
            search: Optional search string (company name, ID, or user email)
            limit: Maximum number of results to return (default 100)
            offset: Number of results to skip for pagination (default 0)
            sort_by: Field to sort by (name, token_balance, token_balance_usd, user_count)
            sort_direction: Sort direction (asc or desc)
            filter_balance: Filter by balance (no_balance, has_balance)
            filter_users: Filter by user count (single_user, multiple_users)

        Returns:
            dict: Contains companies list and total count
        """
        self.validate_user()

        if not self.is_super_admin():
            raise HTTPException(
                status_code=403,
                detail="Access denied. Super admin role required.",
            )

        with get_session() as db:
            try:
                from sqlalchemy import or_, func, cast, String, desc, asc

                # Base query for all companies
                query = db.query(Company).options(
                    joinedload(Company.users).joinedload(UserCompany.user),
                    joinedload(Company.users).joinedload(UserCompany.role),
                )

                # If search is provided, filter by name, ID, or user email
                if search and search.strip():
                    search_term = f"%{search.strip().lower()}%"

                    # Find company IDs that have users matching the email search
                    user_company_ids = (
                        db.query(UserCompany.company_id)
                        .join(User)
                        .filter(func.lower(User.email).like(search_term))
                        .distinct()
                        .all()
                    )
                    user_company_ids = [uc[0] for uc in user_company_ids]

                    # Build search conditions
                    search_conditions = [
                        func.lower(Company.name).like(search_term),
                        func.lower(cast(Company.id, String)).like(search_term),
                    ]
                    if user_company_ids:
                        search_conditions.append(Company.id.in_(user_company_ids))

                    query = query.filter(or_(*search_conditions))

                # Apply balance filter
                if filter_balance == "no_balance":
                    query = query.filter(
                        or_(
                            Company.token_balance == None,
                            Company.token_balance == 0,
                            Company.token_balance_usd == None,
                            Company.token_balance_usd == 0,
                        )
                    )
                elif filter_balance == "has_balance":
                    query = query.filter(
                        Company.token_balance > 0,
                        Company.token_balance_usd > 0,
                    )

                # For user count filtering and sorting, we need a subquery
                user_count_subquery = (
                    db.query(
                        UserCompany.company_id,
                        func.count(UserCompany.user_id).label("user_count"),
                    )
                    .group_by(UserCompany.company_id)
                    .subquery()
                )

                # Apply user count filter if specified
                if filter_users in ["single_user", "multiple_users"]:
                    query = query.outerjoin(
                        user_count_subquery,
                        Company.id == user_count_subquery.c.company_id,
                    )
                    if filter_users == "single_user":
                        query = query.filter(
                            or_(
                                user_count_subquery.c.user_count == 1,
                                user_count_subquery.c.user_count == None,
                            )
                        )
                    elif filter_users == "multiple_users":
                        query = query.filter(user_count_subquery.c.user_count > 1)

                # Get total count before pagination
                total_count = query.count()

                # Determine sort order
                sort_func = desc if sort_direction == "desc" else asc
                if sort_by == "token_balance":
                    query = query.order_by(sort_func(Company.token_balance))
                elif sort_by == "token_balance_usd":
                    query = query.order_by(sort_func(Company.token_balance_usd))
                elif sort_by == "user_count":
                    # Join user count subquery if not already joined
                    if filter_users not in ["single_user", "multiple_users"]:
                        query = query.outerjoin(
                            user_count_subquery,
                            Company.id == user_count_subquery.c.company_id,
                        )
                    query = query.order_by(
                        sort_func(func.coalesce(user_count_subquery.c.user_count, 0))
                    )
                else:
                    # Default sort by name
                    query = query.order_by(sort_func(Company.name))

                # Apply pagination
                companies = query.offset(offset).limit(limit).all()

                result = []
                for company in companies:
                    # Collect users for this company
                    unique_users = {}
                    for user_company in company.users:
                        role_name = None
                        for role in default_roles:
                            if role["id"] == user_company.role_id:
                                role_name = role["name"]
                                break
                        if role_name is None:
                            role_name = "user"
                        user = user_company.user
                        user_id = str(user.id)
                        if user_id not in unique_users:
                            unique_users[user_id] = UserResponse(
                                id=user_id,
                                email=user.email,
                                first_name=user.first_name,
                                last_name=user.last_name,
                                role=role_name,
                                role_id=user_company.role_id,
                            )

                    company_data = {
                        "id": str(company.id),
                        "name": company.name,
                        "company_id": (
                            str(company.company_id) if company.company_id else None
                        ),
                        "status": getattr(company, "status", True),
                        "is_suspended": not getattr(company, "status", True),
                        "address": getattr(company, "address", None),
                        "phone_number": getattr(company, "phone_number", None),
                        "email": getattr(company, "email", None),
                        "website": getattr(company, "website", None),
                        "city": getattr(company, "city", None),
                        "state": getattr(company, "state", None),
                        "zip_code": getattr(company, "zip_code", None),
                        "country": getattr(company, "country", None),
                        "notes": getattr(company, "notes", None),
                        "token_balance": getattr(company, "token_balance", 0),
                        "token_balance_usd": getattr(company, "token_balance_usd", 0),
                        "users": list(unique_users.values()),
                        "children": [],
                    }
                    result.append(company_data)

                return {
                    "companies": self.convert_uuid_to_str(result),
                    "total": total_count,
                    "limit": limit,
                    "offset": offset,
                }

            except HTTPException:
                raise
            except Exception as e:
                logging.error(f"Error in get_all_server_companies: {str(e)}")
                logging.error(traceback.format_exc())
                raise HTTPException(
                    status_code=500,
                    detail=f"An error occurred while fetching companies: {str(e)}",
                )

    def verify_company_access(self, company_id: str) -> bool:
        """Verify if the current user has access to the specified company."""
        with get_session() as db:
            # Get all companies the user has access to (including parent/child relationships)
            user_companies = (
                db.query(UserCompany).filter(UserCompany.user_id == self.user_id).all()
            )

            allowed_company_ids = set()
            for uc in user_companies:
                allowed_company_ids.add(str(uc.company_id))
                # If user is admin or company_admin of a parent company,
                # add all child company IDs
                if uc.role_id <= 2:  # tenant_admin or company_admin
                    child_companies = (
                        db.query(Company)
                        .filter(Company.company_id == uc.company_id)
                        .all()
                    )
                    allowed_company_ids.update(str(c.id) for c in child_companies)

            return str(company_id) in allowed_company_ids

    def create_company(
        self,
        name: str,
        parent_company_id: Optional[str] = None,
        agent_name: str = None,
        status: bool = True,
        address: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        website: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
        country: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        """
        Create a new company. Company admins can only create child companies
        under their own company (or a company they have admin access to).
        Only super admins (role_id=0 or 1) can create top-level companies
        without a parent.

        For per_location billing (UltraEstimate), checks location limit before
        allowing child company creation.
        """
        if not agent_name:
            agent_name = getenv("AGENT_NAME")
        with get_session() as db:
            try:
                # Get user's primary company and role
                user_company = (
                    db.query(UserCompany)
                    .filter(UserCompany.user_id == self.user_id)
                    .order_by(UserCompany.role_id)  # Get highest privilege first
                    .first()
                )

                # Determine if user is a super admin (role_id 0 or 1)
                is_super_admin = user_company and user_company.role_id <= 1

                # Check if this is the user's first company (registration flow)
                # If user has no companies, allow them to create a top-level company
                is_first_company = user_company is None

                # If not super admin and no parent specified, force parent to user's company
                # This ensures company admins always create child companies
                # EXCEPTION: Allow first company creation during registration
                if (
                    not is_super_admin
                    and not parent_company_id
                    and not is_first_company
                ):
                    if user_company:
                        parent_company_id = str(user_company.company_id)
                        logging.info(
                            f"Auto-setting parent_company_id to {parent_company_id} "
                            f"for non-super admin user {self.user_id}"
                        )

                # Validate parent company access if specified
                if parent_company_id:
                    # Check if user has admin access to the parent company
                    parent_access = (
                        db.query(UserCompany)
                        .filter(
                            UserCompany.user_id == self.user_id,
                            UserCompany.company_id == parent_company_id,
                            UserCompany.role_id
                            <= 2,  # tenant_admin, super_admin, or company_admin
                        )
                        .first()
                    )
                    if not parent_access and not is_super_admin:
                        raise HTTPException(
                            status_code=403,
                            detail="You do not have permission to create child companies under this parent.",
                        )

                    # For per_location billing, check location limit before creating child company
                    from ExtensionsHub import ExtensionsHub

                    hub = ExtensionsHub()
                    pricing_config = hub.get_pricing_config()
                    pricing_model = (
                        pricing_config.get("pricing_model")
                        if pricing_config
                        else "per_token"
                    )

                    if pricing_model == "per_location":
                        # Get root parent company for billing
                        root_company_id = self.get_root_parent_company(
                            parent_company_id, session=db
                        )
                        billing_company = (
                            db.query(Company)
                            .filter(Company.id == root_company_id)
                            .first()
                        )

                        if billing_company:
                            paid_locations = billing_company.user_limit or 0
                            # Count existing child companies under root
                            child_company_count = (
                                db.query(Company)
                                .filter(Company.company_id == billing_company.id)
                                .count()
                            )
                            # Root + existing children + 1 for the new company
                            total_after_creation = child_company_count + 2

                            # Check if adding another location exceeds limit
                            if total_after_creation > paid_locations:
                                # Check fallback to token balance
                                if not (
                                    billing_company.token_balance
                                    and billing_company.token_balance > 0
                                ):
                                    raise HTTPException(
                                        status_code=402,
                                        detail=f"Location limit reached. You have {paid_locations} paid locations. "
                                        f"Please upgrade your plan to add more locations.",
                                    )

                # Check if user has permission to create companies
                if self.company_id != None:
                    check_company_id = (
                        parent_company_id if parent_company_id else self.company_id
                    )
                    if not self.has_scope("company:write", check_company_id):
                        raise HTTPException(
                            status_code=403,
                            detail="Unauthorized. Insufficient permissions.",
                        )

                new_company = Company.create(
                    db,
                    name=name,
                    company_id=parent_company_id,
                    agent_name=agent_name,
                    status=status,
                    address=address,
                    phone_number=phone_number,
                    email=email,
                    website=website,
                    city=city,
                    state=state,
                    zip_code=zip_code,
                    country=country,
                    notes=notes,
                )
                db.add(new_company)
                db.commit()

                user_company = UserCompany(
                    user_id=self.user_id,
                    company_id=new_company.id,
                    role_id=2,  # Set as company_admin
                )
                db.add(user_company)
                db.commit()
                # Check if this user should be promoted to super admin
                promote_superadmin_if_needed(
                    session=db,
                    user_id=str(self.user_id),
                    email=self.email,
                    company_id=str(new_company.id),
                )
                # Invalidate user company cache since company membership changed
                invalidate_user_company_cache(str(self.user_id))

                # Create company XT API user inline (avoid separate MagicalAuth instance)
                company_email = f"{str(new_company.id)}@{str(new_company.id)}.xt"
                mfa_token = pyotp.random_base32()
                company_user = User(
                    email=company_email,
                    first_name="XT",
                    last_name="API",
                    mfa_token=mfa_token,
                    is_active=True,
                )
                db.add(company_user)
                new_company.token = mfa_token
                db.commit()

                # Create company-level agent with direct InternalClient setup
                agixt = InternalClient(api_key=None, user=company_email)
                # Set user directly to avoid login overhead - we just need to create the agent
                agixt._user = company_email
                default_agent = get_default_agent()
                agixt.add_agent(
                    agent_name=agent_name,
                    settings=default_agent.get("settings", {}),
                    commands=default_agent.get("commands", {}),
                    training_urls=default_agent.get("training_urls", []),
                )
                response = {
                    "id": str(new_company.id),
                    "name": new_company.name,
                    "_default_agent": default_agent,  # Pass to caller to avoid redundant call
                }
                return response
            except SQLAlchemyError as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=str(e))

    def create_company_with_agent(
        self,
        name: str,
        parent_company_id: Optional[str] = None,
        agent_name: str = None,
        status: bool = True,
        address: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        website: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
        country: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        if not agent_name:
            agent_name = getenv("AGENT_NAME")
        company = self.create_company(
            name=name,
            parent_company_id=parent_company_id,
            agent_name=agent_name,
            status=status,
            address=address,
            phone_number=phone_number,
            email=email,
            website=website,
            city=city,
            state=state,
            zip_code=zip_code,
            country=country,
            notes=notes,
        )

        # Create user-level agent - reuse default_agent from create_company to avoid redundant call
        default_agent = company.pop("_default_agent", None) or get_default_agent()
        default_agent["settings"]["company_id"] = company["id"]

        # Use direct InternalClient setup to avoid login overhead
        agixt = InternalClient(api_key=None, user=self.email)
        agixt._user = self.email
        agixt.add_agent(
            agent_name=agent_name,
            settings=default_agent["settings"],
            commands=default_agent["commands"],
            training_urls=default_agent.get("training_urls", []),
        )
        return company

    def get_company_agent_name(self):
        """Get the agent name associated with the company."""
        with get_session() as db:
            company = db.query(Company).filter(Company.id == self.company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            return company.agent_name if company.agent_name else getenv("AGENT_NAME")

    def update_company(self, company_id: str, name: str) -> CompanyResponse:
        # Check if user has permission to write to this company
        if not self.has_scope("company:write", company_id):
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )

        with get_session() as db:
            try:
                company = db.query(Company).filter(Company.id == company_id).first()
                if not company:
                    raise HTTPException(status_code=404, detail="Company not found")

                company.name = name
                db.commit()
                user_role = self.get_user_role(company_id)
                role_name = None
                for role in default_roles:
                    if role["id"] == user_role:
                        role_name = role["name"]
                        break
                if role_name is None:
                    role_name = "user"

                return CompanyResponse(
                    id=str(company.id),
                    name=company.name,
                    company_id=str(company.company_id) if company.company_id else None,
                    status=getattr(company, "status", True),
                    address=getattr(company, "address", None),
                    phone_number=getattr(company, "phone_number", None),
                    email=getattr(company, "email", None),
                    website=getattr(company, "website", None),
                    city=getattr(company, "city", None),
                    state=getattr(company, "state", None),
                    zip_code=getattr(company, "zip_code", None),
                    country=getattr(company, "country", None),
                    notes=getattr(company, "notes", None),
                    users=[
                        UserResponse(
                            id=str(uc.user.id),
                            email=uc.user.email,
                            first_name=uc.user.first_name,
                            last_name=uc.user.last_name,
                            role=role_name,
                            role_id=uc.role_id,
                        )
                        for uc in company.users
                    ],
                    children=[],
                )
            except SQLAlchemyError as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=str(e))

    def get_training_data(self, company_id: str = None) -> str:
        if not company_id:
            company_id = self.company_id
        if str(company_id) not in self.get_user_companies():
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        with get_session() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            return str(company.training_data)

    def set_training_data(self, training_data: str, company_id: str = None) -> str:
        if not company_id:
            company_id = self.company_id
        # Check if user has permission to write to this company
        if not self.has_scope("company:write", company_id):
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        with get_session() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            company.training_data = training_data
            db.commit()
            return training_data

    def get_user_by_id(self, session, user_id):
        """Get a user by ID from the database"""
        try:
            user = session.query(User).filter(User.id == user_id).first()
            return user
        except Exception as e:
            logging.error(f"Error getting user by ID {user_id}: {str(e)}")
            return None

    def get_user_agent_session(self) -> InternalClient:
        session = get_session()
        user_details = session.query(User).filter(User.id == self.user_id).first()
        if not user_details:
            session.close()
            raise HTTPException(status_code=401, detail="Invalid user login")
        agixt = InternalClient()
        agixt.login(
            email=user_details.email, otp=pyotp.TOTP(user_details.mfa_token).now()
        )
        session.close()
        return agixt

    def get_company_agent_session(self, company_id: str = None) -> InternalClient:
        # Handle None, "None" string, or empty string
        if not company_id or str(company_id).lower() in ["none", "null", ""]:
            company_id = self.company_id
        # If still no valid company_id, return None
        if not company_id or str(company_id).lower() in ["none", "null", ""]:
            return None
        company = self.get_user_company(company_id)
        if not company:
            return None
        # Check if company_id is in the users companies
        if str(company_id) not in self.get_user_companies():
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        agixt = InternalClient()
        totp = pyotp.TOTP(str(company["token"]))
        agixt.login(email=f"{company_id}@{company_id}.xt", otp=totp.now())
        return agixt

    def sso(
        self,
        code,
        ip_address,
        provider="microsoft",
        referrer=None,
        invitation_id=None,
        code_verifier=None,
    ):
        if not referrer:
            app_uri = getenv("APP_URI")
            referrer = f"{app_uri}/user/close/{provider}"
        # Check if one of the providers in the extensions folder using recursive discovery
        provider = str(provider).lower()
        extension_files = find_extension_files()
        provider_found = False
        for extension_file in extension_files:
            if os.path.basename(extension_file).replace(".py", "") == provider:
                provider_found = True
                break
        if not provider_found:
            provider = "microsoft"
        sso_data = get_sso_provider(
            provider=provider,
            code=code,
            redirect_uri=referrer,
            code_verifier=code_verifier,
        )
        if not sso_data:
            logging.error(f"Failed to get user data from {provider.capitalize()}.")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to get user data from {provider.capitalize()}.",
            )
        if not sso_data.access_token:
            logging.error(f"Failed to get access token from {provider.capitalize()}.")
            logging.error(f"SSO Data: {sso_data}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to get access token from {provider.capitalize()}.",
            )

        user_data = sso_data.user_info
        access_token = sso_data.access_token
        refresh_token = sso_data.refresh_token
        token_expires_at = (
            datetime.now() + timedelta(seconds=sso_data.expires_in)
            if hasattr(sso_data, "expires_in")
            else None
        )
        account_name = sso_data.user_info.get("email", self.email)

        if not account_name:
            logging.error(
                f"Could not get account identifier from {provider.capitalize()} response."
            )
            raise HTTPException(
                status_code=400,
                detail=f"Could not get account identifier from {provider.capitalize()} response.",
            )

        session = get_session()
        try:
            provider_record = (
                session.query(OAuthProvider)
                .filter(OAuthProvider.name == provider)
                .first()
            )
            if not provider_record:
                provider_record = OAuthProvider(name=provider)
                session.add(provider_record)
                session.commit()

            # Initialize mfa_token as None
            mfa_token = None

            # Check for existing OAuth connection
            if self.user_id:
                existing_oauth = (
                    session.query(UserOAuth)
                    .filter(UserOAuth.provider_id == provider_record.id)
                    .filter(UserOAuth.account_name == account_name)
                    .filter(UserOAuth.user_id == self.user_id)
                    .first()
                )
            else:
                existing_oauth = None

            if existing_oauth:
                # Get the user associated with this OAuth connection
                user = (
                    session.query(User)
                    .filter(User.id == existing_oauth.user_id)
                    .first()
                )
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")

                self.user_id = str(user.id)
                self.email = user.email
                mfa_token = user.mfa_token

                if self.user_id and str(existing_oauth.user_id) != str(self.user_id):
                    raise HTTPException(
                        status_code=400,
                        detail=f"This {provider} account is already connected to a different user.",
                    )
            else:
                # No existing OAuth connection found
                if not self.user_id:
                    # If no user is logged in, look up or create user by email
                    email = user_data.get("email") or account_name
                    user = session.query(User).filter(User.email == email).first()

                    if user:
                        self.user_id = str(user.id)
                        self.email = user.email
                        mfa_token = user.mfa_token
                    else:
                        # Create new user
                        register = Register(
                            email=email,
                            first_name=user_data.get("first_name", ""),
                            last_name=user_data.get("last_name", ""),
                        )
                        registration_response = self.register(
                            new_user=register,
                            invitation_id=invitation_id,
                            verify_email=True,
                        )

                        if isinstance(registration_response, dict):
                            if "error" in registration_response:
                                raise HTTPException(
                                    status_code=registration_response.get(
                                        "status_code", 400
                                    ),
                                    detail=registration_response["error"],
                                )
                            mfa_token = registration_response.get("mfa_token")
                        else:
                            mfa_token = registration_response
                else:
                    # User is logged in, get their MFA token
                    user = session.query(User).filter(User.id == self.user_id).first()
                    if not user:
                        raise HTTPException(status_code=404, detail="User not found")
                    mfa_token = user.mfa_token

            # Verify we have an MFA token before proceeding
            if not mfa_token:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to get or generate MFA token",
                )

            # Update or create OAuth connection
            self.update_sso(
                account_name=account_name,
                provider_name=provider,
                access_token=access_token,
                token_expires_at=token_expires_at,
                refresh_token=refresh_token,
            )

            totp = pyotp.TOTP(mfa_token)
            login = Login(email=self.email, token=totp.now())
            return self.send_magic_link(
                ip_address=ip_address,
                login=login,
                referrer=referrer,
                send_link=False,
            )
        finally:
            session.close()

    def update_sso(
        self,
        provider_name,
        access_token,
        account_name="",
        token_expires_at=None,
        refresh_token=None,
    ):
        provider_name = str(provider_name).lower()
        session = get_session()
        provider = (
            session.query(OAuthProvider)
            .filter(OAuthProvider.name == provider_name)
            .first()
        )
        if not provider:
            provider = OAuthProvider(name=provider_name)
            session.add(provider)
            session.commit()
        user_oauth = (
            session.query(UserOAuth)
            .filter(UserOAuth.user_id == self.user_id)
            .filter(UserOAuth.provider_id == provider.id)
            .first()
        )
        if not user_oauth:
            user_oauth = UserOAuth(
                user_id=self.user_id,
                provider_id=provider.id,
                account_name=account_name,
                access_token=access_token,
                token_expires_at=token_expires_at,
                refresh_token=refresh_token,
            )
            session.add(user_oauth)
        else:
            user_oauth.access_token = access_token
            if account_name:
                user_oauth.account_name = account_name
            if token_expires_at:
                user_oauth.token_expires_at = token_expires_at
            if refresh_token:
                user_oauth.refresh_token = refresh_token
        session.commit()
        session.close()

        if provider_name == "github":
            try:
                response = requests.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"token {access_token}"},
                )
                response.raise_for_status()
                github_username = response.json()["login"]
            except Exception as e:
                logging.error(f"Error getting GitHub username: {str(e)}")
                github_username = ""
            agixt = self.get_user_agent_session()
            agixt.update_agent_settings(
                agent_name=getenv("AGENT_NAME"),
                settings={
                    "GITHUB_API_KEY": access_token,
                    "GITHUB_USERNAME": github_username,
                },
            )
        return f"OAuth2 Credentials updated for {provider_name.capitalize()}."

    def get_sso_connections(self):
        session = get_session()
        user_oauth = (
            session.query(UserOAuth).filter(UserOAuth.user_id == self.user_id).all()
        )
        response = []
        creds = []
        for oauth in user_oauth:
            provider = (
                session.query(OAuthProvider)
                .filter(OAuthProvider.id == oauth.provider_id)
                .first()
            )
            response.append(provider.name)
            creds.append(
                {
                    "provider": provider.name,
                    "account_name": oauth.account_name,
                    "access_token": oauth.access_token,
                    "token_expires_at": oauth.token_expires_at,
                    "refresh_token": oauth.refresh_token,
                }
            )
        session.close()
        return response

    def disconnect_sso(self, provider_name):
        provider_name = str(provider_name).lower()
        session = get_session()
        provider = (
            session.query(OAuthProvider)
            .filter(OAuthProvider.name == provider_name)
            .first()
        )
        if not provider:
            session.close()
            raise HTTPException(status_code=404, detail="Provider not found")
        user_oauth = (
            session.query(UserOAuth)
            .filter(UserOAuth.user_id == self.user_id)
            .filter(UserOAuth.provider_id == provider.id)
            .first()
        )
        if not user_oauth:
            session.close()
            raise HTTPException(status_code=404, detail="User OAuth not found")
        session.delete(user_oauth)
        session.commit()
        session.close()
        agent = self.get_user_agent_session()
        if provider_name == "github":
            agent.update_agent_settings(
                agent_name=getenv("AGENT_NAME"),
                settings={"GITHUB_API_KEY": "", "GITHUB_USERNAME": ""},
            )
        return f"Disconnected {provider_name.capitalize()}."

    def get_timezone(self):
        user_preferences = self.get_user_preferences()
        if "timezone" in user_preferences:
            return user_preferences["timezone"]
        return getenv("TZ")

    def rename_company(self, company_id, name):
        # Check if user has permission to write to this company
        if not self.has_scope("company:write", company_id):
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        with get_session() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            company.name = name
            db.commit()
            user_role = self.get_user_role(company_id)
            role_name = None
            for role in default_roles:
                if role["id"] == user_role:
                    role_name = role["name"]
                    break
            if role_name is None:
                role_name = "user"
            return CompanyResponse(
                id=str(company.id),
                name=company.name,
                company_id=str(company.company_id) if company.company_id else None,
                status=getattr(company, "status", True),
                address=getattr(company, "address", None),
                phone_number=getattr(company, "phone_number", None),
                email=getattr(company, "email", None),
                website=getattr(company, "website", None),
                city=getattr(company, "city", None),
                state=getattr(company, "state", None),
                zip_code=getattr(company, "zip_code", None),
                country=getattr(company, "country", None),
                notes=getattr(company, "notes", None),
                users=[
                    UserResponse(
                        id=str(uc.user.id),
                        email=uc.user.email,
                        first_name=uc.user.first_name,
                        last_name=uc.user.last_name,
                        role=role_name,
                        role_id=uc.role_id,
                    )
                    for uc in company.users
                ],
                children=[],
            )

    def update_company(
        self,
        company_id: str,
        name: Optional[str] = None,
        status: Optional[bool] = None,
        address: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        website: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
        country: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        # Check if user has permission to write to this company
        if not self.has_scope("company:write", company_id):
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        with get_session() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            # Update only the fields that are provided
            if name is not None:
                company.name = name
            if status is not None:
                company.status = status
            if address is not None:
                company.address = address
            if phone_number is not None:
                company.phone_number = phone_number
            if email is not None:
                company.email = email
            if website is not None:
                company.website = website
            if city is not None:
                company.city = city
            if state is not None:
                company.state = state
            if zip_code is not None:
                company.zip_code = zip_code
            if country is not None:
                company.country = country
            if notes is not None:
                company.notes = notes

            db.commit()
            user_role = self.get_user_role(company_id)
            role_name = None
            for role in default_roles:
                if role["id"] == user_role:
                    role_name = role["name"]
                    break
            if role_name is None:
                role_name = "user"
            return CompanyResponse(
                id=str(company.id),
                name=company.name,
                company_id=str(company.company_id) if company.company_id else None,
                status=getattr(company, "status", True),
                address=getattr(company, "address", None),
                phone_number=getattr(company, "phone_number", None),
                users=[
                    UserResponse(
                        id=str(uc.user.id),
                        email=uc.user.email,
                        first_name=uc.user.first_name,
                        last_name=uc.user.last_name,
                        role=role_name,
                        role_id=uc.role_id,
                    )
                    for uc in company.users
                ],
                children=[],
            )

    # ==========================================================================
    # Personal Access Token (PAT) Management
    # ==========================================================================

    def create_personal_access_token(
        self,
        name: str,
        scopes: list,
        agent_ids: list = None,
        company_ids: list = None,
        expiration: str = None,
    ) -> dict:
        """
        Create a new personal access token for the user.

        Args:
            name: Human-readable name for the token (e.g., "CI/CD Pipeline")
            scopes: List of scope names the token has access to
            agent_ids: List of agent IDs the token can access (empty = all user's agents)
            company_ids: List of company IDs the token can access (empty = all user's companies)
            expiration: Expiration setting - "1_day", "7_days", "30_days", "90_days", "1_year", "never", or ISO datetime

        Returns:
            dict with token info including the actual token value (shown only once)
        """
        import secrets
        import hashlib

        self.validate_user()

        # Require apikeys:write scope
        if not self.has_scope("apikeys:write"):
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions. Required scope: apikeys:write",
            )

        # Validate that user can only grant scopes they have
        user_scopes = self.get_user_scopes()
        for scope in scopes:
            if not self.has_scope(scope):
                raise HTTPException(
                    status_code=403,
                    detail=f"Cannot grant scope '{scope}' - you don't have this permission",
                )

        # Validate agent access
        if agent_ids:
            user_agents = self._get_user_agent_ids()
            for agent_id in agent_ids:
                if str(agent_id) not in user_agents:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Cannot grant access to agent '{agent_id}' - you don't have access",
                    )

        # Validate company access
        if company_ids:
            user_companies = self.get_user_companies()
            for company_id in company_ids:
                if str(company_id) not in user_companies:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Cannot grant access to company '{company_id}' - you don't have access",
                    )

        # Calculate expiration date
        expires_at = self._calculate_expiration(expiration)

        # Generate the token
        # Format: agixt_<random_32_bytes_hex>
        token_bytes = secrets.token_bytes(32)
        token_value = f"agixt_{token_bytes.hex()}"
        token_prefix = token_value[:16]  # "agixt_" + first 10 hex chars
        token_hash = hash_pat_token(token_value)

        from DB import (
            PersonalAccessToken,
            PersonalAccessTokenAgentAccess,
            PersonalAccessTokenCompanyAccess,
        )

        session = get_session()
        try:
            # Create the token record
            pat = PersonalAccessToken(
                user_id=self.user_id,
                name=name,
                token_prefix=token_prefix,
                token_hash=token_hash,
                scopes_json=json.dumps(scopes),
                agents_json=json.dumps(agent_ids or []),
                companies_json=json.dumps(company_ids or []),
                expires_at=expires_at,
            )
            session.add(pat)
            session.flush()  # Get the ID

            # Add agent access records
            if agent_ids:
                for agent_id in agent_ids:
                    agent_access = PersonalAccessTokenAgentAccess(
                        token_id=pat.id,
                        agent_id=agent_id,
                    )
                    session.add(agent_access)

            # Add company access records
            if company_ids:
                for company_id in company_ids:
                    company_access = PersonalAccessTokenCompanyAccess(
                        token_id=pat.id,
                        company_id=company_id,
                    )
                    session.add(company_access)

            session.commit()

            return {
                "id": str(pat.id),
                "name": pat.name,
                "token": token_value,  # Only shown at creation time!
                "token_prefix": pat.token_prefix,
                "scopes": scopes,
                "agent_ids": agent_ids or [],
                "company_ids": company_ids or [],
                "expires_at": expires_at.isoformat() if expires_at else None,
                "created_at": (
                    pat.created_at.isoformat()
                    if pat.created_at
                    else datetime.now().isoformat()
                ),
            }
        except Exception as e:
            session.rollback()
            logging.error(f"Error creating personal access token: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create personal access token: {str(e)}",
            )
        finally:
            session.close()

    def _calculate_expiration(self, expiration: str) -> datetime:
        """Calculate expiration datetime from expiration setting string."""
        if not expiration or expiration == "never":
            return None

        now = datetime.now()
        expiration_map = {
            "1_day": timedelta(days=1),
            "7_days": timedelta(days=7),
            "30_days": timedelta(days=30),
            "90_days": timedelta(days=90),
            "1_year": timedelta(days=365),
        }

        if expiration in expiration_map:
            return now + expiration_map[expiration]

        # Try to parse as ISO datetime
        try:
            return datetime.fromisoformat(expiration.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid expiration format: {expiration}. Use '1_day', '7_days', '30_days', '90_days', '1_year', 'never', or ISO datetime.",
            )

    def _get_user_agent_ids(self) -> list:
        """Get list of agent IDs the user has access to."""
        from DB import Agent as AgentModel, AgentSetting as AgentSettingModel

        session = get_session()
        try:
            user = session.query(User).filter(User.id == self.user_id).first()
            if not user:
                return []

            agents = (
                session.query(AgentModel)
                .filter(AgentModel.user_id == self.user_id)
                .all()
            )
            return [str(agent.id) for agent in agents]
        finally:
            session.close()

    def list_personal_access_tokens(self) -> list:
        """
        List all personal access tokens for the current user.

        Returns:
            List of token info dicts (without actual token values)
        """
        self.validate_user()

        if not self.has_scope("apikeys:read"):
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions. Required scope: apikeys:read",
            )

        from DB import PersonalAccessToken

        session = get_session()
        try:
            tokens = (
                session.query(PersonalAccessToken)
                .filter(PersonalAccessToken.user_id == self.user_id)
                .filter(PersonalAccessToken.is_revoked == False)
                .order_by(PersonalAccessToken.created_at.desc())
                .all()
            )

            return [
                {
                    "id": str(token.id),
                    "name": token.name,
                    "token_prefix": token.token_prefix,
                    "scopes": json.loads(token.scopes_json),
                    "agent_ids": json.loads(token.agents_json),
                    "company_ids": json.loads(token.companies_json),
                    "expires_at": (
                        token.expires_at.isoformat() if token.expires_at else None
                    ),
                    "is_revoked": token.is_revoked,
                    "last_used_at": (
                        token.last_used_at.isoformat() if token.last_used_at else None
                    ),
                    "created_at": (
                        token.created_at.isoformat() if token.created_at else None
                    ),
                }
                for token in tokens
            ]
        finally:
            session.close()

    def get_personal_access_token(self, token_id: str) -> dict:
        """
        Get details of a specific personal access token.

        Args:
            token_id: The ID of the token to retrieve

        Returns:
            Token info dict (without actual token value)
        """
        self.validate_user()

        if not self.has_scope("apikeys:read"):
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions. Required scope: apikeys:read",
            )

        from DB import PersonalAccessToken

        session = get_session()
        try:
            token = (
                session.query(PersonalAccessToken)
                .filter(PersonalAccessToken.id == token_id)
                .filter(PersonalAccessToken.user_id == self.user_id)
                .first()
            )

            if not token:
                raise HTTPException(status_code=404, detail="Token not found")

            return {
                "id": str(token.id),
                "name": token.name,
                "token_prefix": token.token_prefix,
                "scopes": json.loads(token.scopes_json),
                "agent_ids": json.loads(token.agents_json),
                "company_ids": json.loads(token.companies_json),
                "expires_at": (
                    token.expires_at.isoformat() if token.expires_at else None
                ),
                "is_revoked": token.is_revoked,
                "last_used_at": (
                    token.last_used_at.isoformat() if token.last_used_at else None
                ),
                "created_at": (
                    token.created_at.isoformat() if token.created_at else None
                ),
            }
        finally:
            session.close()

    def revoke_personal_access_token(self, token_id: str) -> dict:
        """
        Revoke a personal access token.

        Args:
            token_id: The ID of the token to revoke

        Returns:
            Success message
        """
        self.validate_user()

        if not self.has_scope("apikeys:delete"):
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions. Required scope: apikeys:delete",
            )

        from DB import PersonalAccessToken

        session = get_session()
        try:
            token = (
                session.query(PersonalAccessToken)
                .filter(PersonalAccessToken.id == token_id)
                .filter(PersonalAccessToken.user_id == self.user_id)
                .first()
            )

            if not token:
                raise HTTPException(status_code=404, detail="Token not found")

            token.is_revoked = True
            token.updated_at = datetime.now()
            session.commit()

            return {"detail": f"Token '{token.name}' has been revoked"}
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            logging.error(f"Error revoking token: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to revoke token: {str(e)}",
            )
        finally:
            session.close()

    def regenerate_personal_access_token(self, token_id: str) -> dict:
        """
        Regenerate a personal access token (revokes old one and creates new with same settings).

        Args:
            token_id: The ID of the token to regenerate

        Returns:
            New token info including the new token value
        """
        import secrets
        import hashlib

        self.validate_user()

        if not self.has_scope("apikeys:write"):
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions. Required scope: apikeys:write",
            )

        from DB import PersonalAccessToken

        session = get_session()
        try:
            old_token = (
                session.query(PersonalAccessToken)
                .filter(PersonalAccessToken.id == token_id)
                .filter(PersonalAccessToken.user_id == self.user_id)
                .first()
            )

            if not old_token:
                raise HTTPException(status_code=404, detail="Token not found")

            # Generate new token
            token_bytes = secrets.token_bytes(32)
            new_token_value = f"agixt_{token_bytes.hex()}"
            new_token_prefix = new_token_value[:16]
            new_token_hash = hash_pat_token(new_token_value)

            # Update the token record with new hash
            old_token.token_prefix = new_token_prefix
            old_token.token_hash = new_token_hash
            old_token.updated_at = datetime.now()
            session.commit()

            return {
                "id": str(old_token.id),
                "name": old_token.name,
                "token": new_token_value,  # Only shown at regeneration time!
                "token_prefix": old_token.token_prefix,
                "scopes": json.loads(old_token.scopes_json),
                "agent_ids": json.loads(old_token.agents_json),
                "company_ids": json.loads(old_token.companies_json),
                "expires_at": (
                    old_token.expires_at.isoformat() if old_token.expires_at else None
                ),
                "created_at": (
                    old_token.created_at.isoformat() if old_token.created_at else None
                ),
            }
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            logging.error(f"Error regenerating token: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to regenerate token: {str(e)}",
            )
        finally:
            session.close()

    def get_available_scopes_for_token_creation(self) -> dict:
        """
        Get all scopes the current user can grant to a personal access token.

        Returns:
            Dict with scopes list and scopes grouped by category
        """
        self.validate_user()

        user_scopes = self.get_user_scopes()

        from DB import Scope, default_scopes

        session = get_session()
        try:
            # Get all scope definitions
            all_scopes = session.query(Scope).all()

            available_scopes = []
            categories = {}

            for scope in all_scopes:
                # Check if user has this scope (including wildcard matching)
                if self.has_scope(scope.name):
                    scope_info = {
                        "id": str(scope.id),
                        "name": scope.name,
                        "resource": scope.resource,
                        "action": scope.action,
                        "description": scope.description,
                        "category": scope.category or "Other",
                        "is_system": scope.is_system,
                    }
                    available_scopes.append(scope_info)

                    # Group by category
                    cat = scope.category or "Other"
                    if cat not in categories:
                        categories[cat] = []
                    categories[cat].append(scope_info)

            return {
                "scopes": available_scopes,
                "categories": categories,
            }
        finally:
            session.close()

    def get_available_agents_for_token_creation(self) -> list:
        """
        Get all agents the current user can grant access to for a personal access token.

        Returns:
            List of agent info dicts
        """
        self.validate_user()

        agents = get_agents(self.email, self.company_id)
        return agents

    def get_available_companies_for_token_creation(self) -> list:
        """
        Get all companies the current user can grant access to for a personal access token.

        Returns:
            List of company info dicts
        """
        self.validate_user()

        return self.get_user_companies_with_roles()


def validate_personal_access_token(token: str) -> dict:
    """
    Validate a personal access token and return user/scope information.

    This is a standalone function (not a method) so it can be used before
    we know who the user is.

    Args:
        token: The full token value (e.g., "agixt_abc123...")

    Returns:
        dict with validation info including user_id, scopes, etc.
    """
    if not token or not token.startswith("agixt_"):
        return {
            "valid": False,
            "error": "Invalid token format",
        }

    from DB import PersonalAccessToken

    token_hash = hash_pat_token(token)

    session = get_session()
    try:
        pat = (
            session.query(PersonalAccessToken)
            .filter(PersonalAccessToken.token_hash == token_hash)
            .first()
        )

        if not pat:
            return {
                "valid": False,
                "error": "Token not found",
            }

        if pat.is_revoked:
            return {
                "valid": False,
                "error": "Token has been revoked",
            }

        if pat.expires_at and pat.expires_at < datetime.now():
            return {
                "valid": False,
                "error": "Token has expired",
            }

        # Update last_used_at
        pat.last_used_at = datetime.now()
        session.commit()

        # Get user info
        user = session.query(User).filter(User.id == pat.user_id).first()

        return {
            "valid": True,
            "user_id": str(pat.user_id),
            "user_email": user.email if user else None,
            "scopes": json.loads(pat.scopes_json),
            "agent_ids": json.loads(pat.agents_json),
            "company_ids": json.loads(pat.companies_json),
            "token_name": pat.name,
        }
    except Exception as e:
        # Log full error details on the server, but do not expose them to the caller
        logging.error(f"Error validating personal access token: {str(e)}")
        return {
            "valid": False,
            # Return a generic error message to avoid leaking internal details
            "error": "Internal validation error",
        }
    finally:
        session.close()


def refresh_expiring_oauth_tokens():
    """Background task to refresh OAuth tokens that are expiring soon

    This function should be called periodically (e.g., every hour) to proactively
    refresh tokens that are expiring within the next 30 minutes.

    Returns:
        dict: Summary of refresh operations
    """
    session = get_session()
    summary = {
        "total_tokens_checked": 0,
        "tokens_refreshed": 0,
        "tokens_failed": 0,
        "errors": [],
    }

    try:
        # Find all tokens that expire within the next 30 minutes
        expiry_threshold = datetime.now() + timedelta(minutes=30)

        expiring_tokens = (
            session.query(UserOAuth)
            .filter(UserOAuth.token_expires_at <= expiry_threshold)
            .filter(UserOAuth.refresh_token.isnot(None))
            .all()
        )

        summary["total_tokens_checked"] = len(expiring_tokens)

        for user_oauth in expiring_tokens:
            try:
                # Get provider info
                provider = (
                    session.query(OAuthProvider)
                    .filter(OAuthProvider.id == user_oauth.provider_id)
                    .first()
                )

                if not provider:
                    continue

                # Create MagicalAuth instance for this user
                user = session.query(User).filter(User.id == user_oauth.user_id).first()
                if not user:
                    continue

                # Create a token for this user to use MagicalAuth
                temp_token = jwt.encode(
                    {
                        "sub": str(user.id),
                        "email": user.email,
                        "exp": datetime.now() + timedelta(hours=1),
                    },
                    os.getenv("AGIXT_API_KEY", ""),
                    algorithm="HS256",
                )

                auth = MagicalAuth(token=temp_token)
                auth.refresh_oauth_token(provider.name, force_refresh=True)

                summary["tokens_refreshed"] += 1

            except Exception as e:
                summary["tokens_failed"] += 1
                error_msg = f"Failed to refresh token for user {user_oauth.user_id}, provider {provider.name if provider else 'unknown'}: {str(e)}"
                summary["errors"].append(error_msg)
                logging.error(error_msg)

        return summary

    except Exception as e:
        logging.error(f"Error in refresh_expiring_oauth_tokens: {str(e)}")
        summary["errors"].append(f"General error: {str(e)}")
        return summary

    finally:
        session.close()


def cleanup_expired_oauth_tokens():
    """Remove OAuth tokens that have been expired for more than 30 days

    This helps keep the database clean by removing tokens that are definitely unusable.

    Returns:
        int: Number of expired tokens removed
    """
    session = get_session()

    try:
        # Remove tokens expired for more than 30 days
        expiry_threshold = datetime.now() - timedelta(days=30)

        expired_tokens = (
            session.query(UserOAuth)
            .filter(UserOAuth.token_expires_at <= expiry_threshold)
            .all()
        )

        count = len(expired_tokens)

        for token in expired_tokens:
            session.delete(token)

        session.commit()
        return count

    except Exception as e:
        session.rollback()
        logging.error(f"Error cleaning up expired OAuth tokens: {str(e)}")
        return 0

    finally:
        session.close()


def _normalize_user_id_value(user_id):
    """Ensure downstream helpers receive a scalar user identifier."""

    if isinstance(user_id, dict):
        for key in ("id", "user_id"):
            candidate = user_id.get(key)
            if candidate is not None:
                return candidate

        email = user_id.get("email")
        if email:
            try:
                return get_user_id(email)
            except HTTPException:
                return None

        return None

    return user_id


def get_user_timezone(user_id):
    normalized_user_id = _normalize_user_id_value(user_id)
    if normalized_user_id is None:
        return getenv("TZ") or "UTC"

    session = get_session()
    user_preferences = (
        session.query(UserPreferences)
        .filter(
            UserPreferences.user_id == normalized_user_id,
            UserPreferences.pref_key == "timezone",
        )
        .first()
    )
    if not user_preferences:
        user_preferences = UserPreferences(
            user_id=normalized_user_id,
            pref_key="timezone",
            pref_value=getenv("TZ") or "UTC",
        )
        session.add(user_preferences)
        session.commit()
    timezone = user_preferences.pref_value
    session.close()
    return timezone


def convert_time(utc_time, user_id) -> datetime:
    """Convert a UTC time to the user's local timezone"""
    if utc_time is None:
        return None

    normalized_user_id = _normalize_user_id_value(user_id)
    gmt = pytz.timezone("GMT")
    local_tz = pytz.timezone(get_user_timezone(normalized_user_id))
    if utc_time.tzinfo is None:
        return gmt.localize(utc_time).astimezone(local_tz)
    return utc_time.astimezone(local_tz)


def convert_user_time_to_utc(user_time, user_id) -> datetime:
    """Convert a user's local time to UTC for database storage"""
    import pytz

    normalized_user_id = _normalize_user_id_value(user_id)
    user_timezone = get_user_timezone(normalized_user_id)
    local_tz = pytz.timezone(user_timezone)

    # If the user_time is a naive datetime, assume it's in user's timezone
    if user_time.tzinfo is None:
        user_time = local_tz.localize(user_time)

    # Convert to UTC and return as naive datetime for database storage
    return user_time.astimezone(pytz.UTC).replace(tzinfo=None)


def get_current_user_time(user_id) -> datetime:
    """Get the current time in the user's timezone"""
    import pytz

    normalized_user_id = _normalize_user_id_value(user_id)
    user_timezone = get_user_timezone(normalized_user_id)
    local_tz = pytz.timezone(user_timezone)
    return datetime.now(local_tz)


def cleanup_expired_tokens():
    """
    Utility function to remove expired tokens from the blacklist.
    This can be called periodically to keep the blacklist table clean.
    """
    session = get_session()
    try:
        expired_tokens = (
            session.query(TokenBlacklist)
            .filter(TokenBlacklist.expires_at < datetime.now())
            .all()
        )

        count = len(expired_tokens)
        for token in expired_tokens:
            session.delete(token)

        session.commit()
        return count

    except Exception as e:
        session.rollback()
        logging.error(f"Error cleaning up expired tokens: {str(e)}")
        return 0
    finally:
        session.close()


# Example usage and integration points


async def example_oauth_usage():
    """Example of how to use the improved OAuth functionality"""

    # Example 1: Using oauth_api_call for robust API calls
    def get_google_calendar_events(google_api):
        # This function would make actual Google Calendar API calls
        return google_api.get_calendar_events()

    try:
        auth = MagicalAuth(token="your_user_token")
        events = auth.oauth_api_call("google", get_google_calendar_events)
        print(f"Retrieved {len(events)} calendar events")
    except HTTPException as e:
        print(f"Failed to get calendar events: {e.detail}")

    # Example 2: Check token status before important operations
    try:
        auth = MagicalAuth(token="your_user_token")
        token_status = auth.get_oauth_token_status()

        for provider, status in token_status.items():
            if status["is_expired"]:
                print(f"Warning: {provider} token is expired")
            elif status["expires_soon"]:
                print(f"Notice: {provider} token expires soon")
    except Exception as e:
        print(f"Error checking token status: {str(e)}")


def scheduled_token_maintenance():
    """Function to be called by a scheduled task (e.g., hourly)"""
    try:
        # Refresh expiring tokens
        refresh_results = refresh_expiring_oauth_tokens()
        # logging.info(f"Token refresh summary: {refresh_results}")

        # Clean up old expired tokens (run less frequently, e.g., daily)
        if datetime.now().hour == 2:  # Run at 2 AM
            cleanup_count = cleanup_expired_oauth_tokens()
            # logging.info(f"Cleaned up {cleanup_count} old expired tokens")

            # Also cleanup expired JWT tokens
            jwt_cleanup_count = cleanup_expired_tokens()
            # logging.info(f"Cleaned up {jwt_cleanup_count} expired JWT tokens")

    except Exception as e:
        logging.error(f"Error in scheduled token maintenance: {str(e)}")


# Integration with FastAPI endpoints


def create_oauth_status_endpoint():
    """Example FastAPI endpoint to check OAuth token status"""
    from fastapi import Depends

    def get_oauth_status(auth: MagicalAuth = Depends(verify_api_key)):
        """Get OAuth connection status for the authenticated user"""
        try:
            return {"status": "success", "data": auth.get_oauth_token_status()}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return get_oauth_status


def create_oauth_refresh_endpoint():
    """Example FastAPI endpoint to manually refresh OAuth tokens"""
    from fastapi import Depends

    def refresh_oauth_tokens(auth: MagicalAuth = Depends(verify_api_key)):
        """Manually refresh all OAuth tokens for the authenticated user"""
        try:
            results = auth.refresh_all_oauth_tokens()
            return {"status": "success", "data": results}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return refresh_oauth_tokens
