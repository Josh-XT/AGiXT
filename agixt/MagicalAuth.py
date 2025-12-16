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
    TokenBlacklist,
    PaymentTransaction,
    CompanyTokenUsage,
    ExtensionCategory,
)
from payments.pricing import PriceService
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
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
from ExtensionsHub import (
    find_extension_files,
    import_extension_module,
    get_extension_class_name,
)


logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
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
"""


def send_email(email: str, subject: str, body: str):
    try:
        # SendGrid
        sendgrid_api_key = getenv("SENDGRID_API_KEY")
        sendgrid_from_email = getenv("SENDGRID_FROM_EMAIL")
        if sendgrid_api_key and sendgrid_from_email:
            message = Mail(
                from_email=sendgrid_from_email,
                to_emails=email,
                subject=subject,
                html_content=body,
            )
            try:
                response = SendGridAPIClient(sendgrid_api_key).send(message)
            except Exception as e:
                return False
            if response.status_code != 202:
                return False
            return True
        # Mailgun
        mailgun_api_key = getenv("MAILGUN_API_KEY")
        mailgun_domain = getenv("MAILGUN_DOMAIN")
        mailgun_from_email = getenv("MAILGUN_FROM_EMAIL")
        if mailgun_api_key and mailgun_domain and mailgun_from_email:
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
            except Exception as e:
                return False
            if response.status_code != 200:
                return False
            return True

        # None
        return False
    except:
        return False


def is_admin(email: str = "USER", api_key: str = None):
    return True


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
            client_id = os.getenv(f"{module_name.upper()}_CLIENT_ID")
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
        except:
            pass
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
    if api_key == getenv("AGIXT_API_KEY"):
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
    AGIXT_API_KEY = getenv("AGIXT_API_KEY")
    authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    if AGIXT_API_KEY:
        if authorization == AGIXT_API_KEY:
            return get_admin_user()
        try:
            if authorization == AGIXT_API_KEY:
                return get_admin_user()

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
            return user_dict
        except Exception as e:
            logging.info(f"Error verifying API Key: {str(e)}")
            raise HTTPException(status_code=401, detail="Invalid API Key")
    else:
        logging.error(
            "AGiXT API Key is missing. Please set the AGIXT_API_KEY environment variable."
        )
        raise HTTPException(status_code=401, detail="API Key is missing.")


def get_user_id(user: str):
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    if user_data is None:
        session.close()
        raise HTTPException(status_code=404, detail=f"User {user} not found.")
    try:
        user_id = user_data.id
    except Exception as e:
        session.close()
        raise HTTPException(status_code=404, detail=f"User {user} not found.")
    session.close()
    return user_id


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
    AGIXT_API_KEY = getenv("AGIXT_API_KEY")
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
        encryption_key = getenv("AGIXT_API_KEY")
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
        user = session.query(User).filter(User.email == self.email).first()
        if not user:
            self.send_email_code()
            self.send_sms_code()
            session.close()
            return False
        session.close()
        return True

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
        """Check if a user has reached their subscription user limit

        True = user limit not reached
        False = user limit reached
        """
        # Check if we should bypass user limits entirely
        stripe_api_key = getenv("STRIPE_API_KEY")
        price_env = getenv("MONTHLY_PRICE_PER_USER_USD")
        try:
            price_value = float(price_env) if price_env else 0.0
        except (TypeError, ValueError):
            price_value = 0.0

        # If price is 0, bypass user limits regardless of Stripe configuration
        if price_value == 0:
            return True

        # We have to check how many users the company purchased from Stripe, compare to user count for the company
        session = get_session()
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            session.close()
            raise HTTPException(status_code=404, detail="Company not found")

        # Get user count for the company
        user_count = (
            session.query(UserCompany)
            .filter(UserCompany.company_id == company.id)
            .count()
        )

        # If company has an explicit user limit set, check against that
        if company.user_limit is not None and user_count >= company.user_limit:
            session.close()
            return False

        # If no explicit limit is set, check Stripe subscription
        if stripe_api_key and stripe_api_key.lower() != "none":
            try:
                import stripe

                stripe.api_key = stripe_api_key

                # Get company admin to check for subscription
                company_admin = (
                    session.query(User)
                    .join(UserCompany, User.id == UserCompany.user_id)
                    .filter(UserCompany.company_id == company.id)
                    .filter(UserCompany.role_id <= 2)  # Admin roles
                    .first()
                )

                if not company_admin:
                    session.close()
                    return False  # No admin found, can't verify subscription

                # Get admin preferences to find Stripe customer ID
                admin_preferences = (
                    session.query(UserPreferences)
                    .filter(UserPreferences.user_id == company_admin.id)
                    .all()
                )

                admin_pref_dict = {p.pref_key: p.pref_value for p in admin_preferences}
                stripe_id = admin_pref_dict.get("stripe_id")

                if not stripe_id or not stripe_id.startswith("cus_"):
                    session.close()
                    return False  # No valid Stripe ID

                # Get subscriptions for this customer
                subscriptions = self.get_subscribed_products(
                    stripe_api_key, company_admin.email
                )

                if not subscriptions:
                    session.close()
                    return False  # No active subscriptions

                # Check user limits from subscription metadata
                for subscription in subscriptions:
                    for item in subscription.get("items", {}).get("data", []):
                        product_id = item.get("price", {}).get("product")
                        if product_id:
                            product = stripe.Product.retrieve(product_id)
                            metadata = product.get("metadata", {})

                            # Check if product has user limit in metadata
                            if "user_limit" in metadata:
                                subscription_user_limit = int(metadata["user_limit"])
                                if user_count < subscription_user_limit:
                                    session.close()
                                    return True  # Under the subscription limit

                            # If product specifies unlimited users
                            if metadata.get("unlimited_users") == "true":
                                session.close()
                                return True

                # If we got here, no subscription with adequate user limits was found
                session.close()
                return False

            except Exception as e:
                logging.error(f"Error checking Stripe subscription: {str(e)}")
                session.close()
                return False

        # If no Stripe integration or other limits, default to allowing the user
        session.close()
        return True

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
        """Check if any of the user's companies have a positive token balance"""
        company_ids = {
            user_company.company_id
            for user_company in user_companies
            if getattr(user_company, "company_id", None)
        }
        if company_ids:
            company_with_balance = (
                session.query(Company)
                .filter(Company.id.in_(list(company_ids)))
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
                agixt = InternalClient()
                agixt.login(email=new_user.email, otp=pyotp.TOTP(mfa_token).now())
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
                    training_urls=(
                        default_agent["training_urls"]
                        if "training_urls" in default_agent
                        else []
                    ),
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
        session = get_session()
        company = session.query(Company).filter(Company.id == company_id).first()
        # Get users in the company and remove them from the company
        user_companies = (
            session.query(UserCompany)
            .filter(UserCompany.company_id == company.id)
            .all()
        )
        for user_company in user_companies:
            session.delete(user_company)
        session.commit()
        # Delete the company
        session.delete(company)
        session.commit()
        session.close()
        return "Company deleted successfully"

    def delete_user_from_company(self, company_id: str, target_user_id: str):
        self.validate_user()
        session = get_session()
        caller_role = self.get_user_role(company_id)
        if not caller_role or caller_role > 2:
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions to remove users.",
            )

        if str(company_id) not in self.get_user_companies():
            raise HTTPException(
                status_code=403, detail="Unauthorized. Company not accessible to user."
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

        # Prevent self-deletion for company admins
        if str(target_user_id) == str(self.user_id) and caller_role <= 2:
            raise HTTPException(
                status_code=400, detail="Company admins cannot remove themselves"
            )

        session.delete(user_company)
        session.commit()

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
        user_role = self.get_user_role(company_id)
        if user_role is None:
            session.close()
            raise HTTPException(status_code=404, detail="User not found in company")
        if user_role >= 3:
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
        if role_id < user_role:
            session.close()
            raise HTTPException(
                status_code=403,
                detail="User does not have permission to assign this role",
            )
        if user_company:
            user_company.role_id = role_id
            session.commit()
        else:
            session.close()
            raise HTTPException(
                status_code=404, detail="User not found in the specified company"
            )
        session.close()
        return "User role updated successfully."

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
        price_env = getenv("MONTHLY_PRICE_PER_USER_USD")
        try:
            price_value = float(str(price_env))
        except (TypeError, ValueError):
            price_value = 0.0
        # Determine if billing is enabled globally (token price > 0)
        price_service = PriceService()
        try:
            token_price = price_service.get_token_price()
        except Exception:
            # If pricing service fails for any reason, default to billing enabled
            token_price = 1
        billing_enabled = token_price > 0

        # Token billing is the primary billing model
        token_billing_enabled = token_price > 0
        # Subscription billing is deprecated but kept for backwards compatibility
        subscription_billing_enabled = price_value > 0

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
                raise HTTPException(
                    status_code=402,
                    detail={
                        "message": "Insufficient token balance. Please top up your tokens.",
                        "customer_session": {"client_secret": None},
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
            # Only proceed with Stripe checks if we haven't already confirmed active subscription via token balance
            if (
                not has_active_subscription
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
                                    # Only enforce subscription locking when subscription billing enabled
                                    if subscription_billing_enabled:
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
            if getenv("SENDGRID_API_KEY"):
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
        if not getenv("SENDGRID_API_KEY"):
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
        Use sendgrid to send a verification email to the user with a link to verify their email address
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
                company = (
                    session.query(Company)
                    .filter(Company.id == user_company.company_id)
                    .first()
                )

                if company:
                    # Check if company has sufficient balance (only when billing is enabled)
                    if company.token_balance < total_tokens:
                        session.close()
                        raise HTTPException(
                            status_code=402,
                            detail="Insufficient token balance. Please top up your company's token balance.",
                        )

                    # Deduct from company balance
                    company.token_balance -= total_tokens
                    company.tokens_used_total += total_tokens

                    # Record usage for audit trail
                    usage = CompanyTokenUsage(
                        company_id=company.id,
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
        """Get company token balance and usage stats"""
        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            low_balance_threshold = int(getenv("LOW_BALANCE_WARNING_THRESHOLD"))
            return {
                "token_balance": company.token_balance,
                "token_balance_usd": company.token_balance_usd,
                "tokens_used_total": company.tokens_used_total,
                "low_balance_warning": company.token_balance <= low_balance_threshold,
            }
        finally:
            session.close()

    def should_show_low_balance_warning(self, company_id: str) -> bool:
        """Check if low balance warning should be shown to admin"""
        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                return False

            current_balance = company.token_balance
            last_warning = company.last_low_balance_warning or 0
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
        """Admin dismisses warning, record current balance"""
        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            company.last_low_balance_warning = company.token_balance
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

    def get_user_companies_with_roles(self) -> List[dict]:
        """Get list of company IDs that the user has access to"""
        session = get_session()
        try:
            user_companies = (
                session.query(UserCompany)
                .filter(UserCompany.user_id == self.user_id)
                .all()
            )
            response = []
            for uc in user_companies:
                # Use the session to query the company
                company = (
                    session.query(Company).filter(Company.id == uc.company_id).first()
                )
                if company:
                    # Make sure to get the dict while the session is still open
                    company_dict = {}
                    for key, value in company.__dict__.items():
                        if not key.startswith("_"):
                            company_dict[key] = value

                    company_dict["role_id"] = uc.role_id
                    # Remove sensitive/large fields from response to reduce payload
                    if "encryption_key" in company_dict:
                        company_dict.pop("encryption_key")
                    if "token" in company_dict:
                        company_dict.pop("token")
                    # Remove training_data to reduce payload size - use persona endpoint instead
                    if "training_data" in company_dict:
                        company_dict.pop("training_data")
                    if str(company_dict["id"]) == str(self.company_id):
                        company_dict["primary"] = True
                    else:
                        company_dict["primary"] = False
                    # Get agents associated with this company and user
                    agents = get_agents(email=self.email, company=company_dict["id"])
                    company_dict["agents"] = agents
                    response.append(company_dict)
            return response
        finally:
            session.close()

    def get_invitations(self, company_id=None):
        if not company_id:
            company_id = self.get_user_company_id()
        if str(company_id) not in self.get_user_companies():
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
            for invitation in invitations:
                response.append(
                    {
                        "id": str(invitation.id),
                        "email": invitation.email,
                        "company_id": str(invitation.company_id),
                        "role_id": invitation.role_id,
                        "inviter_id": str(invitation.inviter_id),
                        "created_at": invitation.created_at,
                        "is_accepted": invitation.is_accepted,
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
            if str(invitation.company_id) not in self.get_user_companies():
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
        if str(invitation.company_id) not in self.get_user_companies():
            invitation.company_id = self.get_user_company_id()
        if getenv("STRIPE_API_KEY") != "":
            if not self.check_user_limit(invitation.company_id):
                raise HTTPException(
                    status_code=402,
                    detail="You've reached your user limit. Please upgrade your subscription.",
                )
        with get_session() as db:
            try:
                # Check if user has appropriate role
                user_role = self.get_user_role(invitation.company_id)
                if not invitation.role_id:
                    invitation.role_id = 3
                if user_role > 2:  # Only allow tenant_admin and company_admin
                    raise HTTPException(
                        status_code=403,
                        detail="Unauthorized. Insufficient permissions.",
                    )
                if int(invitation.role_id) < user_role:
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
                    invitation_link = self.send_invitation_email(existing_invitation)
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

                # Send invitation email
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
        if not email_send:
            logging.info(
                f"Failed to send invitation link {invitation_link} to {invitation.email}"
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
                return True
            except SQLAlchemyError as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=str(e))

    def get_user_company_id(self):
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
                        return None
                    return company_id_str
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
            if not user_company:
                return None
            return (
                user_company.role_id if user_company else 3
            )  # Default to regular user

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
                    role_id = self.get_user_role(str(company.id))
                    if not role_id:
                        continue
                    try:
                        role_id = int(role_id)
                    except:
                        continue
                    if role_id < 3:
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
                                if user_id not in child_unique_users:
                                    child_unique_users[user_id] = UserResponse(
                                        id=user_id,
                                        email=user.email,
                                        first_name=user.first_name,
                                        last_name=user.last_name,
                                        role=role_name,
                                        role_id=user_company.role_id,
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
        if not agent_name:
            agent_name = getenv("AGENT_NAME")
        with get_session() as db:
            try:
                if self.company_id != None:
                    if parent_company_id != None:
                        user_role = self.get_user_role(parent_company_id)
                    else:
                        user_role = self.get_user_role(self.company_id)
                    if user_role != None:
                        if user_role > 2:  # Only allow tenant_admin and company_admin
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
                agixt = InternalClient()
                company_email = f"{str(new_company.id)}@{str(new_company.id)}.xt"
                auth = MagicalAuth()
                auth.register(
                    new_user=Register(
                        email=company_email,
                        first_name="XT",
                        last_name="API",
                    ),
                    verify_email=False,
                )
                # Get mfa token by email
                company_user = (
                    db.query(User).filter(User.email == company_email).first()
                )
                mfa_token = company_user.mfa_token
                new_company.token = mfa_token
                db.commit()
                totp = pyotp.TOTP(mfa_token)
                agixt.login(email=company_email, otp=totp.now())
                default_agent = get_default_agent()
                agixt.add_agent(
                    agent_name="AGiXT",
                    settings=(
                        default_agent["settings"] if "settings" in default_agent else {}
                    ),
                    commands=(
                        default_agent["commands"] if "commands" in default_agent else {}
                    ),
                    training_urls=(
                        default_agent["training_urls"]
                        if "training_urls" in default_agent
                        else []
                    ),
                )
                response = {
                    "id": str(new_company.id),
                    "name": new_company.name,
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
        agixt = self.get_user_agent_session()
        # Just create an agent associated with the company like we do at registration
        default_agent = get_default_agent()
        default_agent["settings"]["company_id"] = company["id"]
        agixt.add_agent(
            agent_name=agent_name,
            settings=default_agent["settings"],
            commands=default_agent["commands"],
            training_urls=(
                default_agent["training_urls"]
                if "training_urls" in default_agent
                else []
            ),
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
        with get_session() as db:
            try:
                company = db.query(Company).filter(Company.id == company_id).first()
                if not company:
                    raise HTTPException(status_code=404, detail="Company not found")

                user_role = self.get_user_role(company_id)
                if user_role > 2:  # Only allow tenant_admin and company_admin
                    raise HTTPException(
                        status_code=403,
                        detail="Unauthorized. Insufficient permissions.",
                    )

                company.name = name
                db.commit()
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
        if str(company_id) not in self.get_user_companies():
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        # If role id is greater than 2, the user does not have permission to update the training data
        user_role = self.get_user_role(company_id)
        if user_role > 2:
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
        # Check if company is in users companies
        if str(company_id) not in self.get_user_companies():
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        with get_session() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            user_role = self.get_user_role(company_id)
            if user_role > 2:
                raise HTTPException(
                    status_code=403,
                    detail="Unauthorized. Insufficient permissions.",
                )
            company.name = name
            db.commit()
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
        # Check if company is in users companies
        if str(company_id) not in self.get_user_companies():
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        with get_session() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            user_role = self.get_user_role(company_id)
            if user_role > 2:
                raise HTTPException(
                    status_code=403,
                    detail="Unauthorized. Insufficient permissions.",
                )

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
                    getenv("AGIXT_API_KEY"),
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
