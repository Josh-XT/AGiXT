import base64
import hashlib
import os
from Models import (
    Detail,
    Login,
    Register,
    CompanyResponse,
    InvitationCreate,
    InvitationResponse,
    ToggleCommandPayload,
    ResponseMessage,
    NewCompanyInput,
    NewCompanyResponse,
    RenameCompanyInput,
    UpdateUserRole,
)
from fastapi import APIRouter, Request, Header, Depends, HTTPException
from MagicalAuth import (
    MagicalAuth,
    decrypt,
    encrypt,
    verify_api_key,
    impersonate_user,
    get_oauth_providers,
)
from Agent import Agent
from typing import List
from Globals import getenv
import logging
import pyotp


app = APIRouter()
logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


@app.post("/v1/user", summary="Register a new user", tags=["Auth"])
async def register(register: Register):
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


# Get invitations is auth.get_invitations(company_id)
@app.get("/v1/invitations", summary="Get all invitations", tags=["Companies"])
async def get_invitations(
    email: str = Depends(verify_api_key),
    company_id: str = None,
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        invites = auth.get_invitations()
        return {"invitations": invites}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while fetching the invitations: {str(e)}",
        )


# Get invitations is auth.get_invitations(company_id)
@app.get(
    "/v1/invitations/{company_id}",
    summary="Get all invitations for a company",
    tags=["Companies"],
)
async def get_invitations(
    email: str = Depends(verify_api_key),
    company_id: str = None,
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        invites = auth.get_invitations(company_id)
        return {"invitations": invites}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while fetching the invitations: {str(e)}",
        )


# delete invitation is auth.delete_invitation(invitation_id)
@app.delete(
    "/v1/invitation/{invitation_id}", summary="Delete an invitation", tags=["Companies"]
)
async def delete_invitation(
    invitation_id: str,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        auth.delete_invitation(invitation_id)
        return {"detail": "Invitation deleted successfully."}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while deleting the invitation: {str(e)}",
        )


@app.get(
    "/v1/user/exists",
    response_model=bool,
    summary="Check if user exists",
    tags=["Auth"],
)
async def get_user_exists(email: str) -> bool:
    try:
        return MagicalAuth().user_exists(email=email)
    except:
        return False


@app.get(
    "/v1/user",
    dependencies=[Depends(verify_api_key)],
    summary="Get user details",
    tags=["Auth"],
)
async def get_user(
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
        "id": auth.user_id,
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
    tags=["Auth"],
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
    tags=["Auth"],
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
    tags=["Auth"],
)
async def delete_user(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    MagicalAuth(token=authorization).delete_user()
    return Detail(detail="User deleted successfully.")


@app.post("/v1/invitations", response_model=InvitationResponse, tags=["Companies"])
async def create_invitations(
    invitation: InvitationCreate,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        return auth.create_invitation(invitation)
    except Exception as e:
        logging.error(f"Error in create_invitation endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while creating the invitation: {str(e)}",
        )


@app.post("/v1/user/verify/mfa", response_model=Detail, tags=["Auth"])
async def user_verify_mfa(request: Request, authorization: str = Header(None)):
    data = await request.json()
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    auth = MagicalAuth(token=token)
    if "code" not in data:
        raise HTTPException(status_code=400, detail="MFA code is required.")
    return {"detail": auth.verify_mfa(token=data["code"])}


@app.post("/v1/user/verify/sms", response_model=Detail, tags=["Auth"])
async def user_verify_sms(request: Request, authorization: str = Header(None)):
    data = await request.json()
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    auth = MagicalAuth(token=token)
    if "code" not in data:
        raise HTTPException(status_code=400, detail="SMS code is required.")
    return {"detail": auth.verify_sms(code=data["code"])}


@app.post("/v1/user/verify/email", response_model=Detail, tags=["Auth"])
async def user_verify_email(request: Request):
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


@app.post("/v1/user/mfa/sms", response_model=Detail, tags=["Auth"])
async def send_mfa_sms(request: Request):
    data = await request.json()
    email = data["email"]
    token = impersonate_user(email)
    auth = MagicalAuth(token=token)
    return {"detail": auth.send_sms_code()}


@app.post("/v1/user/mfa/email", response_model=Detail, tags=["Auth"])
async def send_mfa_email(request: Request):
    data = await request.json()
    email = data["email"]
    token = impersonate_user(email)
    auth = MagicalAuth(token=token)
    return {"detail": auth.send_email_code()}


@app.get(
    "/v1/oauth2/pkce-simple", summary="Generate PKCE code challenge", tags=["Auth"]
)
async def get_pkce_challenge_simple():
    """Generate code_verifier and code_challenge, embed verifier in state."""
    api_key = getenv("AGIXT_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500, detail="Server misconfiguration: Missing AGIXT_API_KEY"
        )
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")
    code_verifier_digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return {
        "code_challenge": base64.urlsafe_b64encode(code_verifier_digest)
        .decode("utf-8")
        .rstrip("="),
        "state": encrypt(getenv("AGIXT_API_KEY"), {"verifier": code_verifier}),
    }


@app.post(
    "/v1/oauth2/{provider}",
    response_model=Detail,
    summary="Login using OAuth2 provider",
    tags=["Auth"],
)
async def oauth_login(
    request: Request, provider: str = "microsoft", authorization: str = Header(None)
):
    data = await request.json()
    logging.info(f"OAuth2 login request received for {provider}: {data}")
    auth = MagicalAuth(token=authorization)
    email = auth.email
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    code_verifier = None
    state = data.get("state")
    if state:
        try:
            code_verifier = decrypt(getenv("AGIXT_API_KEY"), state).get("verifier")
        except Exception as e:
            logging.error(f"Failed to decode code_verifier from state: {str(e)}")

    magic_link = auth.sso(
        provider=provider.lower(),
        code=data["code"],
        ip_address=client_ip,
        referrer=data["referrer"] if "referrer" in data else getenv("APP_URI"),
        invitation_id=data["invitation_id"] if "invitation_id" in data else None,
        code_verifier=code_verifier,
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
    tags=["Auth"],
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
    tags=["Auth"],
)
async def get_providers(
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


# Get list of available oauth providers, client ID, their scopes, and login URLs
@app.get("/v1/oauth")
async def get_oauth():
    return {"providers": get_oauth_providers()}


@app.delete(
    "/v1/oauth2/{provider}",
    response_model=Detail,
    summary="Delete OAuth2 provider access token",
    tags=["Auth"],
)
async def delete_oauth_token(provider: str, authorization: str = Header(None)):
    auth = MagicalAuth(token=authorization)
    response = auth.disconnect_sso(provider_name=provider)
    return Detail(detail=response)


@app.get("/v1/companies", response_model=List[CompanyResponse], tags=["Companies"])
async def get_companies(
    email: str = Depends(verify_api_key), authorization: str = Header(None)
):
    try:
        auth = MagicalAuth(token=authorization)
        companies = auth.get_all_companies()
        return companies
    except Exception as e:
        logging.error(f"Error in get_companies endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while fetching companies: {str(e)}",
        )


@app.post("/v1/companies", response_model=NewCompanyResponse, tags=["Companies"])
async def create_company(
    company: NewCompanyInput,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        new_company = auth.create_company_with_agent(
            name=company.name,
            parent_company_id=company.parent_company_id,
            agent_name=company.agent_name,
        )
        return NewCompanyResponse(**new_company)
    except Exception as e:
        logging.error(f"Error in create_company endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while creating the company: {str(e)}",
        )


# delete company
@app.delete(
    "/v1/companies/{company_id}",
    response_model=Detail,
    summary="Delete a company",
    tags=["Companies"],
)
async def delete_company(
    company_id: str,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        auth.delete_company(company_id)
        return Detail(detail="Company deleted successfully.")
    except Exception as e:
        logging.error(f"Error in delete_company endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while deleting the company: {str(e)}",
        )


# delete user from company
@app.delete(
    "/v1/companies/{company_id}/users/{user_id}",
    response_model=Detail,
    summary="Remove a user from a company",
    tags=["Companies"],
)
async def delete_user_from_company(
    company_id: str,
    user_id: str,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        result = auth.delete_user_from_company(company_id, user_id)
        return Detail(detail=result)
    except Exception as e:
        logging.error(f"Error in delete_user_from_company endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while removing the user from the company: {str(e)}",
        )


@app.get(
    "/v1/companies/{company_id}/extensions",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
)
async def get_company_extensions(
    company_id: str = None,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    ApiClient = auth.get_company_agent_session(company_id=company_id)
    user_data = ApiClient.get_user()
    agent = Agent(agent_name="AGiXT", user=user_data["email"], ApiClient=ApiClient)
    extensions = agent.get_agent_extensions()
    return {"extensions": extensions}


@app.patch(
    "/v1/companies/{company_id}/command",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
)
async def toggle_command(
    company_id: str,
    payload: ToggleCommandPayload,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    ApiClient = auth.get_company_agent_session(company_id=company_id)
    token = ApiClient.headers.get("Authorization")
    company_auth = MagicalAuth(token=token)
    agent = Agent(agent_name="AGiXT", user=company_auth.email, ApiClient=ApiClient)
    update_config = agent.update_agent_config(
        new_config={payload.command_name: payload.enable}, config_key="commands"
    )
    return ResponseMessage(message=update_config)


# Rename company
@app.put(
    "/v1/companies/{company_id}",
    response_model=CompanyResponse,
    summary="Rename a company",
    tags=["Companies"],
)
async def rename_company(
    company_id: str,
    company_name: RenameCompanyInput,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    return auth.rename_company(company_id, company_name.name)


@app.put(
    "/v1/user/role",
    response_model=Detail,
    summary="Update user role in a company",
    tags=["Companies"],
)
async def update_user_role(
    role: UpdateUserRole,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        auth.update_user_role(
            company_id=role.company_id, user_id=role.user_id, role_id=role.role_id
        )
        return Detail(detail="User role updated successfully.")
    except Exception as e:
        logging.error(f"Error in update_user_role endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while updating the user role: {str(e)}",
        )
