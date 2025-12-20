from fastapi import APIRouter, HTTPException, Depends, Header
from Extensions import Extensions
from ApiClient import Agent, Conversations, verify_api_key, get_api_client, is_admin
from MagicalAuth import require_scope
from Models import CommandExecution, CommandArgs, ExtensionsModel, ExtensionSettings
from XT import AGiXT
from DB import get_db_session, ExtensionCategory, Extension
from typing import Dict, Any, List
import logging

app = APIRouter()


@app.get(
    "/api/extension/categories",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=Dict[str, List[Dict[str, Any]]],
    summary="Get Extension Categories",
    description="Retrieves all available extension categories.",
)
async def get_extension_categories(user=Depends(verify_api_key)):
    try:
        with get_db_session() as session:
            categories = session.query(ExtensionCategory).all()
            categories_data = []
            for category in categories:
                categories_data.append(
                    {
                        "id": str(category.id),
                        "name": category.name,
                        "description": category.description or "",
                        "extension_count": (
                            len(category.extensions) if category.extensions else 0
                        ),
                    }
                )
            return {"categories": categories_data}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve extension categories: {str(e)}"
        )


@app.get(
    "/api/extensions/settings",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=ExtensionSettings,
    summary="Get Extension Settings",
    description="Retrieves all extension settings for the authenticated user. This includes settings for all available extensions and chains.",
)
async def get_extension_settings(user=Depends(verify_api_key)):
    # try:
    ApiClient = get_api_client()
    ext = Extensions(user=user, ApiClient=ApiClient)
    return {"extension_settings": ext.get_extension_settings()}


@app.get(
    "/v1/extensions/settings",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=ExtensionSettings,
    summary="Get Extension Settings",
    description="Retrieves all extension settings for the authenticated user. This includes settings for all available extensions and chains.",
)
async def get_extension_settings_v1(user=Depends(verify_api_key)):
    ApiClient = get_api_client()
    ext = Extensions(user=user, ApiClient=ApiClient)
    return {"extension_settings": ext.get_extension_settings()}


@app.get(
    "/api/extensions/{command_name}/args",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=CommandArgs,
    summary="Get Command Arguments",
    description="Retrieves the available arguments for a specific command.",
)
async def get_command_args(command_name: str, user=Depends(verify_api_key)):
    return {"command_args": Extensions().get_command_args(command_name=command_name)}


@app.get(
    "/v1/extensions/{command_name}/args",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=CommandArgs,
    summary="Get Command Arguments",
    description="Retrieves the available arguments for a specific command.",
)
async def get_command_args_v1(command_name: str, user=Depends(verify_api_key)):
    return {"command_args": Extensions().get_command_args(command_name=command_name)}


@app.get(
    "/api/extensions",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=ExtensionsModel,
    summary="Get All Extensions",
    description="Retrieves all available extensions and their commands for the authenticated user.",
)
async def get_extensions(user=Depends(verify_api_key)):
    ext = Extensions(user=user)
    extensions = ext.get_extensions()
    return {"extensions": extensions}


@app.get(
    "/v1/agent/{agent_id}/extensions",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ExtensionsModel,
    summary="Get Agent Extensions by ID",
    description="Retrieves all extensions and their enabled/disabled status for a specific agent using agent ID.",
)
async def get_agent_extensions_v1(agent_id: str, user=Depends(verify_api_key)):
    ApiClient = get_api_client()
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    extensions = agent.get_agent_extensions()
    return {"extensions": extensions}


@app.post(
    "/v1/agent/{agent_id}/command",
    tags=["Agent"],
    dependencies=[
        Depends(verify_api_key),
        Depends(require_scope("extensions:execute")),
    ],
    response_model=Dict[str, Any],
    summary="Execute Agent Command by ID",
    description="Executes a specific command for an agent using agent ID. Requires extensions:execute scope.",
)
async def run_command_v1(
    agent_id: str,
    command: CommandExecution,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_name = agent.agent_name

    command_output = await AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=command.conversation_name,
    ).execute_command(
        command_name=command.command_name,
        command_args=command.command_args,
    )
    if (
        command.conversation_name != ""
        and command.conversation_name != None
        and command_output != None
    ):
        c = Conversations(conversation_name=command.conversation_name, user=user)
        c.log_interaction(role=agent_name, message=command_output)
    return {
        "response": command_output,
    }


# V1 Extension Categories Lightweight endpoint for staged loading
@app.get(
    "/v1/extension/categories/summary",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=List[Dict[str, Any]],
    summary="Get Extension Categories Summary",
    description="Get lightweight summary of extension categories. Returns only category names, descriptions and counts - no extension data. Use /v1/extension/category/{id} to load full extension data on demand.",
)
async def get_extension_categories_summary(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Lightweight endpoint for staged extension loading.
    Returns only category metadata without extension details.
    Use GET /v1/extension/category/{id} to load full extension data when user expands a category.
    """
    try:
        ApiClient = get_api_client(authorization=authorization)
        with get_db_session() as session:
            categories = session.query(ExtensionCategory).all()

            # Get all extensions to count them per category
            extensions_obj = Extensions(ApiClient=ApiClient, user=user)
            all_extensions = extensions_obj.get_extensions()

            # Build a quick lookup of extension counts per category
            category_counts = {}
            for extension in all_extensions:
                # Special handling for Custom Automation
                if extension["extension_name"] == "Custom Automation":
                    core_abilities = (
                        session.query(ExtensionCategory)
                        .filter_by(name="Core Abilities")
                        .first()
                    )
                    if core_abilities:
                        cat_id = str(core_abilities.id)
                        category_counts[cat_id] = category_counts.get(cat_id, 0) + 1
                    continue

                ext_db = (
                    session.query(Extension)
                    .filter_by(name=extension["extension_name"])
                    .first()
                )
                if ext_db and ext_db.category_id:
                    cat_id = str(ext_db.category_id)
                    category_counts[cat_id] = category_counts.get(cat_id, 0) + 1

            result = []
            for category in categories:
                cat_id = str(category.id)
                count = category_counts.get(cat_id, 0)
                # Only include categories that have extensions
                if count > 0:
                    result.append(
                        {
                            "id": cat_id,
                            "name": category.name,
                            "description": category.description or "",
                            "extension_count": count,
                        }
                    )

            return result
    except Exception as e:
        logging.error(f"Error getting extension categories summary: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving extension categories: {str(e)}"
        )


# V1 Extension Categories endpoints (ID-based)
@app.get(
    "/v1/extension/categories",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=List[Dict[str, Any]],
    summary="Get Extension Categories",
    description="Get all extension categories with ID-based structure. Only returns categories that have extensions.",
)
async def get_extension_categories_v1(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """Get all extension categories with their associated extensions"""
    try:
        ApiClient = get_api_client(authorization=authorization)
        with get_db_session() as session:
            categories = session.query(ExtensionCategory).all()

            # Get all extensions with category information
            extensions_obj = Extensions(ApiClient=ApiClient, user=user)
            all_extensions = extensions_obj.get_extensions()

            # First, enrich extensions with category information
            for extension in all_extensions:
                # Special handling for Custom Automation - it's dynamically generated
                if extension["extension_name"] == "Custom Automation":
                    # Custom Automation should be in Core Abilities
                    core_abilities = (
                        session.query(ExtensionCategory)
                        .filter_by(name="Core Abilities")
                        .first()
                    )
                    if core_abilities:
                        extension["category_info"] = {
                            "id": str(core_abilities.id),
                            "name": core_abilities.name,
                            "description": core_abilities.description,
                        }
                    else:
                        extension["category_info"] = None
                    continue

                ext_db = (
                    session.query(Extension)
                    .filter_by(name=extension["extension_name"])
                    .first()
                )
                if ext_db and ext_db.category_id:
                    category = (
                        session.query(ExtensionCategory)
                        .filter_by(id=ext_db.category_id)
                        .first()
                    )
                    if category:
                        extension["category_info"] = {
                            "id": str(category.id),
                            "name": category.name,
                            "description": category.description,
                        }
                    else:
                        extension["category_info"] = None
                else:
                    extension["category_info"] = None

            result = []
            for category in categories:
                # Find extensions that belong to this category
                category_extensions = []
                for extension in all_extensions:
                    category_info = extension.get("category_info")
                    if category_info and category_info.get("id") == str(category.id):
                        category_extensions.append(
                            {
                                "name": extension["extension_name"],
                                "friendly_name": extension.get("friendly_name"),
                                "description": extension.get("description", ""),
                                "settings": extension.get("settings", []),
                                "commands": extension.get("commands", []),
                            }
                        )

                # Only include categories that have extensions
                if len(category_extensions) > 0:
                    result.append(
                        {
                            "id": str(category.id),
                            "name": category.name,
                            "description": category.description,
                            "extensions": category_extensions,
                            "extension_count": len(category_extensions),
                        }
                    )

            return result
    except Exception as e:
        logging.error(f"Error getting extension categories: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving extension categories: {str(e)}"
        )


@app.get(
    "/v1/extension/category/{category_id}",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=Dict[str, Any],
    summary="Get Extension Category by ID",
    description="Get a specific extension category by ID with full extension data including commands and settings.",
)
async def get_extension_category_v1(
    category_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """Get a specific extension category by ID with its full extension data"""
    try:
        ApiClient = get_api_client(authorization=authorization)
        with get_db_session() as session:
            category = (
                session.query(ExtensionCategory).filter_by(id=category_id).first()
            )
            if not category:
                raise HTTPException(
                    status_code=404, detail="Extension category not found"
                )

            # Get extensions for this category
            extensions_obj = Extensions(ApiClient=ApiClient, user=user)
            all_extensions = extensions_obj.get_extensions()

            # First enrich all extensions with category_info
            for extension in all_extensions:
                # Special handling for Custom Automation
                if extension["extension_name"] == "Custom Automation":
                    core_abilities = (
                        session.query(ExtensionCategory)
                        .filter_by(name="Core Abilities")
                        .first()
                    )
                    if core_abilities:
                        extension["category_info"] = {
                            "id": str(core_abilities.id),
                            "name": core_abilities.name,
                            "description": core_abilities.description,
                        }
                    else:
                        extension["category_info"] = None
                    continue

                ext_db = (
                    session.query(Extension)
                    .filter_by(name=extension["extension_name"])
                    .first()
                )
                if ext_db and ext_db.category_id:
                    ext_category = (
                        session.query(ExtensionCategory)
                        .filter_by(id=ext_db.category_id)
                        .first()
                    )
                    if ext_category:
                        extension["category_info"] = {
                            "id": str(ext_category.id),
                            "name": ext_category.name,
                            "description": ext_category.description,
                        }
                    else:
                        extension["category_info"] = None
                else:
                    extension["category_info"] = None

            category_extensions = []
            for extension in all_extensions:
                if extension.get("category_info", {}).get("id") == str(category.id):
                    category_extensions.append(
                        {
                            "name": extension["extension_name"],
                            "friendly_name": extension.get("friendly_name"),
                            "description": extension.get("description", ""),
                            "settings": extension.get("settings", []),
                            "commands": extension.get("commands", []),
                        }
                    )

            return {
                "id": str(category.id),
                "name": category.name,
                "description": category.description,
                "extensions": category_extensions,
                "extension_count": len(category_extensions),
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting extension category {category_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving extension category: {str(e)}"
        )


@app.get(
    "/v1/extensions",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=List[Dict[str, Any]],
    summary="Get All Extensions with Categories",
    description="Get all extensions with category information using ID-based structure.",
)
async def get_extensions_v1(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """Get all extensions with category information"""
    try:
        ApiClient = get_api_client(authorization=authorization)
        extensions_obj = Extensions(ApiClient=ApiClient)
        extensions = extensions_obj.get_extensions()

        # Add category information to each extension
        with get_db_session() as session:
            for extension in extensions:
                ext_db = (
                    session.query(Extension)
                    .filter_by(name=extension["extension_name"])
                    .first()
                )
                if ext_db and ext_db.category_id:
                    category = (
                        session.query(ExtensionCategory)
                        .filter_by(id=ext_db.category_id)
                        .first()
                    )
                    if category:
                        extension["category_info"] = {
                            "id": str(category.id),
                            "name": category.name,
                            "description": category.description,
                        }
                    else:
                        extension["category_info"] = None
                else:
                    # If no database entry, create one with the category from the extension class
                    default_category = (
                        session.query(ExtensionCategory)
                        .filter_by(name="Automation")
                        .first()
                    )
                    if default_category:
                        extension["category_info"] = {
                            "id": str(default_category.id),
                            "name": default_category.name,
                            "description": default_category.description,
                        }
                    else:
                        extension["category_info"] = None

        return extensions
    except Exception as e:
        logging.error(f"Error getting extensions: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving extensions: {str(e)}"
        )


@app.get(
    "/v1/extensions/category/{category_id}",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=List[Dict[str, Any]],
    summary="Get Extensions by Category",
    description="Get all extensions that belong to a specific category.",
)
async def get_extensions_by_category_v1(
    category_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """Get all extensions that belong to a specific category"""
    try:
        ApiClient = get_api_client(authorization=authorization)

        # Verify category exists
        with get_db_session() as session:
            category = (
                session.query(ExtensionCategory).filter_by(id=category_id).first()
            )
            if not category:
                raise HTTPException(
                    status_code=404, detail="Extension category not found"
                )

        # Get all extensions and filter by category
        extensions_obj = Extensions(ApiClient=ApiClient)
        all_extensions = extensions_obj.get_extensions()

        category_extensions = []
        for extension in all_extensions:
            if extension.get("category_info", {}).get("id") == category_id:
                category_extensions.append(extension)

        return category_extensions
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting extensions by category {category_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving extensions by category: {str(e)}"
        )
