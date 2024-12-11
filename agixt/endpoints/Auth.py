from fastapi import APIRouter, Request, Header, Depends, HTTPException
from Models import Detail, Login, UserInfo, Register
from MagicalAuth import MagicalAuth, verify_api_key, is_agixt_admin
from DB import get_session, User, UserPreferences
from agixtsdk import AGiXTSDK
from Models import WebhookUser, WebhookModel
from Globals import getenv
import pyotp
import logging

app = APIRouter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


@app.post("/v1/user", tags=["User"], summary="Register a new user")
def register(register: Register):
    mfa_token = MagicalAuth().register(new_user=register)
    totp = pyotp.TOTP(mfa_token)
    otp_uri = totp.provisioning_uri(name=register.email, issuer_name=getenv("APP_NAME"))
    return {"otp_uri": otp_uri}


@app.get(
    "/v1/user/exists",
    tags=["User"],
    response_model=bool,
    summary="Check if user exists",
)
def get_user(email: str) -> bool:
    try:
        return MagicalAuth().user_exists(email=email)
    except:
        return False


@app.get(
    "/v1/user",
    tags=["User"],
    dependencies=[Depends(verify_api_key)],
    summary="Get user details",
)
def log_in(
    request: Request,
    authorization: str = Header(None),
):
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    auth = MagicalAuth(token=token)
    logging.info(f"Forwarded for: {request.headers.get('X-Forwarded-For')}")
    logging.info(f"Client IP: {request.client.host}")
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    user_data = auth.login(ip_address=client_ip)
    user_preferences = auth.get_user_preferences()
    return {
        "email": user_data.email,
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        **user_preferences,
    }


@app.post(
    "/v1/login",
    tags=["User"],
    response_model=Detail,
    summary="Login with email and OTP token",
)
async def send_magic_link(request: Request, login: Login):
    auth = MagicalAuth()
    data = await request.json()
    referrer = None
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    if "referrer" in data:
        referrer = data["referrer"]
    magic_link = auth.send_magic_link(
        ip_address=client_ip, login=login, referrer=referrer
    )
    return Detail(detail=magic_link)


@app.put(
    "/v1/user",
    tags=["User"],
    dependencies=[Depends(verify_api_key)],
    response_model=Detail,
    summary="Update user details",
)
async def update_user(request: Request, authorization: str = Header(None)):
    data = await request.json()
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    user = MagicalAuth(token=authorization).update_user(ip_address=client_ip, **data)
    return Detail(detail=user)


# Delete user
@app.delete(
    "/v1/user",
    tags=["User"],
    dependencies=[Depends(verify_api_key)],
    response_model=Detail,
    summary="Delete user",
)
def delete_user(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    MagicalAuth(token=authorization).delete_user()
    return Detail(detail="User deleted successfully.")


# Webhook user creations from other applications
@app.post("/api/user", tags=["User"])
async def createuser(account: WebhookUser):
    email = account.email.lower()
    agent_name = account.agent_name
    settings = account.settings
    commands = account.commands
    training_urls = account.training_urls
    github_repos = account.github_repos
    zip_file_content = account.zip_file_content
    sdk = AGiXTSDK(base_uri=getenv("AGIXT_URI"))
    user_exists = sdk.user_exists(email=email)
    if user_exists:
        return {"status": "User already exists"}, 200
    sdk.register_user(email=email, first_name="User", last_name="Name")
    if agent_name != "" and agent_name is not None:
        sdk.add_agent(
            agent_name=agent_name,
            settings=settings,
            commands=commands,
            training_urls=training_urls,
        )
    if github_repos != []:
        for repo in github_repos:
            sdk.learn_github_repo(agent_name=agent_name, github_repo=repo)
    if zip_file_content != "":
        sdk.learn_file(
            agent_name=agent_name,
            file_name="training_data.zip",
            file_content=zip_file_content,
        )
    return {"status": "Success"}, 200


@app.post(
    "/v1/oauth2/{provider}",
    tags=["User"],
    response_model=Detail,
    summary="Login using OAuth2 provider",
)
async def oauth_login(request: Request, provider: str):
    data = await request.json()
    auth = MagicalAuth()
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    magic_link = auth.sso(
        provider=provider.lower(),
        code=data["code"],
        ip_address=client_ip,
        referrer=data["referrer"] if "referrer" in data else getenv("MAGIC_LINK_URL"),
    )
    return {"detail": magic_link, "email": auth.email, "token": auth.token}


@app.put(
    "/v1/oauth2/{provider}",
    tags=["User"],
    dependencies=[Depends(verify_api_key)],
    response_model=Detail,
    summary="Update OAuth2 provider access token",
)
async def update_oauth_token(
    request: Request, provider: str, authorization: str = Header(None)
):
    data = await request.json()
    auth = MagicalAuth(token=authorization)
    response = auth.update_sso(
        provider_name=provider,
        account_name=data["account_name"],
        token_expires_at=data["token_expires_at"],
        access_token=data["access_token"],
        refresh_token=data["refresh_token"] if "refresh_token" in data else None,
    )
    return Detail(detail=response)


@app.delete(
    "/v1/oauth2/{provider}",
    tags=["User"],
    dependencies=[Depends(verify_api_key)],
    response_model=Detail,
    summary="Delete OAuth2 provider access token",
)
async def delete_oauth_token(provider: str, authorization: str = Header(None)):
    auth = MagicalAuth(token=authorization)
    response = auth.disconnect_sso(provider_name=provider)
    return Detail(detail=response)
