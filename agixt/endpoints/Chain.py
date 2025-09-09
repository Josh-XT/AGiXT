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
    StepInfoV1,
    ChainStepV1,
    ChainDetailsResponse,
    ResponseMessage,
)

app = APIRouter()


@app.get(
    "/v1/chains",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=List[Dict[str, str]],
    summary="Get all chains",
    description="Retrieves a list of all available chains with IDs for the authenticated user and global chains.",
)
async def get_chains_v1(
    user=Depends(verify_api_key), authorization: str = Header(None)
):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")

    # Get chain names
    chain_names = Chain(user=user).get_chains()

    # For each chain, get its full data to extract the ID
    chains_with_ids = []
    for chain_name in chain_names:
        try:
            chain_data = Chain(user=user).get_chain(chain_name=chain_name)
            if chain_data and "steps" in chain_data:
                # Generate a consistent ID if not present
                import hashlib

                chain_id = chain_data.get(
                    "id", hashlib.md5(chain_name.encode()).hexdigest()
                )
                chains_with_ids.append(
                    {
                        "id": str(chain_id),
                        "chainName": chain_name,
                        "description": chain_data.get("description", ""),
                    }
                )
        except Exception as e:
            # Skip chains that can't be loaded
            continue

    return chains_with_ids


@app.post(
    "/v1/chain",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Create new chain",
    description="Creates a new empty chain with the specified name.",
)
async def add_chain_v1(
    chain_name: ChainName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_name.chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).add_chain(
        chain_name=chain_name.chain_name, description=chain_name.description
    )
    return ResponseMessage(message=f"Chain '{chain_name.chain_name}' created.")


@app.post(
    "/v1/chain/import",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Import chain",
    description="Imports a chain configuration including all steps and settings.",
)
async def import_chain_v1(
    chain: ChainData, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if chain.chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    response = Chain(user=user).import_chain(
        chain_name=chain.chain_name, steps=chain.steps
    )
    return ResponseMessage(message=response)


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

    # Transform the steps to match frontend expectations
    transformed_steps = []
    for step in chain_data.get("steps", []):
        transformed_step = {
            "step": step.get("step"),
            "agentName": step.get("agent_name"),  # Transform agent_name to agentName
            "promptType": step.get(
                "prompt_type"
            ),  # Transform prompt_type to promptType
            "prompt": step.get("prompt", {}),  # Keep prompt structure as-is
        }
        transformed_steps.append(transformed_step)

    # Transform the response to match ChainDetailsResponse model
    response_data = {
        "id": chain_data.get("id", chain_id),
        "chain_name": chain_data.get("name", ""),
        "steps": transformed_steps,
    }

    return {chain_data.get("name", ""): response_data}


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


# V1 Step Management Endpoints using chain_id and agent_id
@app.post(
    "/v1/chain/{chain_id}/step",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Add chain step by ID",
    description="Adds a new step to an existing chain using chain ID and agent ID.",
)
async def add_step_by_id_v1(
    chain_id: str,
    step_info: StepInfoV1,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")
    if step_info.agent_id == "":
        raise HTTPException(status_code=400, detail="Agent ID cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")

    try:
        # Get the chain name from chain ID
        chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
        if chain_data is None:
            raise HTTPException(status_code=404, detail="Chain not found")
        chain_name = chain_data["name"]

        # Get the agent name from agent ID
        agents = get_agents(user=user)
        agent_name = None
        for agent in agents:
            if agent["id"] == step_info.agent_id:
                agent_name = agent["name"]
                break

        if agent_name is None:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Add the step using the existing chain method
        Chain(user=user).add_chain_step(
            chain_name=chain_name,
            step_number=step_info.step_number,
            prompt_type=step_info.prompt_type,
            prompt=step_info.prompt,
            agent_name=agent_name,
        )
        return {
            "message": f"Step {step_info.step_number} added to chain '{chain_name}'."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put(
    "/v1/chain/{chain_id}/step/{step_number}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Update chain step by ID",
    description="Updates the configuration of an existing step in the chain using chain ID and agent ID.",
)
async def update_step_by_id_v1(
    chain_id: str,
    step_number: int,
    chain_step: ChainStepV1,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")
    if chain_step.agent_id == "":
        raise HTTPException(status_code=400, detail="Agent ID cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")

    try:
        # Get the chain name from chain ID
        chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
        if chain_data is None:
            raise HTTPException(status_code=404, detail="Chain not found")
        chain_name = chain_data["name"]

        # Get the agent name from agent ID
        agents = get_agents(user=user)
        agent_name = None
        for agent in agents:
            if agent.get("id") == chain_step.agent_id:
                agent_name = agent.get("name")
                break

        if agent_name is None:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Update the step using the existing chain method
        Chain(user=user).update_step(
            chain_name=chain_name,
            step_number=step_number if step_number else chain_step.step_number,
            prompt_type=chain_step.prompt_type,
            prompt=chain_step.prompt,
            agent_name=agent_name,
        )
        return {
            "message": f"Step {chain_step.step_number} updated for chain '{chain_name}'."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete(
    "/v1/chain/{chain_id}/step/{step_number}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Delete chain step by ID",
    description="Removes a specific step from the chain using chain ID.",
)
async def delete_step_by_id_v1(
    chain_id: str,
    step_number: int,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")

    try:
        # Get the chain name from chain ID
        chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
        if chain_data is None:
            raise HTTPException(status_code=404, detail="Chain not found")
        chain_name = chain_data["name"]

        # Delete the step using the existing chain method
        Chain(user=user).delete_step(chain_name=chain_name, step_number=step_number)
        return {"message": f"Step {step_number} deleted from chain '{chain_name}'."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch(
    "/v1/chain/{chain_id}/step/move",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Move chain step by ID",
    description="Changes the position of a step within the chain using chain ID.",
)
async def move_step_by_id_v1(
    chain_id: str,
    chain_step_new_info: ChainStepNewInfo,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")

    try:
        # Get the chain name from chain ID
        chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
        if chain_data is None:
            raise HTTPException(status_code=404, detail="Chain not found")
        chain_name = chain_data["name"]

        # Move the step using the existing chain method
        Chain(user=user).move_step(
            chain_name=chain_name,
            current_step_number=chain_step_new_info.old_step_number,
            new_step_number=chain_step_new_info.new_step_number,
        )
        return {
            "message": f"Step {chain_step_new_info.old_step_number} moved to {chain_step_new_info.new_step_number} in chain '{chain_name}'."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
