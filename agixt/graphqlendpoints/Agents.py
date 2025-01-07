from typing import List, Dict, Any, Optional
import strawberry
from fastapi import HTTPException
from Models import (
    AgentNewName,
    AgentPrompt,
    ToggleCommandPayload,
    AgentSettings,
    AgentConfig,
    AgentResponse,
    AgentConfigResponse,
    AgentCommandsResponse,
    AgentBrowsedLinksResponse,
    PersonaInput,
    TTSInput,
    TaskPlanInput,
    ThinkingPrompt,
    ResponseMessage,
    UrlInput,
)
from endpoints.Agent import (
    addagent as rest_add_agent,
    import_agent as rest_import_agent,
    renameagent as rest_rename_agent,
    update_agent_settings as rest_update_settings,
    update_agent_commands as rest_update_commands,
    deleteagent as rest_delete_agent,
    getagents as rest_get_agents,
    get_agentconfig as rest_get_config,
    prompt_agent as rest_prompt_agent,
    get_commands as rest_get_commands,
    toggle_command as rest_toggle_command,
    get_agent_browsed_links as rest_get_browsed_links,
    delete_browsed_link as rest_delete_browsed_link,
    text_to_speech as rest_text_to_speech,
    plan_task as rest_plan_task,
    think as rest_think,
    update_persona as rest_update_persona,
    get_persona as rest_get_persona,
    delete_provider as rest_delete_provider,
)
from ApiClient import verify_api_key


# Convert Pydantic models to Strawberry types
@strawberry.experimental.pydantic.type(model=AgentResponse)
class AgentResponseType:
    message: str


@strawberry.experimental.pydantic.type(model=AgentConfigResponse)
class AgentConfigResponseType:
    agent: Dict[str, Any]


@strawberry.experimental.pydantic.type(model=AgentCommandsResponse)
class AgentCommandsResponseType:
    commands: Dict[str, bool]


@strawberry.experimental.pydantic.type(model=AgentBrowsedLinksResponse)
class AgentBrowsedLinksResponseType:
    links: List[Dict[str, Any]]


@strawberry.experimental.pydantic.type(model=ResponseMessage)
class ResponseMessageType:
    message: str


# Input types
@strawberry.input
class AgentSettingsInput:
    agent_name: str
    settings: Dict[str, Any] = strawberry.field(default_factory=dict)
    commands: Dict[str, Any] = strawberry.field(default_factory=dict)
    training_urls: List[str] = strawberry.field(default_factory=list)


@strawberry.input
class AgentPromptInput:
    prompt_name: str
    prompt_args: Dict[str, Any]


@strawberry.type
class AgentSetting:
    key: str
    value: str


@strawberry.type
class AgentCommand:
    name: str
    enabled: bool


@strawberry.type
class Agent:
    name: str
    settings: List[AgentSetting]
    commands: List[AgentCommand]


@strawberry.type
class AgentListResponse:
    agents: List[Agent]


@strawberry.type
class AgentType:
    name: str
    settings: Dict[str, str]
    commands: Dict[str, bool]


@strawberry.input
class PersonaUpdateInput:
    persona: str
    company_id: Optional[str] = None


# Helper for auth
async def get_user_from_context(info):
    request = info.context["request"]
    try:
        user = await verify_api_key(request)
        return user
    except HTTPException as e:
        raise Exception(str(e.detail))


@strawberry.type
class Query:
    @strawberry.field
    async def agents(self, info) -> AgentListResponse:
        """Get all agents"""
        response = await rest_get_agents(
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )

        agents = []
        for agent_data in response["agents"]:
            # Convert dict settings to list of AgentSetting objects
            settings = [
                AgentSetting(key=k, value=v)
                for k, v in agent_data.get("settings", {}).items()
            ]

            # Convert dict commands to list of AgentCommand objects
            commands = [
                AgentCommand(name=k, enabled=v)
                for k, v in agent_data.get("commands", {}).items()
            ]

            agents.append(
                Agent(name=agent_data["name"], settings=settings, commands=commands)
            )

        return AgentListResponse(agents=agents)

    @strawberry.field
    async def agent_config(self, info, agent_name: str) -> AgentConfigResponseType:
        """Get agent configuration"""
        result = await rest_get_config(
            agent_name=agent_name,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return AgentConfigResponseType.from_pydantic(result)

    @strawberry.field
    async def agent_commands(self, info, agent_name: str) -> AgentCommandsResponseType:
        """Get agent commands"""
        result = await rest_get_commands(
            agent_name=agent_name,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return AgentCommandsResponseType.from_pydantic(result)

    @strawberry.field
    async def browsed_links(
        self, info, agent_name: str, collection_number: str = "0"
    ) -> AgentBrowsedLinksResponseType:
        """Get agent's browsed links"""
        result = await rest_get_browsed_links(
            agent_name=agent_name,
            collection_number=collection_number,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return AgentBrowsedLinksResponseType.from_pydantic(result)

    @strawberry.field
    async def agent_persona(
        self, info, agent_name: str, company_id: Optional[str] = None
    ) -> Dict[str, str]:
        """Get agent persona"""
        return await rest_get_persona(
            agent_name=agent_name,
            company_id=company_id if company_id else None,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_agent(self, info, agent: AgentSettingsInput) -> AgentResponseType:
        """Create a new agent"""
        result = await rest_add_agent(
            agent=AgentSettings(**agent.__dict__),
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return AgentResponseType.from_pydantic(result)

    @strawberry.mutation
    async def import_agent(self, info, agent: AgentSettingsInput) -> AgentResponseType:
        """Import an agent configuration"""
        result = await rest_import_agent(
            agent=AgentConfig(**agent.__dict__),
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return AgentResponseType.from_pydantic(result)

    @strawberry.mutation
    async def rename_agent(
        self, info, agent_name: str, new_name: str
    ) -> ResponseMessageType:
        """Rename an agent"""
        result = await rest_rename_agent(
            agent_name=agent_name,
            new_name=AgentNewName(new_name=new_name),
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def update_agent_settings(
        self, info, agent_name: str, settings: AgentSettingsInput
    ) -> ResponseMessageType:
        """Update agent settings"""
        result = await rest_update_settings(
            agent_name=agent_name,
            settings=AgentSettings(**settings.__dict__),
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def update_agent_persona(
        self, info, agent_name: str, persona_input: PersonaUpdateInput
    ) -> ResponseMessageType:
        """Update agent persona"""
        result = await rest_update_persona(
            agent_name=agent_name,
            persona=PersonaInput(**persona_input.__dict__),
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def delete_agent(self, info, agent_name: str) -> ResponseMessageType:
        """Delete an agent"""
        result = await rest_delete_agent(
            agent_name=agent_name,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def prompt_agent(
        self, info, agent_name: str, prompt: AgentPromptInput
    ) -> Dict[str, str]:
        """Send a prompt to an agent"""
        return await rest_prompt_agent(
            agent_name=agent_name,
            agent_prompt=AgentPrompt(**prompt.__dict__),
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )

    @strawberry.mutation
    async def toggle_command(
        self, info, agent_name: str, command_name: str, enable: bool
    ) -> ResponseMessageType:
        """Toggle agent command"""
        result = await rest_toggle_command(
            agent_name=agent_name,
            payload=ToggleCommandPayload(command_name=command_name, enable=enable),
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def text_to_speech(self, info, agent_name: str, text: str) -> Dict[str, str]:
        """Convert text to speech"""
        return await rest_text_to_speech(
            agent_name=agent_name,
            text=TTSInput(text=text),
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )

    @strawberry.mutation
    async def plan_task(
        self, info, agent_name: str, task: TaskPlanInput
    ) -> Dict[str, str]:
        """Plan a task"""
        return await rest_plan_task(
            agent_name=agent_name,
            task=task,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )

    @strawberry.mutation
    async def think(self, info, thinking_prompt: ThinkingPrompt) -> Dict[str, str]:
        """Make agent think"""
        return await rest_think(
            agent_prompt=thinking_prompt,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )

    @strawberry.mutation
    async def delete_browsed_link(
        self, info, agent_name: str, url_input: UrlInput
    ) -> ResponseMessageType:
        """Delete browsed link"""
        result = await rest_delete_browsed_link(
            agent_name=agent_name,
            url=url_input,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def delete_provider(
        self, info, agent_name: str, provider_name: str
    ) -> ResponseMessageType:
        """Delete provider"""
        result = await rest_delete_provider(
            agent_id=agent_name,
            provider_name=provider_name,
            user=await get_user_from_context(info),
            authorization=info.context["request"].headers.get("authorization"),
        )
        return ResponseMessageType.from_pydantic(result)


schema = strawberry.Schema(query=Query, mutation=Mutation)
