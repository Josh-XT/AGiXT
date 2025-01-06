from typing import Dict
from fastapi import APIRouter, Depends
from Providers import (
    get_provider_options,
    get_providers,
    get_providers_with_settings,
    get_providers_by_service,
    get_providers_with_details,
)
from Models import (
    ProvidersResponse,
    ProviderSettings,
    ProviderWithSettings,
    EmbedderResponse,
)
from ApiClient import verify_api_key, get_api_client, is_admin
from typing import Any

app = APIRouter()


@app.get(
    "/api/provider",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
    response_model=ProvidersResponse,
    summary="Get All Available Providers",
    description="Returns a list of all enabled providers in the system. These providers can be used for various services like LLM, TTS, image generation, etc.",
)
async def getproviders(user=Depends(verify_api_key)):
    providers = get_providers()
    return {"providers": providers}


@app.get(
    "/api/provider/{provider_name}",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
    response_model=ProviderSettings,
    summary="Get Provider Settings",
    description="Retrieves the configuration settings and options available for a specific provider. This includes default values and required parameters.",
)
async def get_provider_settings(provider_name: str, user=Depends(verify_api_key)):
    settings = get_provider_options(provider_name=provider_name)
    return {"settings": settings}


@app.get(
    "/api/providers",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
    response_model=ProviderWithSettings,
    summary="Get All Providers with Settings",
    description="Returns a comprehensive list of all providers along with their respective configuration settings and options.",
)
async def get_all_providers(user=Depends(verify_api_key)):
    providers = get_providers_with_settings()
    return {"providers": providers}


@app.get(
    "/api/providers/service/{service}",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
    response_model=ProvidersResponse,
    summary="Get Providers by Service",
    description="Retrieves a list of providers that offer a specific service. Valid services include: 'llm', 'tts', 'image', 'embeddings', 'transcription', 'translation', and 'vision'.",
)
async def get_providers_by_service_name(service: str, user=Depends(verify_api_key)):
    providers = get_providers_by_service(service=service)
    return {"providers": providers}


# Gets list of embedding providers
@app.get(
    "/api/embedding_providers",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
    response_model=ProvidersResponse,
    summary="Get Embedding Providers",
    description="Returns a list of providers that specifically offer embedding services. This endpoint is a specialized version of the service-specific provider endpoint.",
)
async def get_embed_providers(user=Depends(verify_api_key)):
    providers = get_providers_by_service(service="embeddings")
    return {"providers": providers}


# Gets embedders with their details such as required parameters and chunk sizes
@app.get(
    "/api/embedders",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
    response_model=EmbedderResponse,
    summary="Get Detailed Embedder Information",
    description="Retrieves detailed information about available embedding providers, including their capabilities and requirements.",
)
async def get_embedder_info(user=Depends(verify_api_key)) -> Dict[str, Any]:
    return {"embedders": get_providers_by_service(service="embeddings")}


@app.get(
    "/v1/providers",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
    summary="Get All Providers with Settings",
    description="Returns a comprehensive list of all providers along with their respective configuration settings and options.",
)
async def get_all_providers(user=Depends(verify_api_key)):
    providers = get_providers_with_details()
    return {"providers": providers}
