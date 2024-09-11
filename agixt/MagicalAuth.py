from DB import (
    User,
    FailedLogins,
    UserOAuth,
    OAuthProvider,
    UserPreferences,
    get_session,
)
from OAuth2Providers import get_sso_provider
from Models import UserInfo, Register, Login
from agixtsdk import AGiXTSDK
from fastapi import Header, HTTPException
from Globals import getenv, get_default_agent, get_agixt_training_urls
from datetime import datetime, timedelta
from fastapi import HTTPException
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    FileContent,
    FileName,
    FileType,
    Disposition,
    Mail,
)
import pyotp
import requests
import logging
import jwt
import json
import os


logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
"""
Required environment variables:

- SENDGRID_API_KEY: SendGrid API key
- SENDGRID_FROM_EMAIL: Default email address to send emails from
- AGIXT_API_KEY: Encryption key to encrypt and decrypt data
- MAGIC_LINK_URL: URL to send in the email for the user to click on
- REGISTRATION_WEBHOOK: URL to send a POST request to when a user registers
"""


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


def verify_api_key(authorization: str = Header(None)):
    AGIXT_API_KEY = getenv("AGIXT_API_KEY")
    if getenv("AUTH_PROVIDER") == "magicalauth":
        AGIXT_API_KEY = f'{AGIXT_API_KEY}{datetime.now().strftime("%Y%m%d")}'
    authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    if AGIXT_API_KEY:
        if authorization is None:
            raise HTTPException(
                status_code=401, detail="Authorization header is missing"
            )
        if authorization == AGIXT_API_KEY:
            return "ADMIN"
        try:
            if authorization == AGIXT_API_KEY:
                return "ADMIN"
            token = jwt.decode(
                jwt=authorization,
                key=AGIXT_API_KEY,
                algorithms=["HS256"],
                leeway=timedelta(hours=5),
            )
            db = get_session()
            user = db.query(User).filter(User.id == token["sub"]).first()
        except Exception as e:
            raise HTTPException(status_code=401, detail="Invalid API Key")
        if user.is_active == False:
            user_preferences = MagicalAuth(token=authorization).get_user_preferences()
        db.close()
        return user
    else:
        return authorization


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
    user = session.query(User).filter(User.email == email).first()
    if not user:
        session.close()
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def send_email(
    email: str,
    subject: str,
    body: str,
    attachment_content=None,
    attachment_file_type=None,
    attachment_file_name=None,
):
    message = Mail(
        from_email=getenv("SENDGRID_FROM_EMAIL"),
        to_emails=email,
        subject=subject,
        html_content=body,
    )
    if (
        attachment_content != None
        and attachment_file_type != None
        and attachment_file_name != None
    ):
        attachment = Attachment(
            FileContent(attachment_content),
            FileName(attachment_file_name),
            FileType(attachment_file_type),
            Disposition("attachment"),
        )
        message.attachment = attachment

    try:
        response = SendGridAPIClient(getenv("SENDGRID_API_KEY")).send(message)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Email could not be sent.")
    if response.status_code != 202:
        raise HTTPException(status_code=400, detail="Email could not be sent.")
    return None


def encrypt(key: str, data: str):
    return jwt.encode({"data": data}, key, algorithm="HS256")


def decrypt(key: str, data: str):
    return jwt.decode(
        data,
        key,
        algorithms=["HS256"],
        leeway=timedelta(hours=5),
    )["data"]


class MagicalAuth:
    def __init__(self, token: str = None):
        encryption_key = getenv("AGIXT_API_KEY")
        self.link = getenv("MAGIC_LINK_URL")
        self.encryption_key = f'{encryption_key}{datetime.now().strftime("%Y%m%d")}'
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
            self.user_id = get_user_id(self.email)
            self.token = token
        except:
            self.email = None
            self.token = None
            self.user_id = None
        if token == encryption_key:
            self.email = getenv("DEFAULT_USER")
            self.user_id = get_user_id(self.email)
            self.token = token

    def validate_user(self):
        if self.user_id is None:
            logging.info(f"Email: {self.email}")
            logging.info(f"Token: {self.token}")
            logging.info(f"User ID: {self.user_id}")
            raise HTTPException(status_code=401, detail="Invalid token. Please log in.")
        return True

    def user_exists(self, email: str = None):
        self.email = email.lower()
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
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
        send_link: bool = True,
    ):
        self.email = login.email.lower()
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        if user is None:
            session.close()
            raise HTTPException(status_code=404, detail="User not found")
        if not pyotp.TOTP(user.mfa_token).verify(login.token):
            self.add_failed_login(ip_address=ip_address)
            session.close()
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
        if (
            getenv("SENDGRID_API_KEY") != ""
            and str(getenv("SENDGRID_API_KEY")).lower() != "none"
            and getenv("SENDGRID_FROM_EMAIL") != ""
            and str(getenv("SENDGRID_FROM_EMAIL")).lower() != "none"
            and send_link
        ):
            send_email(
                email=self.email,
                subject="Magic Link",
                body=f"<a href='{magic_link}'>Click here to log in</a>",
            )
        else:
            session.close()
            return magic_link
        # Upon clicking the link, the front end will call the login method and save the email and encrypted_id in the session
        session.close()
        return f"A login link has been sent to {self.email}, please check your email and click the link to log in. The link will expire in 24 hours."

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

    def register(
        self,
        new_user: Register,
    ):
        new_user.email = new_user.email.lower()
        self.email = new_user.email
        allowed_domains = getenv("ALLOWED_DOMAINS")
        registration_disabled = getenv("REGISTRATION_DISABLED").lower() == "true"
        if registration_disabled:
            raise HTTPException(
                status_code=403, detail="Registration is disabled for this server."
            )
        if allowed_domains is None or allowed_domains == "":
            allowed_domains = "*"
        if allowed_domains != "*":
            if "," in allowed_domains:
                allowed_domains = allowed_domains.split(",")
            else:
                allowed_domains = [allowed_domains]
            domain = self.email.split("@")[1]
            if domain not in allowed_domains:
                raise HTTPException(
                    status_code=403,
                    detail="Registration is not allowed for this domain.",
                )
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        if user is not None:
            logging.info(
                f"User already exists with email: {self.email}. {user.__dict__}"
            )
            session.close()
            raise HTTPException(
                status_code=409, detail="User already exists with this email."
            )
        mfa_token = pyotp.random_base32()
        user = User(
            mfa_token=mfa_token,
            **new_user.model_dump(),
        )
        session.add(user)
        session.commit()
        # Add default user preferences
        user_preferences = UserPreferences(
            user_id=user.id,
            pref_key="timezone",
            pref_value=getenv("TZ"),
        )
        session.add(user_preferences)
        session.commit()
        user_preferences = UserPreferences(
            user_id=user.id,
            pref_key="input_tokens",
            pref_value="0",
        )
        session.add(user_preferences)
        session.commit()
        user_preferences = UserPreferences(
            user_id=user.id,
            pref_key="output_tokens",
            pref_value="0",
        )
        session.add(user_preferences)
        session.commit()
        session.close()
        # Send registration webhook out to third party application such as AGiXT to create a user there.
        registration_webhook = getenv("REGISTRATION_WEBHOOK")
        if registration_webhook:
            try:
                requests.post(
                    registration_webhook,
                    json={"email": self.email},
                    headers={"Authorization": getenv("AGIXT_API_KEY")},
                )
            except Exception as e:
                pass
        # After registering the user, add a default AGiXT agent for the user
        # Train the agent on the AGiXT documentation.
        create_agent = str(getenv("CREATE_AGENT_ON_REGISTER")).lower() == "true"
        if create_agent:
            agixt = AGiXTSDK(base_uri=getenv("AGIXT_URI"))
            otp = pyotp.TOTP(mfa_token)
            agixt.login(email=new_user.email, otp=otp.now())
            agent_name = getenv("AGIXT_AGENT")
            agent_config = get_default_agent()
            agent_settings = agent_config["settings"]
            agent_commands = agent_config["commands"]
            create_agixt_agent = str(getenv("CREATE_AGIXT_AGENT")).lower() == "true"
            training_urls = (
                get_agixt_training_urls()
                if create_agixt_agent and agent_name == "AGiXT"
                else agent_config["training_urls"]
            )
            agixt.add_agent(
                agent_name=agent_name,
                settings=agent_settings,
                commands=agent_commands,
                training_urls=training_urls,
            )
        return mfa_token

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
        if "stripe_id" in kwargs:
            del kwargs["stripe_id"]
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

    def delete_user(self):
        session = get_session()
        user = session.query(User).filter(User.id == self.user_id).first()
        user.is_active = False
        session.commit()
        session.close()
        return "User deleted successfully"

    def sso(
        self,
        provider,
        code,
        ip_address,
        referrer=None,
    ):
        if not referrer:
            referrer = getenv("MAGIC_LINK_URL")
        provider = str(provider).lower()
        sso_data = None
        sso_data = get_sso_provider(provider=provider, code=code, redirect_uri=referrer)
        if not sso_data:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to get user data from {provider.capitalize()}.",
            )
        if not sso_data.access_token:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to get access token from {provider.capitalize()}.",
            )
        user_data = sso_data.user_info
        access_token = sso_data.access_token
        refresh_token = sso_data.refresh_token
        self.email = str(user_data["email"]).lower()
        if not user_data:
            logging.warning(f"Error on {provider.capitalize()}: {user_data}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to get user data from {provider.capitalize()}.",
            )
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        if not user:
            register = Register(
                email=self.email,
                first_name=user_data["first_name"] if "first_name" in user_data else "",
                last_name=user_data["last_name"] if "last_name" in user_data else "",
            )
            mfa_token = self.register(new_user=register)
            # Create the UserOAuth record
            user = session.query(User).filter(User.email == self.email).first()
            provider = (
                session.query(OAuthProvider)
                .filter(OAuthProvider.name == provider)
                .first()
            )
            if not provider:
                provider = OAuthProvider(name=provider)
                session.add(provider)
            user_oauth = UserOAuth(
                user_id=user.id,
                provider_id=provider.id,
                access_token=access_token,
                refresh_token=refresh_token,
            )
            session.add(user_oauth)
        else:
            mfa_token = user.mfa_token
            user_oauth = (
                session.query(UserOAuth).filter(UserOAuth.user_id == user.id).first()
            )
            if user_oauth:
                user_oauth.access_token = access_token
                user_oauth.refresh_token = refresh_token
        session.commit()
        session.close()
        totp = pyotp.TOTP(mfa_token)
        login = Login(email=self.email, token=totp.now())
        return self.send_magic_link(
            ip_address=ip_address,
            login=login,
            referrer=referrer,
            send_link=False,
        )

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
        if provider.name == "google":
            from sso.google import GoogleSSO

            return GoogleSSO(access_token=access_token)
        elif provider.name == "microsoft":
            from sso.microsoft import MicrosoftSSO

            return MicrosoftSSO(access_token=access_token)
        elif provider.name == "github":
            from sso.github import GitHubSSO

            return GitHubSSO(access_token=access_token)

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

    def get_subscribed_products(self, stripe_api_key, stripe_customer_id):
        import stripe

        # TODO make sure if the stripe request fails, an exception gets thrown.
        stripe.api_key = stripe_api_key
        logging.info(f"Checking subscriptions for customer {stripe_customer_id}...")
        all_subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id,
            expand=["data.items.data.price"],
        )
        logging.info(f"Found {len(all_subscriptions)} subscriptions.")
        relevant_subscriptions = []
        for subscription in all_subscriptions:
            logging.info(f"Checking subscription {subscription['id']}")
            if subscription.status == "active":
                logging.info(f"Subscription {subscription['id']} active.")
                relevant_to_this_app = None
                for item in subscription["items"]:
                    product_id = item["price"]["product"]
                    product = stripe.Product.retrieve(product_id)
                    try:
                        relevant_app = product["metadata"]["APP_NAME"]
                    except:
                        relevant_app = "[No App Defined in Product]"
                        logging.warning(
                            f"Subscription detected with items missing relevant APP_NAME metadata: {subscription['id']}"
                        )
                    print(product)
                    print(relevant_app)
                    if relevant_app == getenv("APP_NAME"):
                        if relevant_to_this_app == False:
                            raise Exception(
                                f"Subscription detected with items from multiple apps (or products missing metadata): {subscription['id']}"
                            )
                        relevant_to_this_app = True
                        logging.info(
                            f"Subscription {subscription['id']} relevant to this app {getenv('APP_NAME')}."
                        )
                    else:
                        if relevant_to_this_app == True:
                            raise Exception(
                                f"Subscription detected with items from multiple apps (or products missing metadata): {subscription['id']}"
                            )
                        relevant_to_this_app = False
                        logging.info(
                            f"Subscription {subscription['id']} not relevant to this app {getenv('APP_NAME')}, is for {relevant_app}."
                        )
                    if relevant_to_this_app:
                        relevant_subscriptions.append(subscription)
            else:
                logging.info(f"Subscription {subscription['id']} not active.")
        return relevant_subscriptions

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
                if "stripe_id" not in user_preferences or not user_preferences[
                    "stripe_id"
                ].startswith("cus_"):
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

                else:
                    logging.info("Stripe ID found: " + user_preferences["stripe_id"])
                    relevant_subscriptions = self.get_subscribed_products(
                        api_key, user_preferences["stripe_id"]
                    )
                    if not relevant_subscriptions:
                        logging.info(f"No active subscriptions for this app detected.")
                        c_session = stripe.CustomerSession.create(
                            customer=user_preferences["stripe_id"],
                            components={"pricing_table": {"enabled": True}},
                        )
                        user = (
                            session.query(User).filter(User.id == self.user_id).first()
                        )
                        user.is_active = False
                        session.commit()
                        session.close()
                        raise HTTPException(
                            status_code=402,
                            detail={
                                "message": f"No active subscriptions.",
                                "customer_session": c_session,
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
        if "missing_requirements" in user_preferences:
            del user_preferences["missing_requirements"]
        missing_requirements = []
        if user_requirements:
            for key, value in user_requirements.items():
                if key not in user_preferences:
                    if key != "stripe_id":
                        missing_requirements.append({key: value})
        if missing_requirements:
            user_preferences["missing_requirements"] = missing_requirements
        session.close()
        logging.info(f"User Preferences: {user_preferences}")
        return user_preferences

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
