import strawberry
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from ApiClient import verify_api_key
from Providers import (
    get_provider_options,
    get_providers,
    get_providers_with_settings,
    get_providers_by_service,
    get_providers_with_details,
)


@strawberry.type
class ProviderSetting:
    name: str
    default_value: Optional[Any]


@strawberry.type
class ProviderService:
    name: str
    description: str


@strawberry.type
class ProviderDetail:
    name: str
    friendly_name: str
    description: str
    services: List[str]
    settings: List[ProviderSetting]


@strawberry.type
class Provider:
    name: str
    settings: List[ProviderSetting]


@strawberry.type
class EmbedderInfo:
    name: str
    capabilities: List[str]
    max_chunks: int
    chunk_size: int
    settings: List[ProviderSetting]


# Response types that group related data
@strawberry.type
class ProviderList:
    providers: List[str]


@strawberry.type
class ProviderWithSettings:
    provider: Provider


@strawberry.type
class ProvidersWithDetails:
    providers: List[ProviderDetail]


@strawberry.type
class EmbedderList:
    embedders: List[EmbedderInfo]


# Helper for auth
async def get_user_from_context(info):
    request = info.context["request"]
    try:
        user = await verify_api_key(request)
        return user
    except HTTPException as e:
        raise Exception(str(e.detail))


def convert_settings_to_type(settings_dict: Dict[str, Any]) -> List[ProviderSetting]:
    """Convert settings dictionary to list of ProviderSetting objects"""
    return [
        ProviderSetting(name=key, default_value=value)
        for key, value in settings_dict.items()
    ]


def convert_provider_details(details: Dict[str, Any]) -> ProviderDetail:
    """Convert provider details dictionary to ProviderDetail object"""
    return ProviderDetail(
        name=details["name"],
        friendly_name=details.get("friendly_name", details["name"]),
        description=details["description"],
        services=details["services"],
        settings=convert_settings_to_type(details["settings"]),
    )


@strawberry.type
class Query:
    @strawberry.field
    async def providers(self, info) -> ProviderList:
        """Get all available providers"""
        user = await get_user_from_context(info)
        providers = get_providers()
        return ProviderList(providers=providers)

    @strawberry.field
    async def provider_settings(self, info, provider_name: str) -> Provider:
        """Get settings for a specific provider"""
        user = await get_user_from_context(info)
        settings = get_provider_options(provider_name=provider_name)
        return Provider(name=provider_name, settings=convert_settings_to_type(settings))

    @strawberry.field
    async def providers_with_settings(self, info) -> List[ProviderWithSettings]:
        """Get all providers with their settings"""
        user = await get_user_from_context(info)
        providers_settings = get_providers_with_settings()
        return [
            ProviderWithSettings(
                provider=Provider(
                    name=list(provider.keys())[0],
                    settings=convert_settings_to_type(list(provider.values())[0]),
                )
            )
            for provider in providers_settings
        ]

    @strawberry.field
    async def providers_by_service(self, info, service: str) -> ProviderList:
        """Get providers that offer a specific service"""
        user = await get_user_from_context(info)
        providers = get_providers_by_service(service=service)
        return ProviderList(providers=providers)

    @strawberry.field
    async def embedding_providers(self, info) -> ProviderList:
        """Get providers that offer embedding services"""
        user = await get_user_from_context(info)
        providers = get_providers_by_service(service="embeddings")
        return ProviderList(providers=providers)

    @strawberry.field
    async def providers_with_details(self, info) -> ProvidersWithDetails:
        """Get comprehensive provider details"""
        user = await get_user_from_context(info)
        provider_details = get_providers_with_details()
        providers = [
            convert_provider_details({"name": name, **details})
            for name, details in provider_details.items()
        ]
        return ProvidersWithDetails(providers=providers)


schema = strawberry.Schema(query=Query)

# Example GraphQL Queries:
"""
# Get all providers
query {
  providers {
    providers
  }
}

# Get settings for a specific provider
query {
  providerSettings(providerName: "openai") {
    name
    settings {
      name
      defaultValue
    }
  }
}

# Get providers with details
query {
  providersWithDetails {
    providers {
      name
      friendlyName
      description
      services
      settings {
        name
        defaultValue
      }
    }
  }
}

# Get providers by service
query {
  providersByService(service: "llm") {
    providers
  }
}
"""
