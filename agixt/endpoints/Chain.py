from fastapi import APIRouter, HTTPException, Depends, Header
from ApiClient import Chain, verify_api_key, get_api_client, is_admin
from MagicalAuth import require_scope
from Agent import get_agent_name_by_id
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
    ChainResponse,
)

app = APIRouter()


@app.get(
    "/v1/chains",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:read"))],
    response_model=List[Dict[str, str]],
    summary="Get all chains",
    description="Retrieves a list of all available chains with IDs for the authenticated user and global chains.",
)
async def get_chains_v1(
    user=Depends(verify_api_key), authorization: str = Header(None)
):

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
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:write"))],
    response_model=ChainResponse,
    summary="Create new chain",
    description="Creates a new empty chain with the specified name.",
)
async def add_chain_v1(
    chain_name: ChainName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ChainResponse:
    if chain_name.chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    chain_id = Chain(user=user).add_chain(
        chain_name=chain_name.chain_name, description=chain_name.description
    )
    return ChainResponse(
        message=f"Chain '{chain_name.chain_name}' created.", id=chain_id
    )


@app.post(
    "/v1/chain/import",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:write"))],
    response_model=ResponseMessage,
    summary="Import chain",
    description="Imports a chain configuration including all steps and settings.",
)
async def import_chain_v1(
    chain: ChainData, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if chain.chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
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

    # Transform the response to match ChainDetailsResponse model
    response_data = {
        "id": chain_data.get("id", chain_id),
        "chain_name": chain_data.get("name", ""),
        "description": chain_data.get("description", ""),
        "steps": chain_data.get("steps", []),
    }

    return {chain_data.get("name", ""): response_data}


@app.delete(
    "/v1/chain/{chain_id}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:delete"))],
    response_model=ResponseMessage,
    summary="Delete chain by ID",
    description="Deletes a specific chain using chain ID. Requires admin privileges.",
)
async def delete_chain_by_id_v1(
    chain_id: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")
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
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:write"))],
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
    chain_args = Chain(user=user).get_chain_args_by_id(chain_id=chain_id)
    return chain_args


# V1 Step Management Endpoints using chain_id and agent_id
@app.post(
    "/v1/chain/{chain_id}/step",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:write"))],
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

    try:
        # Get the chain name from chain ID
        chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
        if chain_data is None:
            raise HTTPException(status_code=404, detail="Chain not found")
        chain_name = chain_data["name"]

        # Get the agent name from agent ID using standalone function
        try:
            agent_name = get_agent_name_by_id(agent_id=step_info.agent_id, user=user)
        except ValueError:
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
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:write"))],
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

    try:
        # Get the chain name from chain ID
        chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
        if chain_data is None:
            raise HTTPException(status_code=404, detail="Chain not found")
        chain_name = chain_data["name"]

        # Get the agent name from agent ID using standalone function
        try:
            agent_name = get_agent_name_by_id(agent_id=chain_step.agent_id, user=user)
        except ValueError:
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
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:delete"))],
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
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:write"))],
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


# V1 Chain Run Endpoints


@app.post(
    "/v1/chain/{chain_id}/run",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:execute"))],
    response_model=str,
    summary="Run chain by ID",
    description="Executes a chain using its ID and returns the final output.",
)
async def run_chain_v1(
    chain_id: str,
    user_input: RunChain,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")

    # Get the chain name from chain ID
    chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
    if chain_data is None:
        raise HTTPException(status_code=404, detail="Chain not found")
    chain_name = chain_data["name"]

    # Handle agent_override - if specified, get agent name by ID or use as name
    agent_name = None
    if user_input.agent_override:
        try:
            # First try treating it as an ID
            agent_name = get_agent_name_by_id(
                agent_id=user_input.agent_override, user=user
            )
        except ValueError:
            # If that fails, treat it as an agent name directly
            agent_name = user_input.agent_override

    # If no agent_override provided, default to "XT" agent
    if not agent_name:
        agent_name = "XT"

    conversation_name = user_input.conversation_name
    chain_response = await AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=conversation_name,
    ).execute_chain(
        chain_name=chain_name,
        user_input=user_input.prompt,
        agent_override=user_input.agent_override,
        from_step=user_input.from_step,
        chain_args=user_input.chain_args,
        log_user_input=False,
        log_output=False,
    )
    try:
        if "Chain failed to complete" in chain_response:
            raise HTTPException(status_code=500, detail=f"{chain_response}")
    except:
        return f"{chain_response}"
    return chain_response


@app.post(
    "/v1/chain/{chain_id}/run/step/{step_number}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:execute"))],
    response_model=str,
    summary="Run chain step by ID",
    description="Executes a specific step within a chain using chain ID and returns the output.",
)
async def run_chain_step_v1(
    chain_id: str,
    step_number: str,
    user_input: RunChainStep,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if chain_id == "":
        raise HTTPException(status_code=400, detail="Chain ID cannot be empty.")

    # Get the chain name from chain ID
    chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
    if chain_data is None:
        raise HTTPException(status_code=404, detail="Chain not found")
    chain_name = chain_data["name"]

    chain = Chain(user=user)
    chain_steps = chain.get_chain(chain_name=chain_name)
    try:
        step = chain_steps["step"][step_number]
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Step {step_number} not found. {e}"
        )
    agent_name = (
        user_input.agent_override if user_input.agent_override else step["agent"]
    )
    chain_step_response = await AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=user_input.conversation_name,
    ).run_chain_step(
        chain_run_id=user_input.chain_run_id,
        step=step,
        chain_name=chain_name,
        user_input=user_input.prompt,
        agent_override=user_input.agent_override,
        chain_args=user_input.chain_args,
    )
    if chain_step_response == None:
        raise HTTPException(
            status_code=500,
            detail=f"Error running step {step_number} in chain {chain_name}",
        )
    if "Chain failed to complete" in chain_step_response:
        raise HTTPException(status_code=500, detail=chain_step_response)
    return chain_step_response


# =========================================================================
# Tiered Chain Endpoints
# =========================================================================


@app.get(
    "/v1/chains/all",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
    summary="Get all chains from all tiers",
    description="Retrieves all chains available to the user from server, company, and user tiers with source indicators.",
)
async def get_all_user_chains_v1(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    chains = Chain(user=user).get_all_user_chains()
    return {"chains": chains}


@app.post(
    "/v1/chain/{chain_id}/clone",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:write"))],
    response_model=ChainResponse,
    summary="Clone chain to user level",
    description="Clone a chain from parent tier (server/company) to user level for editing.",
)
async def clone_chain_to_user_v1(
    chain_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ChainResponse:
    # Get chain name from ID first
    chain_data = Chain(user=user).get_chain_by_id(chain_id=chain_id)
    if chain_data:
        chain_name = chain_data["name"]
    else:
        # Try to get from tiered resolution
        tiered_data = Chain(user=user).get_chain_with_tiered_resolution(chain_id)
        if tiered_data and "chain_name" in tiered_data:
            chain_name = tiered_data["chain_name"]
        else:
            raise HTTPException(status_code=404, detail="Chain not found")

    new_chain_id = Chain(user=user).clone_chain_to_user(chain_name=chain_name)
    if not new_chain_id:
        raise HTTPException(status_code=400, detail="Could not clone chain")
    return ChainResponse(message="Chain cloned to user level.", id=new_chain_id)


@app.post(
    "/v1/chain/{chain_id}/revert",
    tags=["Chain"],
    response_model=ResponseMessage,
    summary="Revert chain to default",
    description="Revert a user's customized chain back to the parent (server/company) version.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:write"))],
)
async def revert_chain_to_default_v1(
    chain_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    result = Chain(user=user).revert_chain_to_default(chain_id=chain_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ResponseMessage(message=result["message"])


# =========================================================================
# Server-level chain management (super admin only)
# =========================================================================


@app.get(
    "/v1/server/chains",
    tags=["Server Chains"],
    summary="Get all server-level chains",
    description="Retrieve all server-level chains. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:chains"))],
)
async def get_server_chains_v1(
    include_internal: bool = False,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    chains = Chain(user=user).get_server_chains(include_internal=include_internal)
    return {"chains": chains}


@app.post(
    "/v1/server/chain",
    tags=["Server Chains"],
    summary="Create a server-level chain",
    description="Create a new server-level chain. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:chains"))],
)
async def create_server_chain_v1(
    chain_name: ChainName,
    is_internal: bool = False,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ChainResponse:
    chain_id = Chain(user=user).add_server_chain(
        name=chain_name.chain_name,
        description=chain_name.description,
        is_internal=is_internal,
    )
    return ChainResponse(
        message=f"Server chain '{chain_name.chain_name}' created.",
        id=chain_id,
    )


@app.get(
    "/v1/server/chain/{chain_id}",
    tags=["Server Chains"],
    summary="Get a server-level chain by ID",
    description="Retrieve a specific server-level chain by its ID. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:chains"))],
)
async def get_server_chain_v1(
    chain_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    chain = Chain(user=user).get_server_chain_by_id(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Server chain not found")
    return chain


@app.put(
    "/v1/server/chain/{chain_id}",
    tags=["Server Chains"],
    response_model=ResponseMessage,
    summary="Update a server-level chain",
    description="Update a server-level chain by ID. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:chains"))],
)
async def update_server_chain_v1(
    chain_id: str,
    chain_data: ChainNewName,
    is_internal: bool = None,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Chain(user=user).update_server_chain(
            chain_id=chain_id,
            name=chain_data.new_name,
            description=getattr(chain_data, "description", None),
            is_internal=is_internal,
        )
        return ResponseMessage(message="Server chain updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete(
    "/v1/server/chain/{chain_id}",
    tags=["Server Chains"],
    response_model=ResponseMessage,
    summary="Delete a server-level chain",
    description="Delete a server-level chain by ID. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:chains"))],
)
async def delete_server_chain_v1(
    chain_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Chain(user=user).delete_server_chain(chain_id=chain_id)
        return ResponseMessage(message="Server chain deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post(
    "/v1/server/chain/{chain_id}/step",
    tags=["Server Chains"],
    response_model=ResponseMessage,
    summary="Add step to server chain",
    description="Add a step to a server-level chain. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:chains"))],
)
async def add_server_chain_step_v1(
    chain_id: str,
    step_info: StepInfo,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Chain(user=user).add_server_chain_step(
            chain_id=chain_id,
            step_number=step_info.step_number,
            agent_name=step_info.agent_name,
            prompt_type=step_info.prompt_type,
            prompt=step_info.prompt,
        )
        return ResponseMessage(
            message=f"Step {step_info.step_number} added to server chain."
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete(
    "/v1/server/chain/{chain_id}/step/{step_number}",
    tags=["Server Chains"],
    response_model=ResponseMessage,
    summary="Delete step from server chain",
    description="Delete a step from a server-level chain. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:chains"))],
)
async def delete_server_chain_step_v1(
    chain_id: str,
    step_number: int,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Chain(user=user).delete_server_chain_step(
            chain_id=chain_id, step_number=step_number
        )
        return ResponseMessage(message=f"Step {step_number} deleted from server chain.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# =========================================================================
# Company-level chain management (company admin only)
# =========================================================================


@app.get(
    "/v1/company/chains",
    tags=["Company Chains"],
    summary="Get all company-level chains",
    description="Retrieve all company-level chains for the user's company. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:chains"))],
)
async def get_company_chains_v1(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    chains = Chain(user=user).get_company_chains()
    return {"chains": chains}


@app.post(
    "/v1/company/chain",
    tags=["Company Chains"],
    summary="Create a company-level chain",
    description="Create a new company-level chain. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:chains"))],
)
async def create_company_chain_v1(
    chain_name: ChainName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ChainResponse:
    chain_id = Chain(user=user).add_company_chain(
        name=chain_name.chain_name,
        description=chain_name.description,
    )
    return ChainResponse(
        message=f"Company chain '{chain_name.chain_name}' created.",
        id=chain_id,
    )


@app.get(
    "/v1/company/chain/{chain_id}",
    tags=["Company Chains"],
    summary="Get a company-level chain by ID",
    description="Retrieve a specific company-level chain by its ID. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:chains"))],
)
async def get_company_chain_v1(
    chain_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    chain = Chain(user=user).get_company_chain_by_id(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Company chain not found")
    return chain


@app.put(
    "/v1/company/chain/{chain_id}",
    tags=["Company Chains"],
    response_model=ResponseMessage,
    summary="Update a company-level chain",
    description="Update a company-level chain by ID. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:chains"))],
)
async def update_company_chain_v1(
    chain_id: str,
    chain_data: ChainNewName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Chain(user=user).update_company_chain(
            chain_id=chain_id,
            name=chain_data.new_name,
            description=getattr(chain_data, "description", None),
        )
        return ResponseMessage(message="Company chain updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete(
    "/v1/company/chain/{chain_id}",
    tags=["Company Chains"],
    response_model=ResponseMessage,
    summary="Delete a company-level chain",
    description="Delete a company-level chain by ID. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:chains"))],
)
async def delete_company_chain_v1(
    chain_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Chain(user=user).delete_company_chain(chain_id=chain_id)
        return ResponseMessage(message="Company chain deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post(
    "/v1/company/chain/share/{chain_id}",
    tags=["Company Chains"],
    summary="Share a user chain to company",
    description="Share a user's chain to the company level. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("chains:share"))],
)
async def share_chain_to_company_v1(
    chain_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ChainResponse:
    try:
        new_chain_id = Chain(user=user).share_chain_to_company(chain_id=chain_id)
        return ChainResponse(
            message="Chain shared to company.",
            id=new_chain_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/v1/company/chain/{chain_id}/step",
    tags=["Company Chains"],
    response_model=ResponseMessage,
    summary="Add step to company chain",
    description="Add a step to a company-level chain. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:chains"))],
)
async def add_company_chain_step_v1(
    chain_id: str,
    step_info: StepInfo,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Chain(user=user).add_company_chain_step(
            chain_id=chain_id,
            step_number=step_info.step_number,
            agent_name=step_info.agent_name,
            prompt_type=step_info.prompt_type,
            prompt=step_info.prompt,
        )
        return ResponseMessage(
            message=f"Step {step_info.step_number} added to company chain."
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete(
    "/v1/company/chain/{chain_id}/step/{step_number}",
    tags=["Company Chains"],
    response_model=ResponseMessage,
    summary="Delete step from company chain",
    description="Delete a step from a company-level chain. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:chains"))],
)
async def delete_company_chain_step_v1(
    chain_id: str,
    step_number: int,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Chain(user=user).delete_company_chain_step(
            chain_id=chain_id, step_number=step_number
        )
        return ResponseMessage(
            message=f"Step {step_number} deleted from company chain."
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
