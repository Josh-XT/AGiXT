from typing import Dict
from fastapi import APIRouter, Depends, Header, HTTPException
from Providers import (
    get_provider_options,
    get_providers,
    get_providers_with_settings,
    get_providers_by_service,
)
from ApiClient import verify_api_key, DB_CONNECTED, get_api_client, is_admin
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


@app.get(
    "/api/providers/service/{service}",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_providers_by_service_name(service: str, user=Depends(verify_api_key)):
    providers = get_providers_by_service(service=service)
    return {"providers": providers}


# Gets list of embedding providers
@app.get(
    "/api/embedding_providers",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_embed_providers(user=Depends(verify_api_key)):
    providers = get_providers_by_service(service="embeddings")
    return {"providers": providers}


# Gets embedders with their details such as required parameters and chunk sizes
@app.get(
    "/api/embedders",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_embedder_info(user=Depends(verify_api_key)) -> Dict[str, Any]:
    return {"embedders": get_providers_by_service(service="embeddings")}


if DB_CONNECTED:
    from db.User import create_user
    from Models import User

    @app.post("/api/user", tags=["User"])
    async def createuser(
        account: User, authorization: str = Header(None), user=Depends(verify_api_key)
    ):
        if not is_admin(email=user, api_key=authorization):
            raise HTTPException(status_code=403, detail="Access Denied")
        ApiClient = get_api_client(authorization=authorization)
        return create_user(
            api_key=authorization,
            email=account.email,
            role="user",
            settings=account.settings,
            commands=account.commands,
            training_urls=account.training_urls,
            github_repos=account.github_repos,
            ApiClient=ApiClient,
        )

    @app.post("/api/admin", tags=["User"])
    async def createadmin(
        account: User, authorization: str = Header(None), user=Depends(verify_api_key)
    ):
        if not is_admin(email=user, api_key=authorization):
            raise HTTPException(status_code=403, detail="Access Denied")
        ApiClient = get_api_client(authorization=authorization)
        return create_user(
            api_key=authorization,
            email=account.email,
            role="admin",
            settings=account.settings,
            commands=account.commands,
            training_urls=account.training_urls,
            github_repos=account.github_repos,
            ApiClient=ApiClient,
        )
