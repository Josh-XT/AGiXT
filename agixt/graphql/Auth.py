from typing import List, Optional, Dict, Any
import strawberry
from fastapi import HTTPException
from Models import (
    Detail,
    Login,
    Register,
    CompanyResponse,
    InvitationCreate,
    InvitationResponse,
    ToggleCommandPayload,
    ResponseMessage,
)
from endpoints.Auth import (
    register as rest_register,
    get_invitations as rest_get_invitations,
    delete_invitation as rest_delete_invitation,
    get_user as rest_get_user,
    get_user_exists as rest_get_user_exists,
    send_magic_link as rest_send_magic_link,
    update_user as rest_update_user,
    delete_user as rest_delete_user,
    update_company as rest_update_company,
    create_invitations as rest_create_invitation,
    user_verify_mfa as rest_verify_mfa,
    user_verify_sms as rest_verify_sms,
    user_verify_email as rest_verify_email,
    send_mfa_sms as rest_send_mfa_sms,
    send_mfa_email as rest_send_mfa_email,
    oauth_login as rest_oauth_login,
    update_oauth_token as rest_update_oauth_token,
    get_oauth_providers as rest_get_oauth_providers,
    delete_oauth_token as rest_delete_oauth_token,
    get_companies as rest_get_companies,
    create_company as rest_create_company,
    get_company_extensions as rest_get_company_extensions,
    toggle_command as rest_toggle_command,
)


# Convert Pydantic models to Strawberry types
@strawberry.experimental.pydantic.type(model=CompanyResponse)
class CompanyResponseType:
    id: str
    name: str
    company_id: Optional[str]
    users: List[Any]
    children: List["CompanyResponseType"]


@strawberry.experimental.pydantic.type(model=InvitationResponse)
class InvitationResponseType:
    id: str
    email: str
    company_id: str
    role_id: int
    inviter_id: str
    created_at: str
    is_accepted: bool


@strawberry.experimental.pydantic.type(model=Detail)
class DetailType:
    detail: str


@strawberry.experimental.pydantic.type(model=ResponseMessage)
class ResponseMessageType:
    message: str


# Input types
@strawberry.input
class RegisterInput:
    email: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    invitation_id: Optional[str] = ""


@strawberry.input
class LoginInput:
    email: str
    token: str


@strawberry.input
class InvitationCreateInput:
    email: str
    company_id: Optional[str] = None
    role_id: int


@strawberry.type
class Query:
    @strawberry.field
    async def user_exists(self, email: str) -> bool:
        """Check if a user exists"""
        return await rest_get_user_exists(email=email)

    @strawberry.field
    async def get_user(self, info) -> Dict[str, Any]:
        """Get user details"""
        return await rest_get_user(
            request=info.context["request"],
            authorization=info.context["request"].headers.get("authorization"),
        )

    @strawberry.field
    async def get_invitations(
        self, info, company_id: Optional[str] = None
    ) -> Dict[str, List[Any]]:
        """Get invitations"""
        return await rest_get_invitations(
            email=await get_user_from_context(info),
            company_id=company_id,
            authorization=info.context["request"].headers.get("authorization"),
        )

    @strawberry.field
    async def get_companies(self, info) -> List[CompanyResponseType]:
        """Get all companies"""
        companies = await rest_get_companies(
            email=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return [CompanyResponseType.from_pydantic(company) for company in companies]

    @strawberry.field
    async def get_company_extensions(
        self, info, company_id: str
    ) -> Dict[str, List[Any]]:
        """Get company extensions"""
        return await rest_get_company_extensions(
            company_id=company_id,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )

    @strawberry.field
    async def get_oauth_providers(self, info) -> List[str]:
        """Get OAuth providers"""
        return await rest_get_oauth_providers(
            email=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def register(self, register: RegisterInput) -> Dict[str, str]:
        """Register a new user"""
        return await rest_register(register=Register(**register.__dict__))

    @strawberry.mutation
    async def login(self, info, login: LoginInput) -> DetailType:
        """Login with email and OTP token"""
        result = await rest_send_magic_link(
            request=info.context["request"], login=Login(**login.__dict__)
        )
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def update_user(self, info, data: Dict[str, Any]) -> DetailType:
        """Update user details"""
        result = await rest_update_user(
            request=info.context["request"],
            authorization=info.context["request"].headers.get("authorization"),
            email=await get_user_from_context(info),
        )
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def delete_user(self, info) -> DetailType:
        """Delete user"""
        result = await rest_delete_user(
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def create_company(
        self, info, name: str, parent_company_id: Optional[str] = None
    ) -> CompanyResponseType:
        """Create a new company"""
        result = await rest_create_company(
            name=name,
            parent_company_id=parent_company_id,
            email=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return CompanyResponseType.from_pydantic(result)

    @strawberry.mutation
    async def update_company(
        self, info, company_id: str, name: str
    ) -> CompanyResponseType:
        """Update company details"""
        result = await rest_update_company(
            company_id=company_id,
            name=name,
            email=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return CompanyResponseType.from_pydantic(result)

    @strawberry.mutation
    async def create_invitation(
        self, info, invitation: InvitationCreateInput
    ) -> InvitationResponseType:
        """Create a new invitation"""
        result = await rest_create_invitation(
            invitation=InvitationCreate(**invitation.__dict__),
            email=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return InvitationResponseType.from_pydantic(result)

    @strawberry.mutation
    async def delete_invitation(self, info, invitation_id: str) -> DetailType:
        """Delete an invitation"""
        result = await rest_delete_invitation(
            invitation_id=invitation_id,
            email=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def verify_mfa(self, info, code: str) -> DetailType:
        """Verify MFA code"""
        result = await rest_verify_mfa(
            request=info.context["request"],
            authorization=info.context["request"].headers.get("authorization"),
        )
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def verify_sms(self, info, code: str) -> DetailType:
        """Verify SMS code"""
        result = await rest_verify_sms(
            request=info.context["request"],
            authorization=info.context["request"].headers.get("authorization"),
        )
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def verify_email(
        self, info, email: str, code: Optional[str] = None
    ) -> DetailType:
        """Verify email address"""
        result = await rest_verify_email(request=info.context["request"])
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def send_mfa_sms(self, info) -> DetailType:
        """Send MFA SMS code"""
        result = await rest_send_mfa_sms(request=info.context["request"])
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def send_mfa_email(self, info) -> DetailType:
        """Send MFA email code"""
        result = await rest_send_mfa_email(request=info.context["request"])
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def oauth_login(
        self,
        info,
        provider: str,
        code: str,
        referrer: Optional[str] = None,
        invitation_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Login using OAuth2 provider"""
        result = await rest_oauth_login(
            request=info.context["request"],
            provider=provider,
            authorization=info.context["request"].headers.get("authorization"),
        )
        return result

    @strawberry.mutation
    async def update_oauth_token(
        self,
        info,
        provider: str,
        access_token: str,
        refresh_token: Optional[str] = None,
    ) -> DetailType:
        """Update OAuth token"""
        result = await rest_update_oauth_token(
            request=info.context["request"],
            provider=provider,
            authorization=info.context["request"].headers.get("authorization"),
        )
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def delete_oauth_token(self, info, provider: str) -> DetailType:
        """Delete OAuth token"""
        result = await rest_delete_oauth_token(
            provider=provider,
            authorization=info.context["request"].headers.get("authorization"),
        )
        return DetailType.from_pydantic(result)

    @strawberry.mutation
    async def toggle_company_command(
        self, info, company_id: str, payload: ToggleCommandPayload
    ) -> ResponseMessageType:
        """Toggle company command"""
        result = await rest_toggle_command(
            company_id=company_id,
            payload=payload,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return ResponseMessageType.from_pydantic(result)


async def get_user_from_context(info):
    """Helper function to get user from context"""
    request = info.context["request"]
    try:
        from ApiClient import verify_api_key

        return await verify_api_key(request)
    except HTTPException as e:
        raise Exception(str(e.detail))


schema = strawberry.Schema(query=Query, mutation=Mutation)
