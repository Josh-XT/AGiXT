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
)
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
from datetime import datetime, timedelta
from fastapi import HTTPException
from agixtsdk import AGiXTSDK
import importlib.util
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
        logging.info(f"sendgrid_api_key: {sendgrid_api_key}")
        logging.info(f"sendgrid_from_email: {sendgrid_from_email}")
        if sendgrid_api_key and sendgrid_from_email:
            message = Mail(
                from_email=sendgrid_from_email,
                to_emails=email,
                subject=subject,
                html_content=body,
            )
            try:
                response = SendGridAPIClient(sendgrid_api_key).send(message)
                logging.info(f"Sengrid response: {response}")
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
    sso_dir = os.path.join(os.path.dirname(__file__), "sso")
    files = os.listdir(sso_dir)
    for file in files:
        if not file.endswith(".py"):
            continue
        file_path = os.path.join(sso_dir, file)
        spec = importlib.util.spec_from_file_location(file, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if file.replace(".py", "") == provider:
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
    sso_dir = os.path.join(os.path.dirname(__file__), "sso")
    files = os.listdir(sso_dir)
    providers = []
    for file in files:
        if not file.endswith(".py"):
            continue
        file_path = os.path.join(sso_dir, file)
        spec = importlib.util.spec_from_file_location(file, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            client_id = os.getenv(f"{file.replace('.py', '').upper()}_CLIENT_ID")
            if client_id:
                providers.append(
                    {
                        "name": file.replace(".py", ""),
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
    sso_dir = os.path.join(os.path.dirname(__file__), "sso")
    files = os.listdir(sso_dir)
    for file in files:
        if not file.endswith(".py"):
            continue
        file_path = os.path.join(sso_dir, file)
        if file.replace(".py", "") == provider:
            module = importlib.import_module(f"sso.{provider}")
            provider_class = getattr(module, f"{provider.capitalize()}SSO")
            return provider_class
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
            token = jwt.decode(
                jwt=authorization,
                key=AGIXT_API_KEY,
                algorithms=["HS256"],
                leeway=timedelta(hours=5),
            )
            db = get_session()
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
        for setting in agent_settings:
            if setting.name == "company_id":
                company_id = setting.value
                break
        if company_id and company:
            if company_id != company:
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
            logging.info(f"Email: {self.email}")
            logging.info(f"Token: {self.token}")
            logging.info(f"User ID: {self.user_id}")
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
        if not pyotp.TOTP(user.mfa_token).verify(login.token, valid_window=60):
            self.add_failed_login(ip_address=ip_address)
            session.close()
            logging.info(
                f"Failed login attempt for {self.email} with token {login.token}, should have been {pyotp.TOTP(user.mfa_token).now()}"
            )
            raise HTTPException(
                status_code=401, detail="Invalid MFA token. Please try again."
            )
        expiration = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        self.token = jwt.encode(
            {
                "sub": str(user.id),
                "email": self.email,
                "admin": user.admin,
                "exp": expiration,
            },
            self.encryption_key,
            algorithm="HS256",
        )
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
        if failures >= 50:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts today. Please try again tomorrow.",
            )
        session = get_session()
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

    def refresh_oauth_token(self, provider: str):
        """Refresh OAuth token if expired"""
        session = get_session()
        provider_record = (
            session.query(OAuthProvider).filter(OAuthProvider.name == provider).first()
        )
        if not provider_record:
            session.close()
            raise HTTPException(status_code=404, detail="Provider not found")

        user_oauth = (
            session.query(UserOAuth)
            .filter(UserOAuth.user_id == self.user_id)
            .filter(UserOAuth.provider_id == provider_record.id)
            .first()
        )

        if not user_oauth:
            session.close()
            raise HTTPException(status_code=404, detail="OAuth connection not found")

        # Check if token needs refresh
        if (
            user_oauth.token_expires_at
            and user_oauth.token_expires_at <= datetime.now() + timedelta(minutes=5)
            and user_oauth.refresh_token
        ):
            try:
                sso_instance = get_sso_instance(provider)(
                    refresh_token=user_oauth.refresh_token
                )
                new_tokens = sso_instance.get_new_token()

                # Update stored tokens
                user_oauth.access_token = new_tokens["access_token"]
                if "refresh_token" in new_tokens:
                    user_oauth.refresh_token = new_tokens["refresh_token"]
                if "expires_in" in new_tokens:
                    user_oauth.token_expires_at = datetime.now() + timedelta(
                        seconds=new_tokens["expires_in"]
                    )

                session.commit()
                session.close()
                return new_tokens["access_token"]

            except Exception as e:
                session.close()
                raise HTTPException(
                    status_code=401,
                    detail=f"Failed to refresh {provider} token: {str(e)}",
                )

        session.close()
        return user_oauth.access_token

    def get_oauth_functions(self, provider: str):
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        if not user:
            session.close()
            raise HTTPException(status_code=404, detail="User not found")
        provider = (
            session.query(OAuthProvider).filter(OAuthProvider.name == provider).first()
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
        access_token = user_oauth.access_token
        session.close()
        return get_sso_instance(provider.name)(access_token=access_token)

    def check_user_limit(self, company_id: str) -> bool:
        """Check if a user has reached their subscription user limit

        True = user limit not reached
        False = user limit reached
        """
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
        stripe_api_key = getenv("STRIPE_API_KEY")
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
            logging.info(f"Fetched invitation: {invitation}")
            # Create new user
            new_user_db = User(
                email=self.email,
                first_name=new_user.first_name,
                last_name=new_user.last_name,
                mfa_token=mfa_token,
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
                agixt = AGiXTSDK(base_uri=getenv("AGIXT_URI"))
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
        import stripe

        stripe.api_key = stripe_api_key
        logging.info(f"Checking subscriptions for user {user_email}...")
        try:
            # First, find all customer records with this email
            customers = stripe.Customer.list(email=user_email)

            relevant_subscriptions = []

            # Check subscriptions for each customer record
            for customer in customers.data:
                logging.info(f"Found customer: {customer.id} for email {user_email}")
                all_subscriptions = stripe.Subscription.list(
                    customer=customer.id,
                    expand=["data.items.data.price"],
                )

                logging.info(
                    f"Found {len(all_subscriptions)} subscriptions for customer {customer.id}."
                )

                # Add all active subscriptions for this app
                for subscription in all_subscriptions:
                    if subscription.status != "active":
                        continue

                    app_relevant = False
                    for item in subscription["items"]["data"]:
                        try:
                            product_id = item["price"]["product"]
                            product = stripe.Product.retrieve(product_id)

                            if product.get("metadata", {}).get("APP_NAME") == getenv(
                                "APP_NAME"
                            ):
                                app_relevant = True
                                break
                        except Exception as e:
                            logging.error(f"Error checking product: {e}")

                    if app_relevant:
                        relevant_subscriptions.append(subscription)
                        logging.info(
                            f"Found relevant subscription {subscription['id']}"
                        )

            return relevant_subscriptions

        except Exception as e:
            logging.error(f"Error checking subscriptions: {e}")
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
        if role_id > 3:
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
        user_requirements = self.registration_requirements()
        if not user_preferences:
            user_preferences = {}
        if "input_tokens" not in user_preferences:
            user_preferences["input_tokens"] = 0
        if "output_tokens" not in user_preferences:
            user_preferences["output_tokens"] = 0
        if user.email != getenv("DEFAULT_USER"):
            api_key = getenv("STRIPE_API_KEY")
            if api_key != "" and api_key is not None and str(api_key).lower() != "none":
                import stripe

                stripe.api_key = api_key
                # Get list of users companies
                user_companies = (
                    session.query(UserCompany)
                    .filter(UserCompany.user_id == self.user_id)
                    .all()
                )
                is_subscription = False
                if not user.email.endswith(".xt"):
                    # Check if this user has their own subscription first
                    if "stripe_id" in user_preferences:
                        relevant_subscriptions = self.get_subscribed_products(
                            api_key, user.email
                        )
                        if relevant_subscriptions:
                            is_subscription = True

                    # Only check company subscriptions if the user doesn't have their own
                    if not is_subscription:
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
                                            company_admin_preferences["stripe_id"],
                                        )
                                    )
                                    if relevant_subscriptions:
                                        is_subscription = True
                                        break
                        if not is_subscription:
                            if (
                                "stripe_id" not in user_preferences
                                or not user_preferences["stripe_id"].startswith("cus_")
                            ):
                                logging.info("No Stripe ID found in user preferences.")
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
                                    "Stripe ID found: " + user_preferences["stripe_id"]
                                )
                                relevant_subscriptions = self.get_subscribed_products(
                                    api_key, user.email
                                )
                                if not relevant_subscriptions:
                                    logging.info(
                                        f"No active subscriptions for this app detected."
                                    )
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
                                        f"{len(relevant_subscriptions)} subscriptions relevant to this app detected."
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
        session.close()
        # logging.info(f"User Preferences: {user_preferences}")
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
                from twilio.rest import Client

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
        logging.info(f"Email verification link sent to {self.email}: {sent}")
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
            session.commit()
        else:
            user_input_tokens.pref_value = str(updated_input_tokens)
            session.commit()
        # Update output tokens
        if user_output_tokens is None:
            user_output_tokens = UserPreferences(
                user_id=self.user_id,
                pref_key="output_tokens",
                pref_value=str(updated_output_tokens),
            )
            session.add(user_output_tokens)
            session.commit()
        else:
            user_output_tokens.pref_value = str(updated_output_tokens)
            session.commit()
        session.close()
        return {
            "input_tokens": updated_input_tokens,
            "output_tokens": updated_output_tokens,
        }

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
                    if "encryption_key" in company_dict:
                        company_dict.pop("encryption_key")
                    if "token" in company_dict:
                        company_dict.pop("token")
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
                    agixt = AGiXTSDK(base_uri=getenv("AGIXT_URI"))
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
                logging.info(f"Invitation created: {response}")
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
                return str(user_company.company_id) if user_company else None
        except Exception as e:
            return None

    def get_user_company(self, company_id):
        with get_session() as db:
            # Make sure the company ID is in the lsit of users companies
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
                            user = user_company.user
                            user_id = str(user.id)
                            if user_id not in unique_users:
                                unique_users[user_id] = UserResponse(
                                    id=user_id,
                                    email=user.email,
                                    first_name=user.first_name,
                                    last_name=user.last_name,
                                    role=user_company.role.name,
                                    role_id=user_company.role_id,
                                )

                    company_data = {
                        "id": str(company.id),
                        "name": company.name,
                        "company_id": (
                            str(company.company_id) if company.company_id else None
                        ),
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
                                user = user_company.user
                                user_id = str(user.id)
                                if user_id not in child_unique_users:
                                    child_unique_users[user_id] = UserResponse(
                                        id=user_id,
                                        email=user.email,
                                        first_name=user.first_name,
                                        last_name=user.last_name,
                                        role=user_company.role.name,
                                        role_id=user_company.role_id,
                                    )

                            child_data = {
                                "id": str(child.id),
                                "name": child.name,
                                "company_id": str(child.company_id),
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
                    db, name=name, company_id=parent_company_id, agent_name=agent_name
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
                agixt = AGiXTSDK(base_uri=getenv("AGIXT_URI"))
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
    ):
        if not agent_name:
            agent_name = getenv("AGENT_NAME")
        company = self.create_company(
            name=name, parent_company_id=parent_company_id, agent_name=agent_name
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

                return CompanyResponse(
                    id=str(company.id),
                    name=company.name,
                    company_id=str(company.company_id) if company.company_id else None,
                    users=[
                        UserResponse(
                            id=str(uc.user.id),
                            email=uc.user.email,
                            first_name=uc.user.first_name,
                            last_name=uc.user.last_name,
                            role=uc.role.name,
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

    def get_user_agent_session(self) -> AGiXTSDK:
        session = get_session()
        user_details = session.query(User).filter(User.id == self.user_id).first()
        if not user_details:
            session.close()
            raise HTTPException(status_code=401, detail="Invalid user login")
        agixt = AGiXTSDK(base_uri=getenv("AGIXT_URI"))
        agixt.login(
            email=user_details.email, otp=pyotp.TOTP(user_details.mfa_token).now()
        )
        session.close()
        return agixt

    def get_company_agent_session(self, company_id: str = None) -> AGiXTSDK:
        if not company_id:
            company_id = self.company_id
        company = self.get_user_company(company_id)
        if not company:
            return None
        # Check if company_id is in the users companies
        if str(company_id) not in self.get_user_companies():
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Insufficient permissions.",
            )
        agixt = AGiXTSDK(base_uri=getenv("AGIXT_URI"))
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
            referrer = getenv("APP_URI")
        # Check if one of the providers in the sso folder
        provider = str(provider).lower()
        files = os.listdir("sso")
        if f"{provider}.py" not in files:
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
            existing_oauth = (
                session.query(UserOAuth)
                .filter(UserOAuth.provider_id == provider_record.id)
                .filter(UserOAuth.account_name == account_name)
                .first()
            )

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
        logging.info(
            f"[{provider_name.capitalize()}] OAuth2 credentials updated. Access Token {access_token}"
        )
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
        logging.info(f"User {self.user_id} has SSO connections: {creds}")
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
            return CompanyResponse(
                id=str(company.id),
                name=company.name,
                company_id=str(company.company_id) if company.company_id else None,
                users=[
                    UserResponse(
                        id=str(uc.user.id),
                        email=uc.user.email,
                        first_name=uc.user.first_name,
                        last_name=uc.user.last_name,
                        role=uc.role.name,
                        role_id=uc.role_id,
                    )
                    for uc in company.users
                ],
                children=[],
            )


def get_user_timezone(user_id):
    session = get_session()
    user_preferences = (
        session.query(UserPreferences)
        .filter(
            UserPreferences.user_id == user_id,
            UserPreferences.pref_key == "timezone",
        )
        .first()
    )
    if not user_preferences:
        user_preferences = UserPreferences(
            user_id=user_id, pref_key="timezone", pref_value=getenv("TZ")
        )
        session.add(user_preferences)
        session.commit()
    timezone = user_preferences.pref_value
    session.close()
    return timezone


def convert_time(utc_time, user_id):
    gmt = pytz.timezone("GMT")
    local_tz = pytz.timezone(get_user_timezone(user_id))
    return gmt.localize(utc_time).astimezone(local_tz)
