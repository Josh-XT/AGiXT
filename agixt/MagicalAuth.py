from DB import User, FailedLogins, get_session
from Models import UserInfo, Register, Login
from fastapi import Header, HTTPException
from Globals import getenv
from datetime import datetime, timedelta
from hashlib import md5
from Agent import add_agent
from agixtsdk import AGiXTSDK
from Crypto.Cipher import AES
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
import base64
import logging
import jwt
import os


logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
"""
Required environment variables:

- SENDGRID_API_KEY: SendGrid API key
- SENDGRID_FROM_EMAIL: Default email address to send emails from
- ENCRYPTION_SECRET: Encryption key to encrypt and decrypt data
- MAGIC_LINK_URL: URL to send in the email for the user to click on
- REGISTRATION_WEBHOOK: URL to send a POST request to when a user registers
"""


def is_agixt_admin(email: str = "", api_key: str = ""):
    if api_key == getenv("AGIXT_API_KEY"):
        return True
    session = get_session()
    user = session.query(User).filter_by(email=email).first()
    if not user:
        return False
    if user.admin is True:
        return True
    return False


def create_user(
    api_key: str,
    email: str,
    role: str = "user",
    agent_name: str = "",
    settings: dict = {},
    commands: dict = {},
    training_urls: list = [],
    github_repos: list = [],
    ApiClient: AGiXTSDK = AGiXTSDK(),
):
    if not is_agixt_admin(email=email, api_key=api_key):
        return {"error": "Access Denied"}, 403
    session = get_session()
    email = email.lower()
    user_exists = session.query(User).filter_by(email=email).first()
    if user_exists:
        session.close()
        return {"error": "User already exists"}, 400
    admin = True if role.lower() == "admin" else False
    user = User(
        email=email,
        admin=admin,
        first_name="",
        last_name="",
    )
    session.add(user)
    session.commit()
    session.close()
    if agent_name != "" and agent_name is not None:
        add_agent(
            agent_name=agent_name,
            provider_settings=settings,
            commands=commands,
            user=email,
        )
    if training_urls != []:
        for url in training_urls:
            ApiClient.learn_url(agent_name=agent_name, url=url)
    if github_repos != []:
        for repo in github_repos:
            ApiClient.learn_github_repo(agent_name=agent_name, github_repo=repo)
    return {"status": "Success"}, 200


def verify_api_key(authorization: str = Header(None)):
    ENCRYPTION_SECRET = getenv("ENCRYPTION_SECRET")
    if getenv("AUTH_PROVIDER") == "magicalauth":
        ENCRYPTION_SECRET = f'{ENCRYPTION_SECRET}{datetime.now().strftime("%Y%m%d")}'
    authorization = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    if ENCRYPTION_SECRET:
        if authorization is None:
            raise HTTPException(
                status_code=401, detail="Authorization header is missing"
            )
        if authorization == ENCRYPTION_SECRET:
            return "ADMIN"
        try:
            if authorization == ENCRYPTION_SECRET:
                return "ADMIN"
            token = jwt.decode(
                jwt=authorization,
                key=ENCRYPTION_SECRET,
                algorithms=["HS256"],
            )
            db = get_session()
            user = db.query(User).filter(User.id == token["sub"]).first()
            db.close()
            return user
        except Exception as e:
            raise HTTPException(status_code=401, detail="Invalid API Key")
    else:
        return authorization


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


def encrypt(passphrase, data):
    passphrase = passphrase.encode("utf-8")
    salt = os.urandom(8)
    passphrase += salt
    key = md5(passphrase).digest()
    final_key = key
    while len(final_key) < 32 + 16:
        key = md5(key + passphrase).digest()
        final_key += key
    key_iv = final_key[: 32 + 16]
    key = key_iv[:32]
    iv = key_iv[32:]
    aes = AES.new(key, AES.MODE_CBC, iv)
    padded_data = data.encode("utf-8") + (16 - len(data) % 16) * bytes(
        [16 - len(data) % 16]
    )
    encrypted_data = aes.encrypt(padded_data)
    encrypted = b"Salted__" + salt + encrypted_data
    return base64.b64encode(encrypted).decode("utf-8")


def decrypt(passphrase, data):
    try:
        passphrase = passphrase.encode("utf-8")
        encrypted = base64.b64decode(data)
        assert encrypted[0:8] == b"Salted__"
        salt = encrypted[8:16]
        assert len(salt) == 8, len(salt)
        passphrase += salt
        key = md5(passphrase).digest()
        final_key = key
        while len(final_key) < 32 + 16:
            key = md5(key + passphrase).digest()
            final_key += key
        key_iv = final_key[: 32 + 16]
        key = key_iv[:32]
        iv = key_iv[32:]
        aes = AES.new(key, AES.MODE_CBC, iv)
        data = aes.decrypt(encrypted[16:])
        decrypted = data[: -(data[-1] if type(data[-1]) == int else ord(data[-1]))]
        return decrypted.decode("utf-8")
    except:
        return data


class MagicalAuth:
    def __init__(self, token: str = None):
        encryption_key = getenv("ENCRYPTION_SECRET")
        self.link = getenv("MAGIC_LINK_URL")
        self.encryption_key = f'{encryption_key}{datetime.now().strftime("%Y%m%d")}'
        self.token = (
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
                jwt=token, key=self.encryption_key, algorithms=["HS256"]
            )
            self.email = decoded["email"]
            self.token = token
        except:
            self.email = None
            self.token = None

    def user_exists(self, email: str = None):
        self.email = email.lower()
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        session.close()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
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
            .filter(FailedLogins.user_id == user.id)
            .filter(FailedLogins.created_at >= datetime.now() - timedelta(hours=24))
            .count()
        )
        session.close()
        return failed_logins

    def send_magic_link(self, ip_address, login: Login, referrer=None):
        self.email = login.email.lower()
        session = get_session()
        user = session.query(User).filter(User.email == self.email).first()
        session.close()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if not pyotp.TOTP(user.mfa_token).verify(login.token):
            self.add_failed_login(ip_address=ip_address)
            raise HTTPException(
                status_code=401, detail="Invalid MFA token. Please try again."
            )
        self.token = jwt.encode(
            {
                "sub": str(user.id),
                "email": self.email,
                "admin": user.admin,
                "exp": datetime.utcnow() + timedelta(hours=24),
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
        ):
            send_email(
                email=self.email,
                subject="Magic Link",
                body=f"<a href='{magic_link}'>Click here to log in</a>",
            )
        else:
            return magic_link
        # Upon clicking the link, the front end will call the login method and save the email and encrypted_id in the session
        return f"A login link has been sent to {self.email}, please check your email and click the link to log in. The link will expire in 24 hours."

    def login(self, ip_address):
        """ "
        Login method to verify the token and return the user object

        :param ip_address: IP address of the user
        :return: User object
        """
        session = get_session()
        failures = self.count_failed_logins()
        if failures >= 50:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts today. Please try again tomorrow.",
            )
        try:
            user_info = jwt.decode(
                jwt=self.token, key=self.encryption_key, algorithms=["HS256"]
            )
        except:
            self.add_failed_login(ip_address=ip_address)
            raise HTTPException(
                status_code=401,
                detail="Invalid login token. Please log out and try again.",
            )
        user_id = user_info["sub"]
        user = session.query(User).filter(User.id == user_id).first()
        session.close()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if str(user.id) == str(user_id):
            return user
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
        session.close()
        # Send registration webhook out to third party application such as AGiXT to create a user there.
        registration_webhook = getenv("REGISTRATION_WEBHOOK")
        if registration_webhook:
            try:
                requests.post(
                    registration_webhook,
                    json={"email": self.email},
                    headers={"Authorization": getenv("ENCRYPTION_SECRET")},
                )
            except Exception as e:
                pass
        # Return mfa_token for QR code generation
        return mfa_token

    def update_user(self, **kwargs):
        user = verify_api_key(self.token)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        session = get_session()
        user = session.query(User).filter(User.id == user.id).first()
        allowed_keys = list(UserInfo.__annotations__.keys())
        for key, value in kwargs.items():
            if key in allowed_keys:
                setattr(user, key, value)
        session.commit()
        session.close()
        return "User updated successfully"

    def delete_user(self):
        user = verify_api_key(self.token)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        session = get_session()
        user = session.query(User).filter(User.id == user.id).first()
        user.is_active = False
        session.commit()
        session.close()
        return "User deleted successfully"
