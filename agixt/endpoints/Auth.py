import base64
import hashlib
import json
import os
from Models import (
    Detail,
    Login,
    Register,
    CompanyResponse,
    InvitationCreate,
    InvitationCreateByRole,
    InvitationResponse,
    ToggleCommandPayload,
    ToggleExtensionCommandsPayload,
    ResponseMessage,
    NewCompanyInput,
    NewCompanyResponse,
    RenameCompanyInput,
    UpdateCompanyInput,
    UpdateUserRole,
)
from DB import TokenBlacklist, get_session, default_roles
from fastapi import APIRouter, Request, Header, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from MagicalAuth import (
    MagicalAuth,
    decrypt,
    encrypt,
    verify_api_key,
    impersonate_user,
    get_oauth_providers,
)
from middleware import send_discord_new_user_notification
from Agent import Agent
from typing import List
from Globals import getenv
import logging
import pyotp
import jwt
from datetime import datetime


app = APIRouter()
logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


@app.post("/v1/user", summary="Register a new user", tags=["Auth"])
async def register(register: Register):
    auth = MagicalAuth()

    # Debug logging
    import logging

    logging.info(
        f"[REGISTER DEBUG] email={register.email}, invitation_id='{register.invitation_id}'"
    )

    # Check if user exists (active OR inactive)
    user_exists_any = auth.user_exists_any(email=register.email)
    user_exists_active = auth.user_exists(email=register.email)
    logging.info(
        f"[REGISTER DEBUG] user_exists_any={user_exists_any}, user_exists_active={user_exists_active}"
    )

    if user_exists_any:
        invitation_id = (
            register.invitation_id.strip() if register.invitation_id else None
        )

        if user_exists_active:
            # User exists and is active - check if they're already in the invited company
            if invitation_id:
                logging.info(
                    f"[REGISTER DEBUG] Active user with invitation, calling handle_existing_user_invitation"
                )
                result = auth.handle_existing_user_invitation(
                    email=register.email, invitation_id=invitation_id
                )
                logging.info(
                    f"[REGISTER DEBUG] handle_existing_user_invitation result: {result}"
                )
                if result.get("already_in_company"):
                    raise HTTPException(
                        status_code=409,
                        detail="User is already a member of this company.",
                    )
                elif result.get("added_to_company"):
                    return result
            # No invitation - user already exists
            raise HTTPException(
                status_code=400, detail="User with this email already exists."
            )
        else:
            # User exists but is inactive - reactivate them if they have an invitation
            if invitation_id:
                logging.info(
                    f"[REGISTER DEBUG] Inactive user with invitation, calling reactivate_user_with_invitation"
                )
                result = auth.reactivate_user_with_invitation(
                    email=register.email,
                    invitation_id=invitation_id,
                    first_name=register.first_name,
                    last_name=register.last_name,
                )
                logging.info(
                    f"[REGISTER DEBUG] reactivate_user_with_invitation result: {result}"
                )
                if result.get("error"):
                    raise HTTPException(status_code=400, detail=result["error"])
                if result.get("already_in_company"):
                    raise HTTPException(
                        status_code=409,
                        detail="User is already a member of this company.",
                    )
                # Return success with magic link for reactivated user
                return result
            else:
                # No invitation - tell them to contact admin
                raise HTTPException(
                    status_code=400,
                    detail="An inactive account exists with this email. Please contact your administrator.",
                )

    result = auth.register(
        new_user=register,
        invitation_id=register.invitation_id if register.invitation_id else None,
    )
    if result["status_code"] != 200:
        raise HTTPException(status_code=result["status_code"], detail=result["error"])
    # Send Discord notification for new user registration
    await send_discord_new_user_notification(email=register.email)
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


# Create invitation for a specific company using role name
@app.post(
    "/v1/companies/{company_id}/invitations",
    response_model=InvitationResponse,
    summary="Create an invitation for a company",
    tags=["Companies"],
)
async def create_company_invitation(
    company_id: str,
    invitation: InvitationCreateByRole,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)

        # Convert role name to role_id
        role_id = 3  # Default to "user"
        role_name = invitation.role.lower().strip() if invitation.role else "user"
        for role in default_roles:
            if role["name"] == role_name:
                role_id = role["id"]
                break

        # Create the internal invitation object
        internal_invitation = InvitationCreate(
            email=invitation.email,
            company_id=company_id,
            role_id=role_id,
        )

        return auth.create_invitation(internal_invitation)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in create_company_invitation endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while creating the invitation: {str(e)}",
        )


@app.get(
    "/v1/user/exists",
    response_model=bool,
    summary="Check if user exists",
    tags=["Auth"],
)
async def get_user_exists(email: str) -> bool:
    try:
        # Use user_exists_any to check if user registered (regardless of payment status)
        # This allows users who registered but haven't paid to still login and complete payment
        return MagicalAuth().user_exists_any(email=email)
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
    if_none_match: str = Header(None, alias="If-None-Match"),
):
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    auth = MagicalAuth(token=token)
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host

    # Use optimized single-session method that fetches everything at once
    data = auth.get_user_data_optimized(ip_address=client_ip)
    user_data = data["user"]
    user_preferences = data["preferences"]
    companies = data["companies"]  # Already includes agents and scopes

    response_data = {
        "id": auth.user_id,
        "email": user_data.email,
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        "companies": companies,
        "tos_accepted_at": (
            user_data.tos_accepted_at.isoformat() if user_data.tos_accepted_at else None
        ),
        **user_preferences,
    }

    # Generate ETag from response data hash (excludes volatile fields like tokens)
    # We hash a subset of data that matters for UI rendering
    etag_data = {
        "id": response_data["id"],
        "email": response_data["email"],
        "first_name": response_data["first_name"],
        "last_name": response_data["last_name"],
        "companies": response_data["companies"],
        "tos_accepted_at": response_data.get("tos_accepted_at"),
    }
    etag_string = json.dumps(etag_data, sort_keys=True, default=str)
    etag = f'"{hashlib.sha256(etag_string.encode()).hexdigest()}"'

    # If client sent If-None-Match and it matches, return 304 Not Modified
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})

    # Return full response with ETag header
    return JSONResponse(
        content=response_data,
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=0, must-revalidate",
        },
    )


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


@app.post(
    "/v1/logout",
    dependencies=[Depends(verify_api_key)],
    response_model=Detail,
    summary="Logout user and blacklist JWT token",
    tags=["Auth"],
)
async def logout_user(
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Logout user by blacklisting their JWT token until its natural expiration.
    This immediately invalidates the token across all sessions.
    """
    if not authorization:
        raise HTTPException(status_code=400, detail="Authorization token is required.")

    # Clean the token
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")

    # Decode token to get expiration time
    try:
        AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", "")
        decoded = jwt.decode(
            jwt=token,
            key=AGIXT_API_KEY,
            algorithms=["HS256"],
            options={"verify_exp": False},  # Don't verify expiration for blacklisting
        )
        user_id = decoded["sub"]
        expires_at = datetime.fromtimestamp(decoded["exp"])

    except jwt.InvalidTokenError as e:
        logging.error(f"Invalid token for blacklisting: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid token.")

    # Add token to blacklist
    session = get_session()
    try:
        # Check if token is already blacklisted
        existing_blacklist = (
            session.query(TokenBlacklist).filter(TokenBlacklist.token == token).first()
        )

        if existing_blacklist:
            session.close()
            return Detail(detail="User logged out successfully.")

        # Add new blacklist entry
        blacklist_entry = TokenBlacklist(
            token=token, user_id=user_id, expires_at=expires_at
        )
        session.add(blacklist_entry)
        session.commit()

        # Invalidate the token validation cache for this token
        from MagicalAuth import invalidate_token_validation_cache

        invalidate_token_validation_cache(token)

        # Cleanup expired tokens (optional - can be done periodically)
        expired_tokens = (
            session.query(TokenBlacklist)
            .filter(TokenBlacklist.expires_at < datetime.now())
            .all()
        )

        for expired_token in expired_tokens:
            session.delete(expired_token)

        session.commit()

        logging.info(
            f"Token blacklisted for user {user_id}. Cleaned up {len(expired_tokens)} expired tokens."
        )

    except Exception as e:
        session.rollback()
        logging.error(f"Error blacklisting token: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"An error occurred during logout: {str(e)}"
        )
    finally:
        session.close()

    return Detail(detail="User logged out successfully.")


@app.post("/v1/invitations", response_model=InvitationResponse, tags=["Companies"])
async def create_invitations(
    invitation: InvitationCreate,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        return auth.create_invitation(invitation)
    except HTTPException:
        raise  # Re-raise HTTPExceptions with their original status code
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


@app.post(
    "/v1/user/mfa/reset",
    dependencies=[Depends(verify_api_key)],
    summary="Reset MFA token",
    description="Resets the user's MFA token and returns a new OTP URI for setting up the authenticator app.",
    tags=["Auth"],
)
async def reset_mfa(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Reset the user's MFA token. This will invalidate any existing authenticator app
    setup and require the user to set up MFA again with a new token.
    Returns the new OTP URI for setting up the authenticator app.
    """
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    auth = MagicalAuth(token=token)

    # Reset the MFA token
    auth.reset_mfa()

    # Get the new MFA token to generate the OTP URI
    from DB import get_session, User

    session = get_session()
    try:
        db_user = session.query(User).filter(User.id == auth.user_id).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        mfa_token = db_user.mfa_token
        totp = pyotp.TOTP(mfa_token)
        otp_uri = totp.provisioning_uri(
            name=db_user.email, issuer_name=getenv("APP_NAME")
        )

        return {"detail": "MFA has been reset.", "otp_uri": otp_uri}
    finally:
        session.close()


@app.post(
    "/v1/user/tos/accept",
    dependencies=[Depends(verify_api_key)],
    response_model=Detail,
    summary="Accept Terms of Service",
    tags=["Auth"],
)
async def accept_tos(
    request: Request,
    authorization: str = Header(None),
):
    """Record that the user has accepted the Terms of Service."""
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    auth = MagicalAuth(token=token)
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    user_data = auth.login(ip_address=client_ip)

    # Update the user's TOS acceptance timestamp
    from DB import get_session, User

    session = get_session()
    try:
        user = session.query(User).filter(User.id == auth.user_id).first()
        if user:
            user.tos_accepted_at = datetime.now()
            session.commit()
            return Detail(detail="Terms of Service accepted successfully.")
        else:
            raise HTTPException(status_code=404, detail="User not found")
    finally:
        session.close()


@app.get(
    "/v1/oauth2/pkce-simple", summary="Generate PKCE code challenge", tags=["Auth"]
)
async def get_pkce_challenge_simple():
    """Generate code_verifier and code_challenge, embed verifier in state."""
    api_key = os.getenv("AGIXT_API_KEY", "")
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
        "state": encrypt(os.getenv("AGIXT_API_KEY", ""), {"verifier": code_verifier}),
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
    auth = MagicalAuth(token=authorization)
    email = auth.email
    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    code_verifier = None
    state = data.get("state")
    if state:
        try:
            code_verifier = decrypt(os.getenv("AGIXT_API_KEY", ""), state).get(
                "verifier"
            )
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
            status=company.status,
            address=company.address,
            phone_number=company.phone_number,
            email=company.email,
            website=company.website,
            city=company.city,
            state=company.state,
            zip_code=company.zip_code,
            country=company.country,
            notes=company.notes,
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
    # Use company's auth email (from ApiClient token) not the user's email
    # This ensures we get the company agent's extensions, not the user's
    token = ApiClient.headers.get("Authorization")
    company_auth = MagicalAuth(token=token)
    agent = Agent(
        agent_name=auth.get_company_agent_name(),
        user=company_auth.email,
        ApiClient=ApiClient,
    )
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
    agent = Agent(
        agent_name=auth.get_company_agent_name(),
        user=company_auth.email,
        ApiClient=ApiClient,
    )
    update_config = agent.update_agent_config(
        new_config={payload.command_name: payload.enable}, config_key="commands"
    )
    return ResponseMessage(message=update_config)


@app.patch(
    "/v1/companies/{company_id}/extension/commands",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Toggle all commands for a specific extension for company agent",
    description="Enables or disables all commands for a specific extension for a company's team agent.",
)
async def toggle_company_extension_commands(
    company_id: str,
    payload: ToggleExtensionCommandsPayload,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    ApiClient = auth.get_company_agent_session(company_id=company_id)
    if not ApiClient:
        raise HTTPException(
            status_code=404, detail="Company not found or access denied"
        )
    token = ApiClient.headers.get("Authorization")
    company_auth = MagicalAuth(token=token)
    agent = Agent(
        agent_name=auth.get_company_agent_name(),
        user=company_auth.email,
        ApiClient=ApiClient,
    )

    # Get all extensions to find the commands for the specified extension
    extensions = agent.get_agent_extensions()

    # Find the extension and get all its commands
    extension_commands = []
    for extension in extensions:
        if extension["extension_name"] == payload.extension_name:
            for command in extension["commands"]:
                extension_commands.append(command["friendly_name"])
            break

    if not extension_commands:
        raise HTTPException(
            status_code=404,
            detail=f"Extension '{payload.extension_name}' not found or has no commands",
        )

    # Create a config update for all commands in the extension
    new_config = {command: payload.enable for command in extension_commands}

    # Update the agent configuration
    update_config = agent.update_agent_config(
        new_config=new_config, config_key="commands"
    )

    return ResponseMessage(
        message=f"Successfully {'enabled' if payload.enable else 'disabled'} {len(extension_commands)} commands for extension '{payload.extension_name}'"
    )


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


@app.patch(
    "/v1/companies/{company_id}",
    response_model=CompanyResponse,
    summary="Update company details",
    tags=["Companies"],
)
async def update_company(
    company_id: str,
    company_details: UpdateCompanyInput,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        auth = MagicalAuth(token=authorization)
        return auth.update_company(
            company_id=company_id,
            name=company_details.name,
            status=company_details.status,
            address=company_details.address,
            phone_number=company_details.phone_number,
            email=company_details.email,
            website=company_details.website,
            city=company_details.city,
            state=company_details.state,
            zip_code=company_details.zip_code,
            country=company_details.country,
            notes=company_details.notes,
        )
    except Exception as e:
        logging.error(f"Error in update_company endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while updating the company: {str(e)}",
        )


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
