from typing import List, Dict, Any, Optional
import strawberry
from fastapi import Depends, HTTPException, Header
from Models import (
    CommandExecution,
    CommandArgs,
    ExtensionsModel,
    ExtensionSettings,
)
from Extensions import Extensions
from ApiClient import Agent, Conversations, verify_api_key, get_api_client, is_admin
from endpoints.Extension import (
    get_extension_settings as rest_get_extension_settings,
    get_command_args as rest_get_command_args,
    get_extensions as rest_get_extensions,
    get_agent_extensions as rest_get_agent_extensions,
    run_command as rest_run_command,
)


# Convert Pydantic models to Strawberry types
@strawberry.experimental.pydantic.type(model=ExtensionSettings)
class ExtensionSettingsType:
    extension_settings: Dict[str, Dict[str, Any]]


@strawberry.experimental.pydantic.type(model=CommandArgs)
class CommandArgsType:
    command_args: Dict[str, Any]


@strawberry.experimental.pydantic.type(model=ExtensionsModel)
class ExtensionsModelType:
    extensions: List[Dict[str, Any]]


# Input types
@strawberry.input
class CommandExecutionInput:
    command_name: str
    command_args: Dict[str, Any]
    conversation_name: Optional[str] = None


@strawberry.type
class CommandResponse:
    response: str


# Helper for auth
async def get_user_and_auth_from_context(info):
    request = info.context["request"]
    try:
        user = await verify_api_key(request)
        auth = request.headers.get("authorization")
        return user, auth
    except HTTPException as e:
        raise Exception(str(e.detail))


@strawberry.type
class Query:
    @strawberry.field
    async def extension_settings(self, info) -> ExtensionSettingsType:
        """Get all extension settings for the authenticated user"""
        try:
            user = await verify_api_key(info.context["request"])
            result = await rest_get_extension_settings(user=user)
            return ExtensionSettingsType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def command_args(self, info, command_name: str) -> CommandArgsType:
        """Get arguments for a specific command"""
        try:
            user = await verify_api_key(info.context["request"])
            result = await rest_get_command_args(command_name=command_name, user=user)
            return CommandArgsType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def extensions(self, info) -> ExtensionsModelType:
        """Get all available extensions"""
        try:
            user = await verify_api_key(info.context["request"])
            result = await rest_get_extensions(user=user)
            return ExtensionsModelType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def agent_extensions(self, info, agent_name: str) -> ExtensionsModelType:
        """Get extensions for a specific agent"""
        try:
            user = await verify_api_key(info.context["request"])
            result = await rest_get_agent_extensions(agent_name=agent_name, user=user)
            return ExtensionsModelType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def execute_command(
        self, info, agent_name: str, command: CommandExecutionInput
    ) -> CommandResponse:
        """Execute a command for an agent"""
        try:
            user, auth = await get_user_and_auth_from_context(info)
            if not is_admin(email=user, api_key=auth):
                raise Exception("Access Denied")

            command_execution = CommandExecution(
                command_name=command.command_name,
                command_args=command.command_args,
                conversation_name=command.conversation_name,
            )

            result = await rest_run_command(
                agent_name=agent_name,
                command=command_execution,
                user=user,
                authorization=auth,
            )

            return CommandResponse(response=result["response"])
        except HTTPException as e:
            raise Exception(str(e.detail))


# Create the schema
schema = strawberry.Schema(query=Query, mutation=Mutation)
