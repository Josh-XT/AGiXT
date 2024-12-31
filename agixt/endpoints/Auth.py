from Models import (
    Detail,
    Login,
    Register,
)
from fastapi import APIRouter, Request, Header, Depends, HTTPException
from MagicalAuth import MagicalAuth, verify_api_key, impersonate_user
from typing import List
from Globals import getenv
import logging
import pyotp


app = APIRouter(tags=["Auth"])
logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


@app.post("/v1/user", summary="Register a new user")
def register(register: Register):
    auth = MagicalAuth()
    user_exists = auth.user_exists(email=register.email)
    if user_exists:
        raise HTTPException(
            status_code=400, detail="User with this email already exists."
        )
    result = auth.register(
        new_user=register,
        invitation_id=register.invitation_id if register.invitation_id else None,
    )
    if result["status_code"] != 200:
        raise HTTPException(status_code=result["status_code"], detail=result["error"])
    mfa_token = result["mfa_token"]
    totp = pyotp.TOTP(mfa_token)
    otp_uri = totp.provisioning_uri(name=register.email, issuer_name=getenv("APP_NAME"))
    # Generate and return login link
    login = Login(email=register.email, token=totp.now())
    magic_link = auth.send_magic_link(
        ip_address="registration", login=login, send_link=False
    )
    return {"otp_uri": otp_uri, "magic_link": magic_link}


@app.get(
    "/v1/user/exists",
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
    companies = auth.get_user_companies_with_roles()
    return {
        "email": user_data.email,
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        "companies": companies,
        **user_preferences,
    }


@app.post(
    "/v1/login",
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
    dependencies=[Depends(verify_api_key)],
    response_model=Detail,
    summary="Update user details",
)
async def update_user(
    request: Request, authorization: str = Header(None), email=Depends(verify_api_key)
):
    data = await request.json()
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    user = MagicalAuth(token=authorization).update_user(ip_address=client_ip, **data)
    return Detail(detail=user)


# Delete user
@app.delete(
    "/v1/user",
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


@app.post("/v1/user/verify/mfa", response_model=Detail)
async def user_verify_mfa(request: Request, authorization: str = Header(None)):
    data = await request.json()
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    auth = MagicalAuth(token=token)
    if "code" not in data:
        raise HTTPException(status_code=400, detail="MFA code is required.")
    return {"detail": auth.verify_mfa(token=data["code"])}


@app.post("/v1/user/verify/sms", response_model=Detail)
async def user_verify_sms(request: Request, authorization: str = Header(None)):
    data = await request.json()
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    auth = MagicalAuth(token=token)
    if "code" not in data:
        raise HTTPException(status_code=400, detail="SMS code is required.")
    return {"detail": auth.verify_sms(code=data["code"])}


@app.post("/v1/user/verify/email", response_model=Detail)
async def user_verify(request: Request):
    data = await request.json()
    if "email" not in data:
        raise HTTPException(status_code=400, detail="Email is required.")
    email = (
        str(data["email"])
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
    token = impersonate_user(email.lower())
    auth = MagicalAuth(token=token)
    if "code" not in data:
        auth.send_email_verification_link()
        raise HTTPException(
            status_code=400,
            detail="Verification code is required, it has been sent via email.",
        )
    return {"detail": auth.verify_email_address(code=data["code"])}


@app.post("/v1/user/mfa/sms", response_model=Detail)
async def send_mfa_sms(request: Request):
    data = await request.json()
    email = data["email"]
    token = impersonate_user(email)
    auth = MagicalAuth(token=token)
    return auth.send_sms_code()


@app.post("/v1/user/mfa/email", response_model=Detail)
async def send_mfa_email(request: Request):
    data = await request.json()
    email = data["email"]
    token = impersonate_user(email)
    auth = MagicalAuth(token=token)
    return auth.send_email_code()


@app.post(
    "/v1/oauth2/{provider}",
    response_model=Detail,
    summary="Login using OAuth2 provider",
)
async def oauth_login(
    request: Request, provider: str = "microsoft", authorization: str = Header(None)
):
    logging.info("OAuth login request received")
    logging.info(f"Authorization header: {authorization}")
    logging.info(f"All headers: {dict(request.headers)}")
    data = await request.json()
    logging.info(f"OAuth2 login request received for {provider}: {data}")
    auth = MagicalAuth(token=authorization)
    email = auth.email
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    magic_link = auth.sso(
        provider=provider.lower(),
        code=data["code"],
        ip_address=client_ip,
        referrer=data["referrer"] if "referrer" in data else getenv("APP_URI"),
        invitation_id=data["invitation_id"] if "invitation_id" in data else None,
    )

    # If user is already logged in (has authorization token)
    if authorization and str(authorization).strip().lower() not in ["", "none", "null"]:
        return {
            "detail": "OAuth provider connected successfully",
            "email": email,
            "token": authorization,
        }

    # Only return new token and email for new logins
    return {"detail": magic_link, "email": auth.email, "token": auth.token}


@app.put(
    "/v1/oauth2/{provider}",
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
        provider=provider,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"] if "refresh_token" in data else None,
    )
    logging.info(f"[{provider}] {response}")
    return Detail(detail=response)


@app.get(
    "/v1/oauth2",
    response_model=List[str],
    summary="List of currently connected OAuth2 providers for the user",
)
async def get_oauth_providers(
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        return auth.get_sso_connections()
    except Exception as e:
        logging.error(f"Error in get_oauth_providers endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while fetching OAuth2 providers: {str(e)}",
        )


@app.delete(
    "/v1/oauth2/{provider}",
    response_model=Detail,
    summary="Delete OAuth2 provider access token",
)
async def delete_oauth_token(provider: str, authorization: str = Header(None)):
    auth = MagicalAuth(token=authorization)
    response = auth.disconnect_sso(provider_name=provider)
    return Detail(detail=response)
