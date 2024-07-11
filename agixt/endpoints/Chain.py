from fastapi import APIRouter, HTTPException, Depends, Header
from ApiClient import Chain, verify_api_key, get_api_client, is_admin
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
    ResponseMessage,
)

app = APIRouter()


@app.get("/api/chain", tags=["Chain"], dependencies=[Depends(verify_api_key)])
async def get_chains(user=Depends(verify_api_key), authorization: str = Header(None)):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    chains = Chain(user=user).get_chains()
    return chains


@app.get(
    "/api/chain/{chain_name}", tags=["Chain"], dependencies=[Depends(verify_api_key)]
)
async def get_chain(chain_name: str, user=Depends(verify_api_key)):
    chain_data = Chain(user=user).get_chain(chain_name=chain_name)
    return {"chain": chain_data}


@app.post(
    "/api/chain/{chain_name}/run",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def run_chain(
    chain_name: str,
    user_input: RunChain,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    agent_name = user_input.agent_override if user_input.agent_override else "gpt4free"
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
    )
    try:
        if "Chain failed to complete" in chain_response:
            raise HTTPException(status_code=500, detail=f"{chain_response}")
    except:
        return f"{chain_response}"
    return chain_response


@app.post(
    "/api/chain/{chain_name}/run/step/{step_number}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def run_chain_step(
    chain_name: str,
    step_number: str,
    user_input: RunChainStep,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
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


# Get chain args
@app.get(
    "/api/chain/{chain_name}/args",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def get_chain_args(
    chain_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    chain_args = Chain(user=user, ApiClient=ApiClient).get_chain_args(
        chain_name=chain_name
    )
    return {"chain_args": chain_args}


@app.post("/api/chain", tags=["Chain"], dependencies=[Depends(verify_api_key)])
async def add_chain(
    chain_name: ChainName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).add_chain(chain_name=chain_name.chain_name)
    return ResponseMessage(message=f"Chain '{chain_name.chain_name}' created.")


@app.post("/api/chain/import", tags=["Chain"], dependencies=[Depends(verify_api_key)])
async def importchain(
    chain: ChainData, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    response = Chain(user=user).import_chain(
        chain_name=chain.chain_name, steps=chain.steps
    )
    return ResponseMessage(message=response)


@app.put(
    "/api/chain/{chain_name}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def rename_chain(
    chain_name: str,
    new_name: ChainNewName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).rename_chain(chain_name=chain_name, new_name=new_name.new_name)
    return ResponseMessage(
        message=f"Chain '{chain_name}' renamed to '{new_name.new_name}'."
    )


@app.delete(
    "/api/chain/{chain_name}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_chain(
    chain_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).delete_chain(chain_name=chain_name)
    return ResponseMessage(message=f"Chain '{chain_name}' deleted.")


@app.post(
    "/api/chain/{chain_name}/step",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def add_step(
    chain_name: str,
    step_info: StepInfo,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    Chain(user=user, ApiClient=ApiClient).add_chain_step(
        chain_name=chain_name,
        step_number=step_info.step_number,
        prompt_type=step_info.prompt_type,
        prompt=step_info.prompt,
        agent_name=step_info.agent_name,
    )
    return {"message": f"Step {step_info.step_number} added to chain '{chain_name}'."}


@app.put(
    "/api/chain/{chain_name}/step/{step_number}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def update_step(
    chain_name: str,
    step_number: int,
    chain_step: ChainStep,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).update_step(
        chain_name=chain_name,
        step_number=step_number if step_number else chain_step.step_number,
        prompt_type=chain_step.prompt_type,
        prompt=chain_step.prompt,
        agent_name=chain_step.agent_name,
    )
    return {
        "message": f"Step {chain_step.step_number} updated for chain '{chain_name}'."
    }


@app.patch(
    "/api/chain/{chain_name}/step/move",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def move_step(
    chain_name: str,
    chain_step_new_info: ChainStepNewInfo,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).move_step(
        chain_name=chain_name,
        current_step_number=chain_step_new_info.old_step_number,
        new_step_number=chain_step_new_info.new_step_number,
    )
    return {
        "message": f"Step {chain_step_new_info.old_step_number} moved to {chain_step_new_info.new_step_number} in chain '{chain_name}'."
    }


@app.delete(
    "/api/chain/{chain_name}/step/{step_number}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_step(
    chain_name: str,
    step_number: int,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).delete_step(chain_name=chain_name, step_number=step_number)
    return {"message": f"Step {step_number} deleted from chain '{chain_name}'."}
