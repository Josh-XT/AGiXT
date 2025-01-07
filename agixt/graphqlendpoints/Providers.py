from typing import List, Dict, Any, Optional
import strawberry
from fastapi import Depends, HTTPException
from Models import (
    ProvidersResponse,
    ProviderSettings,
    ProviderWithSettings,
    EmbedderResponse,
)
from Providers import (
    get_provider_options,
    get_providers,
    get_providers_with_settings,
    get_providers_by_service,
    get_providers_with_details,
)
from ApiClient import verify_api_key
from endpoints.Provider import (
    get_provider_settings as rest_get_provider_settings,
    get_all_providers as rest_get_all_providers,
    get_providers_by_service_name as rest_get_providers_by_service,
    get_embed_providers as rest_get_embed_providers,
    get_embedder_info as rest_get_embedder_info,
)


# Convert existing models to Strawberry types
@strawberry.experimental.pydantic.type(model=ProvidersResponse)
class ProvidersResponseType:
    providers: List[str]


@strawberry.experimental.pydantic.type(model=ProviderSettings)
class ProviderSettingsType:
    settings: Dict[str, Any]


@strawberry.experimental.pydantic.type(model=ProviderWithSettings)
class ProviderWithSettingsType:
    providers: List[Dict[str, Dict[str, Any]]]


@strawberry.experimental.pydantic.type(model=EmbedderResponse)
class EmbedderResponseType:
    embedders: List[str]


# Helper for auth
async def get_user_from_context(info):
    request = info.context["request"]
    try:
        user = await verify_api_key(request)
        return user
    except HTTPException as e:
        raise Exception(str(e.detail))


@strawberry.type
class Query:
    @strawberry.field
    async def providers(self, info) -> ProvidersResponseType:
        """Get all available providers"""
        try:
            result = await rest_get_all_providers(
                user=await get_user_from_context(info)
            )
            return ProvidersResponseType.from_pydantic(
                ProvidersResponse(providers=get_providers())
            )
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def provider_settings(self, info, provider_name: str) -> ProviderSettingsType:
        """Get settings for a specific provider"""
        try:
            result = await rest_get_provider_settings(
                provider_name=provider_name, user=await get_user_from_context(info)
            )
            return ProviderSettingsType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def providers_with_settings(self, info) -> ProviderWithSettingsType:
        """Get all providers with their settings"""
        try:
            result = await rest_get_all_providers(
                user=await get_user_from_context(info)
            )
            return ProviderWithSettingsType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def providers_by_service(self, info, service: str) -> ProvidersResponseType:
        """Get providers that offer a specific service"""
        try:
            result = await rest_get_providers_by_service(
                service=service, user=await get_user_from_context(info)
            )
            return ProvidersResponseType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def embedding_providers(self, info) -> ProvidersResponseType:
        """Get providers that offer embedding services"""
        try:
            result = await rest_get_embed_providers(
                user=await get_user_from_context(info)
            )
            return ProvidersResponseType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def embedders(self, info) -> EmbedderResponseType:
        """Get detailed information about embedding providers"""
        try:
            result = await rest_get_embedder_info(
                user=await get_user_from_context(info)
            )
            return EmbedderResponseType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def providers_with_details(self, info) -> Dict[str, Any]:
        """Get comprehensive provider details (v1 endpoint)"""
        try:
            result = await rest_get_all_providers(
                user=await get_user_from_context(info)
            )
            return {"providers": get_providers_with_details()}
        except HTTPException as e:
            raise Exception(str(e.detail))


# Create the schema (no mutations needed for this endpoint)
schema = strawberry.Schema(query=Query)
