from typing import List, Dict, Any, Optional
import strawberry
from fastapi import HTTPException
from Models import CommandExecution
from ApiClient import verify_api_key, is_admin
from endpoints.Extension import (
    get_extension_settings as rest_get_extension_settings,
    get_command_args as rest_get_command_args,
    get_extensions as rest_get_extensions,
    get_agent_extensions as rest_get_agent_extensions,
    run_command as rest_run_command,
)


""" get_agent_extensions output:
{"extensions": [{"extension_settings": {'sendgrid_email': {'SENDGRID_API_KEY': '', 'SENDGRID_EMAIL': ''},
 'postgres_database': {'POSTGRES_DATABASE_NAME': '',
  'POSTGRES_DATABASE_HOST': '',
  'POSTGRES_DATABASE_PORT': 5432,
  'POSTGRES_DATABASE_USERNAME': '',
  'POSTGRES_DATABASE_PASSWORD': ''},
 'google_search': {'GOOGLE_API_KEY': '', 'GOOGLE_SEARCH_ENGINE_ID': ''},
 'mysql_database': {'MYSQL_DATABASE_NAME': '',
  'MYSQL_DATABASE_HOST': '',
  'MYSQL_DATABASE_PORT': 3306,
  'MYSQL_DATABASE_USERNAME': '',
  'MYSQL_DATABASE_PASSWORD': ''},
 'oura': {'OURA_API_KEY': ''},
 'discord': {'DISCORD_API_KEY': '', 'DISCORD_COMMAND_PREFIX': '/AGiXT'},
 'github': {'GITHUB_USERNAME': '', 'GITHUB_API_KEY': ''},
 'AGiXT Chains': {'Think twice': {'user_input': ''}}]}
"""

""" get_extensions output:
{"extensions":
[{'extension_name': 'Long Term Memory',
  'description': "The Long Term Memory extension enables AGiXT to create and manage persistent memory databases.\nIt provides commands for:\n- Creating specialized memory databases for different types of information\n- Organizing and storing memories in structured tables\n- Retrieving specific memories through SQL queries\n- Tracking metadata about stored knowledge\n- Managing the evolution of memory organization over time\n\nThis extension allows agents to maintain their own organized, searchable knowledge bases\nthat persist across conversations. This acts as the assistant's very long-term memory.",
  'settings': [],
  'commands': [{'friendly_name': 'Create Memory Database',
    'description': 'Create a new memory database for storing and organizing information. This command should be used whenever the agent wants to:\n- Create a new category of memories or knowledge\n- Start tracking a new type of information\n- Organize related data in a structured way\n\nExamples of when to use this command:\n- Creating a database for learning progress in a specific subject\n- Starting a database for tracking project-related information\n- Creating a database for storing research findings\n- Making a database for conversation summaries\n- Creating specialized databases for different types of technical knowledge\n\nArgs:\nname (str): Name of the database (e.g., "russian_learning", "project_memories", "technical_docs")\ndescription (str): Detailed description of what this database stores and its purpose\n\nReturns:\nstr: Success message confirming database creation\n\nExample Usage:\n<execute>\n<name>Create Memory Database</name>\n<name>russian_vocabulary</name>\n<description>Database for storing Russian vocabulary words, phrases, and usage examples learned during conversations, including difficulty levels and practice timestamps.</description>\n</execute>',
    'command_name': 'create_memory_database',
    'command_args': {'name': '', 'description': ''}},
   {'friendly_name': 'Remember This',
    'description': "Store new information in the assistant's long-term memory. This command should be used when:\n- Learning new information that should be remembered later\n- Saving important facts, concepts, or insights\n- Recording structured information for future reference\n- Creating persistent knowledge that should be available across conversations\n- Building up knowledge bases for specific topics\n\nThe assistant will:\n- Analyze what type of information is being stored\n- Choose or create an appropriate memory database\n- Design or use existing table structures\n- Store the information with relevant metadata\n- Verify successful storage\n\nArgs:\ncontent (str): The information to remember (e.g., facts, concepts, structured data)\nmemory_type (str, optional): Category or type of memory to help with organization\n\nExample Usage:\n<execute>\n<name>Store in Long Term Memory</name>\n<content>The word 'полка' means 'shelf' in Russian. Common usage is 'Книга на полке' meaning 'The book is on the shelf'. This is a frequently used noun in household contexts.</content>\n<memory_type>russian_vocabulary</memory_type>\n</execute>\n\nReturns:\nstr: Confirmation of what was stored and where it can be found",
    'command_name': 'store_memory',
    'command_args': {'content': '', 'memory_type': ''}},
   {'friendly_name': 'List Memory Databases',
    'description': 'List all available memory databases and their descriptions. This command should be used when:\n- Deciding which database to store new information in\n- Looking for existing knowledge on a topic\n- Planning where to organize new information\n- Reviewing available knowledge categories\n- Checking when databases were last updated\n\nThe command returns a CSV formatted list containing:\n- Database names\n- Their descriptions\n- Creation dates\n- Last modification dates\n\nThis is particularly useful for:\n- Finding the right database for storing new information\n- Discovering existing knowledge bases\n- Maintaining organization of memories\n- Tracking knowledge evolution over time\n\nReturns:\nstr: CSV formatted list of all memory databases with their metadata\n\nExample Output:\n```csv\n"Database Name","Description","Created Date","Last Modified"\n"russian_vocabulary","Storage for Russian language learning progress","2024-01-01 12:00:00","2024-01-02 15:30:00"\n"project_notes","Technical documentation and decision history for current project","2024-01-01 09:00:00","2024-01-02 14:45:00"\n```',
    'command_name': 'list_memory_databases',
    'command_args': {}}]
}
"""

""" get_commands output:
{"commands":
{'Create Memory Database': False,
 'Remember This': False,
 'List Memory Databases': False,
 'Update Memory Database Description': False,
 'Retrieve Memories': False,
 'Send Email with Sendgrid': False,
 }
 }
"""


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
