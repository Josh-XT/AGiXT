from typing import List, Dict, Optional, Any
import strawberry
from fastapi import HTTPException, Header
from ApiClient import Chain, verify_api_key, get_api_client, is_admin
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
    ResponseMessage as PydanticResponseMessage,
)
from XT import AGiXT
from endpoints.Chain import (
    get_chains as rest_get_chains,
    get_chain as rest_get_chain,
    get_chain_args as rest_get_chain_args,
)


# Convert Pydantic models to Strawberry types
@strawberry.experimental.pydantic.type(model=ChainDetailsResponse)
class ChainDetails:
    id: str
    chain_name: str
    steps: List[Dict[str, Any]]


@strawberry.experimental.pydantic.type(model=PydanticResponseMessage)
class ResponseMessage:
    message: str


# Input types
@strawberry.input
class RunChainInput:
    prompt: str
    agent_override: Optional[str] = None
    all_responses: Optional[bool] = False
    from_step: Optional[int] = 1
    chain_args: Optional[Dict[str, Any]] = strawberry.field(default_factory=dict)
    conversation_name: Optional[str] = ""


@strawberry.input
class RunChainStepInput:
    prompt: str
    agent_override: Optional[str] = None
    chain_args: Optional[Dict[str, Any]] = strawberry.field(default_factory=dict)
    chain_run_id: Optional[str] = ""
    conversation_name: Optional[str] = ""


@strawberry.input
class ChainStepInput:
    step_number: int
    agent_name: str
    prompt_type: str
    prompt: Dict[str, Any]


@strawberry.input
class ChainDataInput:
    chain_name: str
    steps: Dict[str, Any]


@strawberry.input
class MoveStepInput:
    old_step_number: int
    new_step_number: int


# Helper for auth
async def get_user_and_auth_from_context(info):
    request = info.context["request"]
    try:
        user = await verify_api_key(request)
        auth = request.headers.get("authorization")
        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")
        return user, auth
    except HTTPException as e:
        raise Exception(str(e.detail))


@strawberry.type
class Query:
    @strawberry.field
    async def chains(self, info) -> List[str]:
        """Get all available chains"""
        user, auth = await get_user_and_auth_from_context(info)
        return await rest_get_chains(user=user, authorization=auth)

    @strawberry.field
    async def chain(self, info, chain_name: str) -> ChainDetails:
        """Get details of a specific chain"""
        user, _ = await get_user_and_auth_from_context(info)
        result = await rest_get_chain(chain_name=chain_name, user=user)
        return ChainDetails.from_pydantic(result["chain"])

    @strawberry.field
    async def chain_args(self, info, chain_name: str) -> List[str]:
        """Get arguments for a specific chain"""
        user, auth = await get_user_and_auth_from_context(info)
        result = await rest_get_chain_args(
            chain_name=chain_name, user=user, authorization=auth
        )
        return result["chain_args"]


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def run_chain(self, info, chain_name: str, input: RunChainInput) -> str:
        """Execute a chain"""
        user, auth = await get_user_and_auth_from_context(info)
        agent_name = input.agent_override if input.agent_override else "gpt4free"
        chain_response = await AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=auth,
            conversation_name=input.conversation_name,
        ).execute_chain(
            chain_name=chain_name,
            user_input=input.prompt,
            agent_override=input.agent_override,
            from_step=input.from_step,
            chain_args=input.chain_args,
            log_user_input=False,
        )
        if "Chain failed to complete" in chain_response:
            raise Exception(chain_response)
        return chain_response

    @strawberry.mutation
    async def run_chain_step(
        self, info, chain_name: str, step_number: str, input: RunChainStepInput
    ) -> str:
        """Execute a specific step in a chain"""
        user, auth = await get_user_and_auth_from_context(info)
        chain = Chain(user=user)
        chain_steps = chain.get_chain(chain_name=chain_name)

        try:
            step = chain_steps["step"][step_number]
        except Exception as e:
            raise Exception(f"Step {step_number} not found. {str(e)}")

        agent_name = input.agent_override if input.agent_override else step["agent"]
        response = await AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=auth,
            conversation_name=input.conversation_name,
        ).run_chain_step(
            chain_run_id=input.chain_run_id,
            step=step,
            chain_name=chain_name,
            user_input=input.prompt,
            agent_override=input.agent_override,
            chain_args=input.chain_args,
        )

        if response is None:
            raise Exception(f"Error running step {step_number} in chain {chain_name}")
        if "Chain failed to complete" in response:
            raise Exception(response)
        return response

    @strawberry.mutation
    async def create_chain(self, info, chain_name: str) -> ResponseMessage:
        """Create a new chain"""
        user, auth = await get_user_and_auth_from_context(info)
        Chain(user=user).add_chain(chain_name=chain_name)
        return ResponseMessage(message=f"Chain '{chain_name}' created.")

    @strawberry.mutation
    async def import_chain(self, info, input: ChainDataInput) -> ResponseMessage:
        """Import a chain configuration"""
        user, auth = await get_user_and_auth_from_context(info)
        response = Chain(user=user).import_chain(
            chain_name=input.chain_name, steps=input.steps
        )
        return ResponseMessage(message=response)

    @strawberry.mutation
    async def rename_chain(
        self, info, chain_name: str, new_name: str
    ) -> ResponseMessage:
        """Rename an existing chain"""
        user, auth = await get_user_and_auth_from_context(info)
        Chain(user=user).rename_chain(chain_name=chain_name, new_name=new_name)
        return ResponseMessage(message=f"Chain '{chain_name}' renamed to '{new_name}'.")

    @strawberry.mutation
    async def delete_chain(self, info, chain_name: str) -> ResponseMessage:
        """Delete a chain"""
        user, auth = await get_user_and_auth_from_context(info)
        Chain(user=user).delete_chain(chain_name=chain_name)
        return ResponseMessage(message=f"Chain '{chain_name}' deleted.")

    @strawberry.mutation
    async def add_chain_step(
        self, info, chain_name: str, step: ChainStepInput
    ) -> ResponseMessage:
        """Add a step to a chain"""
        user, auth = await get_user_and_auth_from_context(info)
        Chain(user=user).add_chain_step(
            chain_name=chain_name,
            step_number=step.step_number,
            prompt_type=step.prompt_type,
            prompt=step.prompt,
            agent_name=step.agent_name,
        )
        return ResponseMessage(
            message=f"Step {step.step_number} added to chain '{chain_name}'."
        )

    @strawberry.mutation
    async def update_chain_step(
        self, info, chain_name: str, step_number: int, step: ChainStepInput
    ) -> ResponseMessage:
        """Update a chain step"""
        user, auth = await get_user_and_auth_from_context(info)
        Chain(user=user).update_step(
            chain_name=chain_name,
            step_number=step_number or step.step_number,
            prompt_type=step.prompt_type,
            prompt=step.prompt,
            agent_name=step.agent_name,
        )
        return ResponseMessage(
            message=f"Step {step.step_number} updated for chain '{chain_name}'."
        )

    @strawberry.mutation
    async def move_chain_step(
        self, info, chain_name: str, input: MoveStepInput
    ) -> ResponseMessage:
        """Move a step within a chain"""
        user, auth = await get_user_and_auth_from_context(info)
        Chain(user=user).move_step(
            chain_name=chain_name,
            current_step_number=input.old_step_number,
            new_step_number=input.new_step_number,
        )
        return ResponseMessage(
            message=f"Step {input.old_step_number} moved to {input.new_step_number} in chain '{chain_name}'."
        )

    @strawberry.mutation
    async def delete_chain_step(
        self, info, chain_name: str, step_number: int
    ) -> ResponseMessage:
        """Delete a step from a chain"""
        user, auth = await get_user_and_auth_from_context(info)
        Chain(user=user).delete_step(chain_name=chain_name, step_number=step_number)
        return ResponseMessage(
            message=f"Step {step_number} deleted from chain '{chain_name}'."
        )


# Create the schema
schema = strawberry.Schema(query=Query, mutation=Mutation)
