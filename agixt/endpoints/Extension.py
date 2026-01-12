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
    from fastapi.responses import JSONResponse
    import logging

    ApiClient = get_api_client()
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    extensions = agent.get_agent_extensions()
    # Return with no-cache headers to prevent stale responses after command toggles
    return JSONResponse(
        content={"extensions": extensions},
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


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
        log_activities=True,
        log_output=True,
    )
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
            category_map = {str(c.id): c for c in categories}

            # Batch load all extensions with category_id in one query
            all_ext_db = session.query(Extension).all()
            ext_to_category = {
                e.name: str(e.category_id) if e.category_id else None
                for e in all_ext_db
            }

            # Find Core Abilities category for Custom Automation
            core_abilities_id = None
            for c in categories:
                if c.name == "Core Abilities":
                    core_abilities_id = str(c.id)
                    break

            # Get all extensions to count them per category
            extensions_obj = Extensions(ApiClient=ApiClient, user=user)
            all_extensions = extensions_obj.get_extensions()

            # Build a quick lookup of extension counts per category using batch-loaded data
            category_counts = {}
            for extension in all_extensions:
                ext_name = extension["extension_name"]

                # Special handling for Custom Automation
                if ext_name == "Custom Automation":
                    cat_id = core_abilities_id
                else:
                    cat_id = ext_to_category.get(ext_name)

                if cat_id:
                    category_counts[cat_id] = category_counts.get(cat_id, 0) + 1

            result = []
            for cat_id, count in category_counts.items():
                # Only include categories that have extensions and exist in map
                if count > 0 and cat_id in category_map:
                    category = category_map[cat_id]
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
            # Batch load all categories
            categories = session.query(ExtensionCategory).all()
            category_map = {str(c.id): c for c in categories}

            # Batch load all extensions with their category_id in one query
            all_ext_db = session.query(Extension).all()
            ext_to_category = {
                e.name: str(e.category_id) if e.category_id else None
                for e in all_ext_db
            }

            # Find Core Abilities category for Custom Automation
            core_abilities_id = None
            for c in categories:
                if c.name == "Core Abilities":
                    core_abilities_id = str(c.id)
                    break

            # Get all extensions from the Extensions class
            extensions_obj = Extensions(ApiClient=ApiClient, user=user)
            all_extensions = extensions_obj.get_extensions()

            # Group extensions by category using pre-loaded data
            category_extensions_map = {}
            for extension in all_extensions:
                ext_name = extension["extension_name"]

                # Special handling for Custom Automation
                if ext_name == "Custom Automation":
                    cat_id = core_abilities_id
                else:
                    cat_id = ext_to_category.get(ext_name)

                if cat_id:
                    if cat_id not in category_extensions_map:
                        category_extensions_map[cat_id] = []
                    category_extensions_map[cat_id].append(
                        {
                            "name": ext_name,
                            "friendly_name": extension.get("friendly_name"),
                            "description": extension.get("description", ""),
                            "settings": extension.get("settings", []),
                            "commands": extension.get("commands", []),
                        }
                    )

            # Build result only for categories that have extensions
            result = []
            for cat_id, cat_extensions in category_extensions_map.items():
                if cat_id in category_map:
                    category = category_map[cat_id]
                    result.append(
                        {
                            "id": cat_id,
                            "name": category.name,
                            "description": category.description,
                            "extensions": cat_extensions,
                            "extension_count": len(cat_extensions),
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

            # Batch load all extensions with their category_id in one query
            all_ext_db = session.query(Extension).all()
            ext_to_category = {
                e.name: str(e.category_id) if e.category_id else None
                for e in all_ext_db
            }

            # Find Core Abilities category for Custom Automation
            core_abilities = (
                session.query(ExtensionCategory)
                .filter_by(name="Core Abilities")
                .first()
            )
            core_abilities_id = str(core_abilities.id) if core_abilities else None

            # Get extensions for this category
            extensions_obj = Extensions(ApiClient=ApiClient, user=user)
            all_extensions = extensions_obj.get_extensions()

            # Filter extensions for this category using batch-loaded data
            category_extensions = []
            for extension in all_extensions:
                ext_name = extension["extension_name"]

                # Special handling for Custom Automation
                if ext_name == "Custom Automation":
                    ext_cat_id = core_abilities_id
                else:
                    ext_cat_id = ext_to_category.get(ext_name)

                if ext_cat_id == str(category.id):
                    category_extensions.append(
                        {
                            "name": ext_name,
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

        # Batch load all extension to category mappings in one query
        with get_db_session() as session:
            # Load all extension DB records
            all_ext_db = session.query(Extension).all()
            ext_to_category_id = {e.name: e.category_id for e in all_ext_db}

            # Load all categories
            all_categories = session.query(ExtensionCategory).all()
            category_map = {c.id: c for c in all_categories}

            # Get default Automation category
            default_category = next(
                (c for c in all_categories if c.name == "Automation"), None
            )

            # Add category info using batch-loaded data
            for extension in extensions:
                ext_name = extension["extension_name"]
                cat_id = ext_to_category_id.get(ext_name)

                if cat_id and cat_id in category_map:
                    category = category_map[cat_id]
                    extension["category_info"] = {
                        "id": str(category.id),
                        "name": category.name,
                        "description": category.description,
                    }
                elif default_category:
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
