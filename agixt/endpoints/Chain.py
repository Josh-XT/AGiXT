from fastapi import APIRouter, HTTPException, Depends, Header
from ApiClient import Chain, verify_api_key, get_api_client, is_admin, get_agents
from typing import List, Dict
from uuid import UUID
from XT import AGiXT
from Models import (
    RunChain,
    RunChainStep,
    ChainName,
    ChainData,
    ChainNewName,
    StepInfo,
    ChainStep,
    ChainStepNewInfo,
    ChainDetailsResponse,
    ResponseMessage,
)

app = APIRouter()


@app.get(
    "/v1/chain/{chain_id}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=Dict[str, ChainDetailsResponse],
    summary="Get chain details by ID",
    description="Retrieves detailed information about a specific chain using chain ID, including all steps and configurations.",
)
async def get_chain_by_id_v1(chain_id: str, user=Depends(verify_api_key)):
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")
    chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
    if chain_data is None:
        raise HTTPException(status_code=404, detail="Chain not found")
    return {chain_data["name"]: chain_data}


@app.delete(
    "/v1/chain/{chain_id}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Delete chain by ID",
    description="Deletes a specific chain using chain ID. Requires admin privileges.",
)
async def delete_chain_by_id_v1(
    chain_id: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    try:
        chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
        if chain_data is None:
            raise HTTPException(status_code=404, detail="Chain not found")
        Chain(user=user).delete_chain_by_id(chain_id=chain_id)
        return {"message": f"Chain '{chain_data['name']}' deleted."}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put(
    "/v1/chain/{chain_id}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Update chain by ID",
    description="Updates a chain's name and description using chain ID. Requires admin privileges.",
)
async def update_chain_by_id_v1(
    chain_id: str,
    chain_data: ChainNewName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    try:
        Chain(user=user).update_chain_by_id(
            chain_id=chain_id,
            chain_name=chain_data.new_name,
            description=getattr(chain_data, "description", ""),
        )
        return {"message": f"Chain updated to '{chain_data.new_name}'."}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get(
    "/v1/chain/{chain_id}/args",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=List[str],
    summary="Get chain arguments by ID",
    description="Retrieves the list of arguments required by a specific chain using chain ID.",
)
async def get_chain_args_by_id_v1(chain_id: str, user=Depends(verify_api_key)):
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")
    try:
        chain_args = Chain(user=user).get_chain_args_by_id(chain_id=chain_id)
        return chain_args
    except Exception as e:
        raise HTTPException(status_code=404, detail="Chain not found")
