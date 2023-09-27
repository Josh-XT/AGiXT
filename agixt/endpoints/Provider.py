from typing import Dict
from fastapi import APIRouter, Depends
from Providers import get_provider_options, get_providers, get_providers_with_settings
from Embedding import get_embedding_providers, get_embedders
from ApiClient import verify_api_key
from typing import Any

app = APIRouter()


@app.get("/api/provider", tags=["Provider"], dependencies=[Depends(verify_api_key)])
async def getproviders(user=Depends(verify_api_key)):
    providers = get_providers()
    return {"providers": providers}


@app.get(
    "/api/provider/{provider_name}",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_provider_settings(provider_name: str, user=Depends(verify_api_key)):
    settings = get_provider_options(provider_name=provider_name)
    return {"settings": settings}


@app.get(
    "/api/providers",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_all_providers(user=Depends(verify_api_key)):
    providers = get_providers_with_settings()
    return {"providers": providers}


# Gets list of embedding providers
@app.get(
    "/api/embedding_providers",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_embed_providers(user=Depends(verify_api_key)):
    providers = get_embedding_providers()
    return {"providers": providers}


# Gets embedders with their details such as required parameters and chunk sizes
@app.get(
    "/api/embedders",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_embedder_info(user=Depends(verify_api_key)) -> Dict[str, Any]:
    return {"embedders": get_embedders()}
