"""
Server Configuration Endpoints

These endpoints allow super admins to manage server-level configuration
through the UI instead of requiring environment variable changes.
"""

import os
from fastapi import APIRouter, Header, HTTPException, Depends
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from MagicalAuth import MagicalAuth, verify_api_key
from DB import (
    ServerConfig,
    get_session,
    SERVER_CONFIG_DEFINITIONS,
    encrypt_config_value,
    decrypt_config_value,
    set_server_config,
    get_server_config,
    ServerExtensionCommand,
    CompanyExtensionCommand,
)
from Globals import invalidate_server_config_cache, load_server_config_cache, getenv
import logging

app = APIRouter()


# Pydantic Models
class ServerConfigItem(BaseModel):
    """A single server configuration item."""

    name: str
    value: Optional[str] = None
    category: str
    description: Optional[str] = None
    value_type: str = "string"
    default_value: Optional[str] = None
    is_sensitive: bool = False
    is_required: bool = False


class ServerConfigUpdate(BaseModel):
    """Request to update a server configuration value."""

    name: str
    value: str


class ServerConfigBulkUpdate(BaseModel):
    """Request to update multiple server configuration values."""

    configs: List[ServerConfigUpdate]


class ServerConfigResponse(BaseModel):
    """Response containing server configuration."""

    configs: List[ServerConfigItem]
    categories: List[str]


class PublicConfigResponse(BaseModel):
    """
    Public configuration that can be fetched without authentication.
    Used by the frontend to get app name, URIs, and feature flags.
    """

    app_name: str
    app_description: str
    app_uri: str
    agixt_server: str
    footer_message: str
    allow_email_sign_in: bool
    file_upload_enabled: bool
    voice_input_enabled: bool
    rlhf_enabled: bool
    allow_message_editing: bool
    allow_message_deletion: bool
    show_override_switches: str
    registration_disabled: bool


# Helper functions
def verify_super_admin(authorization: str) -> MagicalAuth:
    """Verify that the user is a super admin."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Super admin role required.",
        )
    return auth


def mask_sensitive_value(value: str, is_sensitive: bool) -> str:
    """Mask sensitive values for display, showing only first/last few characters."""
    if not is_sensitive or not value:
        return value
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}{'•' * (len(value) - 8)}{value[-4:]}"


# Endpoints
@app.get(
    "/v1/server/config/public",
    tags=["Server Config"],
    response_model=PublicConfigResponse,
    summary="Get public server configuration",
    description="Get public configuration values that the frontend needs. No authentication required.",
)
async def get_public_config():
    """
    Get public server configuration values.
    These are safe to expose without authentication and are needed by the frontend.
    """
    return PublicConfigResponse(
        app_name=getenv("APP_NAME", "AGiXT"),
        app_description=getenv(
            "APP_DESCRIPTION",
            "AGiXT is an advanced artificial intelligence agent orchestration platform.",
        ),
        app_uri=getenv("APP_URI", "http://localhost:3437"),
        agixt_server=getenv(
            "AGIXT_SERVER", getenv("AGIXT_URI", "http://localhost:7437")
        ),
        footer_message=getenv("AGIXT_FOOTER_MESSAGE", "AGiXT 2025"),
        allow_email_sign_in=getenv("ALLOW_EMAIL_SIGN_IN", "true").lower() == "true",
        file_upload_enabled=getenv("AGIXT_FILE_UPLOAD_ENABLED", "true").lower()
        == "true",
        voice_input_enabled=getenv("AGIXT_VOICE_INPUT_ENABLED", "true").lower()
        == "true",
        rlhf_enabled=getenv("AGIXT_RLHF", "true").lower() == "true",
        allow_message_editing=getenv("AGIXT_ALLOW_MESSAGE_EDITING", "true").lower()
        == "true",
        allow_message_deletion=getenv("AGIXT_ALLOW_MESSAGE_DELETION", "true").lower()
        == "true",
        show_override_switches=getenv(
            "AGIXT_SHOW_OVERRIDE_SWITCHES", "tts,websearch,analyze-user-input"
        ),
        registration_disabled=getenv("REGISTRATION_DISABLED", "false").lower()
        == "true",
    )


@app.get(
    "/v1/server/config",
    tags=["Server Config"],
    response_model=ServerConfigResponse,
    summary="Get all server configuration (super admin only)",
    description="Super admin endpoint to retrieve all server configuration values.",
    dependencies=[Depends(verify_api_key)],
)
async def get_all_server_config(
    authorization: str = Header(None),
    category: Optional[str] = None,
    include_sensitive: bool = False,
):
    """
    Get all server configuration values (super admin only).

    Args:
        category: Optional filter by category
        include_sensitive: If False, sensitive values are masked

    Returns:
        List of configuration items with their current values
    """
    verify_super_admin(authorization)

    configs = []
    categories = set()

    with get_session() as db:
        query = db.query(ServerConfig)
        if category:
            query = query.filter(ServerConfig.category == category)

        db_configs = {c.name: c for c in query.all()}

        # Use definitions to ensure we include all config items
        for definition in SERVER_CONFIG_DEFINITIONS:
            if category and definition.get("category") != category:
                continue

            name = definition["name"]
            categories.add(definition.get("category", "general"))

            db_config = db_configs.get(name)

            if db_config:
                value = db_config.value
                if db_config.is_sensitive:
                    # Decrypt for comparison, then mask or return based on include_sensitive
                    decrypted = decrypt_config_value(value) if value else ""
                    if include_sensitive:
                        value = decrypted
                    else:
                        value = mask_sensitive_value(decrypted, True)

                configs.append(
                    ServerConfigItem(
                        name=name,
                        value=value,
                        category=db_config.category,
                        description=db_config.description,
                        value_type=db_config.value_type,
                        default_value=db_config.default_value,
                        is_sensitive=db_config.is_sensitive,
                        is_required=db_config.is_required,
                    )
                )
            else:
                # Config not in database, use definition
                configs.append(
                    ServerConfigItem(
                        name=name,
                        value=None,
                        category=definition.get("category", "general"),
                        description=definition.get("description"),
                        value_type=definition.get("value_type", "string"),
                        default_value=definition.get("default_value"),
                        is_sensitive=definition.get("is_sensitive", False),
                        is_required=definition.get("is_required", False),
                    )
                )

    return ServerConfigResponse(configs=configs, categories=sorted(list(categories)))


@app.get(
    "/v1/server/config/{config_name}",
    tags=["Server Config"],
    response_model=ServerConfigItem,
    summary="Get a specific server configuration (super admin only)",
    description="Super admin endpoint to retrieve a specific configuration value.",
    dependencies=[Depends(verify_api_key)],
)
async def get_server_config_item(
    config_name: str,
    authorization: str = Header(None),
    include_sensitive: bool = False,
):
    """
    Get a specific server configuration value (super admin only).
    """
    verify_super_admin(authorization)

    with get_session() as db:
        config = db.query(ServerConfig).filter(ServerConfig.name == config_name).first()

        if not config:
            # Check if it's a valid config name from definitions
            definition = next(
                (d for d in SERVER_CONFIG_DEFINITIONS if d["name"] == config_name), None
            )
            if not definition:
                raise HTTPException(
                    status_code=404, detail=f"Configuration '{config_name}' not found"
                )
            # Return definition with no value set
            return ServerConfigItem(
                name=config_name,
                value=None,
                category=definition.get("category", "general"),
                description=definition.get("description"),
                value_type=definition.get("value_type", "string"),
                default_value=definition.get("default_value"),
                is_sensitive=definition.get("is_sensitive", False),
                is_required=definition.get("is_required", False),
            )

        value = config.value
        if config.is_sensitive:
            decrypted = decrypt_config_value(value) if value else ""
            if include_sensitive:
                value = decrypted
            else:
                value = mask_sensitive_value(decrypted, True)

        return ServerConfigItem(
            name=config.name,
            value=value,
            category=config.category,
            description=config.description,
            value_type=config.value_type,
            default_value=config.default_value,
            is_sensitive=config.is_sensitive,
            is_required=config.is_required,
        )


@app.put(
    "/v1/server/config/{config_name}",
    tags=["Server Config"],
    summary="Update a server configuration (super admin only)",
    description="Super admin endpoint to update a specific configuration value.",
    dependencies=[Depends(verify_api_key)],
)
async def update_server_config_item(
    config_name: str,
    update: ServerConfigUpdate,
    authorization: str = Header(None),
):
    """
    Update a specific server configuration value (super admin only).
    Automatically encrypts sensitive values.
    """
    auth = verify_super_admin(authorization)

    if update.name != config_name:
        raise HTTPException(
            status_code=400, detail="Config name in URL must match name in request body"
        )

    # Find definition to check if this is a valid config
    definition = next(
        (d for d in SERVER_CONFIG_DEFINITIONS if d["name"] == config_name), None
    )
    if not definition:
        raise HTTPException(
            status_code=400, detail=f"Unknown configuration key: {config_name}"
        )

    with get_session() as db:
        config = db.query(ServerConfig).filter(ServerConfig.name == config_name).first()

        if config:
            # Update existing config
            if config.is_sensitive and update.value:
                config.value = encrypt_config_value(update.value)
            else:
                config.value = update.value
        else:
            # Create new config from definition
            is_sensitive = definition.get("is_sensitive", False)
            new_config = ServerConfig(
                name=config_name,
                value=(
                    encrypt_config_value(update.value)
                    if is_sensitive and update.value
                    else update.value
                ),
                category=definition.get("category", "general"),
                is_sensitive=is_sensitive,
                is_required=definition.get("is_required", False),
                description=definition.get("description"),
                value_type=definition.get("value_type", "string"),
                default_value=definition.get("default_value"),
            )
            db.add(new_config)

        db.commit()

    # Invalidate cache to pick up new value
    invalidate_server_config_cache()
    load_server_config_cache()

    logging.info(f"Server config '{config_name}' updated by user {auth.user_id}")

    return {"status": "success", "message": f"Configuration '{config_name}' updated"}


@app.put(
    "/v1/server/config",
    tags=["Server Config"],
    summary="Bulk update server configurations (super admin only)",
    description="Super admin endpoint to update multiple configuration values at once.",
    dependencies=[Depends(verify_api_key)],
)
async def bulk_update_server_config(
    updates: ServerConfigBulkUpdate,
    authorization: str = Header(None),
):
    """
    Bulk update server configuration values (super admin only).
    """
    auth = verify_super_admin(authorization)

    updated = []
    errors = []

    with get_session() as db:
        for update in updates.configs:
            config_name = update.name

            # Find definition
            definition = next(
                (d for d in SERVER_CONFIG_DEFINITIONS if d["name"] == config_name), None
            )
            if not definition:
                errors.append(f"Unknown configuration key: {config_name}")
                continue

            config = (
                db.query(ServerConfig).filter(ServerConfig.name == config_name).first()
            )

            if config:
                if config.is_sensitive and update.value:
                    config.value = encrypt_config_value(update.value)
                else:
                    config.value = update.value
            else:
                is_sensitive = definition.get("is_sensitive", False)
                new_config = ServerConfig(
                    name=config_name,
                    value=(
                        encrypt_config_value(update.value)
                        if is_sensitive and update.value
                        else update.value
                    ),
                    category=definition.get("category", "general"),
                    is_sensitive=is_sensitive,
                    is_required=definition.get("is_required", False),
                    description=definition.get("description"),
                    value_type=definition.get("value_type", "string"),
                    default_value=definition.get("default_value"),
                )
                db.add(new_config)

            updated.append(config_name)

        db.commit()

    # Invalidate cache to pick up new values
    invalidate_server_config_cache()
    load_server_config_cache()

    logging.info(
        f"Server configs bulk updated by user {auth.user_id}: {', '.join(updated)}"
    )

    return {
        "status": "success",
        "updated": updated,
        "errors": errors,
        "message": f"Updated {len(updated)} configuration(s)",
    }


@app.get(
    "/v1/server/config/categories",
    tags=["Server Config"],
    summary="Get available configuration categories",
    description="Get a list of all configuration categories for UI organization.",
    dependencies=[Depends(verify_api_key)],
)
async def get_config_categories(
    authorization: str = Header(None),
):
    """
    Get a list of all configuration categories.
    """
    verify_super_admin(authorization)

    categories = set()
    for definition in SERVER_CONFIG_DEFINITIONS:
        categories.add(definition.get("category", "general"))

    # Category metadata for UI
    category_info = {
        "app_settings": {
            "name": "Application Settings",
            "description": "General application configuration",
            "icon": "settings",
        },
        "uris": {
            "name": "Server URIs",
            "description": "API and application endpoint URLs",
            "icon": "globe",
        },
        "ai_providers": {
            "name": "AI Providers",
            "description": "API keys and models for AI services",
            "icon": "brain",
        },
        "oauth": {
            "name": "OAuth Providers",
            "description": "OAuth client credentials for SSO",
            "icon": "key",
        },
        "storage": {
            "name": "Storage",
            "description": "S3, Azure, and other storage backends",
            "icon": "database",
        },
        "billing": {
            "name": "Billing",
            "description": "Token pricing and payment settings",
            "icon": "credit-card",
        },
        "extensions": {
            "name": "Extensions Hub",
            "description": "Extension repository configuration",
            "icon": "puzzle",
        },
        "notifications": {
            "name": "Notifications",
            "description": "Webhook and notification settings",
            "icon": "bell",
        },
        "agent_defaults": {
            "name": "Agent Defaults",
            "description": "Default settings for new agents",
            "icon": "bot",
        },
        "features": {
            "name": "Feature Flags",
            "description": "Enable/disable UI features",
            "icon": "toggle-left",
        },
    }

    return {
        "categories": [
            {
                "key": cat,
                **category_info.get(
                    cat,
                    {
                        "name": cat.replace("_", " ").title(),
                        "description": "",
                        "icon": "folder",
                    },
                ),
            }
            for cat in sorted(categories)
        ]
    }


# ============================================================================
# Server Extension Settings Endpoints
# ============================================================================

from DB import (
    ServerExtensionSetting,
    CompanyExtensionSetting,
    get_new_id,
)
from Extensions import Extensions


class ExtensionSettingItem(BaseModel):
    """A single extension setting item."""

    extension_name: str
    setting_key: str
    setting_value: Optional[str] = None
    is_sensitive: bool = False
    description: Optional[str] = None


class ExtensionSettingUpdate(BaseModel):
    """Request to update an extension setting."""

    extension_name: str
    setting_key: str
    setting_value: str


class ExtensionSettingBulkUpdate(BaseModel):
    """Request to update multiple extension settings."""

    settings: List[ExtensionSettingUpdate]


class ExtensionWithSettings(BaseModel):
    """Extension with its available settings."""

    extension_name: str
    friendly_name: str
    category: str
    settings: List[ExtensionSettingItem]


class ServerExtensionSettingsResponse(BaseModel):
    """Response containing server extension settings organized by extension."""

    extensions: List[ExtensionWithSettings]


@app.get(
    "/v1/server/extension-settings",
    tags=["Server Extension Settings"],
    response_model=ServerExtensionSettingsResponse,
    summary="Get all server extension settings (super admin only)",
    description="Get all extension settings with their server-level default values.",
    dependencies=[Depends(verify_api_key)],
)
async def get_server_extension_settings(
    authorization: str = Header(None),
):
    """
    Get all server extension settings.
    Returns all available extensions with their settings and current server-level values.
    """
    verify_super_admin(authorization)

    # Get all available extension settings from Extensions class
    ext = Extensions()
    all_settings = ext.get_extension_settings()

    # Also get extension metadata for friendly names and categories
    # Use lowercase keys for case-insensitive matching
    extensions_data = ext.get_extensions()
    extension_meta = {}
    for ext_data in extensions_data:
        extension_meta[ext_data["extension_name"].lower()] = {
            "friendly_name": ext_data.get("friendly_name")
            or ext_data["extension_name"],
            "category": ext_data.get("category") or "Other",
        }

    # Get current server-level values from database
    with get_session() as db:
        db_settings = db.query(ServerExtensionSetting).all()
        db_values = {}
        for setting in db_settings:
            key = f"{setting.extension_name}:{setting.setting_key}"
            value = setting.setting_value
            if setting.is_sensitive and value:
                value = decrypt_config_value(value)
            db_values[key] = {
                "value": value,
                "is_sensitive": setting.is_sensitive,
                "description": setting.description,
            }

    # Build response
    extensions = []
    for extension_name, settings in all_settings.items():
        meta = extension_meta.get(extension_name.lower(), {})
        friendly_name = meta.get("friendly_name") or extension_name
        category = meta.get("category") or "Other"

        setting_items = []
        # Map of alternative env var names for common settings
        # Some env vars use different naming conventions (e.g., EZLOCALAI_URI vs EZLOCALAI_API_URI)
        ALT_ENV_VAR_NAMES = {
            "EZLOCALAI_API_URI": ["EZLOCALAI_URI"],
            "OPENAI_API_URI": ["OPENAI_BASE_URI", "OPENAI_URI"],
            "OPENAI_AI_MODEL": ["OPENAI_MODEL"],
            "ANTHROPIC_AI_MODEL": ["ANTHROPIC_MODEL"],
            "GOOGLE_AI_MODEL": ["GOOGLE_MODEL"],
            "AZURE_AI_MODEL": ["AZURE_MODEL"],
            "XAI_AI_MODEL": ["XAI_MODEL"],
            "DEEPSEEK_AI_MODEL": ["DEEPSEEK_MODEL"],
        }

        for setting_key, default_value in settings.items():
            db_key = f"{extension_name}:{setting_key}"
            db_data = db_values.get(db_key, {})

            # Determine if this is a sensitive setting (API keys, secrets, etc.)
            is_sensitive = db_data.get("is_sensitive", False)
            if not is_sensitive:
                # Check for sensitive keywords but exclude false positives like MAX_TOKENS
                upper_key = setting_key.upper()
                is_sensitive = any(
                    kw in upper_key
                    for kw in [
                        "API_KEY",
                        "SECRET",
                        "PASSWORD",
                        "PRIVATE_KEY",
                        "ACCESS_TOKEN",
                        "REFRESH_TOKEN",
                        "AUTH_TOKEN",
                        "BEARER_TOKEN",
                    ]
                )

            # Check database first, then fall back to environment variable
            current_value = db_data.get("value") if db_key in db_values else None
            if current_value is None:
                # Fall back to environment variable - check primary name first
                env_value = os.getenv(setting_key)
                if not env_value:
                    # Check alternative env var names
                    for alt_name in ALT_ENV_VAR_NAMES.get(setting_key, []):
                        env_value = os.getenv(alt_name)
                        if env_value:
                            break
                if env_value:
                    current_value = env_value

            # Mask sensitive values
            if is_sensitive and current_value:
                current_value = mask_sensitive_value(current_value, True)

            setting_items.append(
                ExtensionSettingItem(
                    extension_name=extension_name,
                    setting_key=setting_key,
                    setting_value=current_value,
                    is_sensitive=is_sensitive,
                    description=db_data.get(
                        "description", f"Configure {setting_key} for {friendly_name}"
                    ),
                )
            )

        if setting_items:
            extensions.append(
                ExtensionWithSettings(
                    extension_name=extension_name,
                    friendly_name=friendly_name,
                    category=category,
                    settings=setting_items,
                )
            )

    # Sort by category then name
    extensions.sort(key=lambda x: (x.category, x.friendly_name))

    return ServerExtensionSettingsResponse(extensions=extensions)


@app.put(
    "/v1/server/extension-settings",
    tags=["Server Extension Settings"],
    summary="Update server extension settings (super admin only)",
    description="Update server-level default values for extension settings.",
    dependencies=[Depends(verify_api_key)],
)
async def update_server_extension_settings(
    updates: ExtensionSettingBulkUpdate,
    authorization: str = Header(None),
):
    """
    Update server extension settings.
    These become the default values for all companies.
    """
    verify_super_admin(authorization)

    updated = []
    errors = []

    with get_session() as db:
        for update in updates.settings:
            try:
                # Check if setting exists
                existing = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == update.extension_name,
                        ServerExtensionSetting.setting_key == update.setting_key,
                    )
                    .first()
                )

                # Determine if sensitive
                is_sensitive = any(
                    kw in update.setting_key.upper()
                    for kw in ["API_KEY", "SECRET", "PASSWORD", "TOKEN", "PRIVATE"]
                )

                # Encrypt if sensitive
                value = update.setting_value
                if is_sensitive and value:
                    value = encrypt_config_value(value)

                if existing:
                    existing.setting_value = value
                    existing.is_sensitive = is_sensitive
                else:
                    new_setting = ServerExtensionSetting(
                        id=get_new_id(),
                        extension_name=update.extension_name,
                        setting_key=update.setting_key,
                        setting_value=value,
                        is_sensitive=is_sensitive,
                        description=f"Server-level default for {update.setting_key}",
                    )
                    db.add(new_setting)

                updated.append(f"{update.extension_name}:{update.setting_key}")
            except Exception as e:
                errors.append(f"{update.extension_name}:{update.setting_key}: {str(e)}")

        db.commit()

    return {
        "status": "success" if not errors else "partial",
        "updated": updated,
        "errors": errors,
        "message": f"Updated {len(updated)} extension settings"
        + (f" with {len(errors)} errors" if errors else ""),
    }


@app.delete(
    "/v1/server/extension-settings/{extension_name}/{setting_key}",
    tags=["Server Extension Settings"],
    summary="Delete a server extension setting (super admin only)",
    description="Remove a server-level extension setting, reverting to extension default.",
    dependencies=[Depends(verify_api_key)],
)
async def delete_server_extension_setting(
    extension_name: str,
    setting_key: str,
    authorization: str = Header(None),
):
    """
    Delete a server extension setting.
    The setting will revert to the extension's default value.
    """
    verify_super_admin(authorization)

    with get_session() as db:
        setting = (
            db.query(ServerExtensionSetting)
            .filter(
                ServerExtensionSetting.extension_name == extension_name,
                ServerExtensionSetting.setting_key == setting_key,
            )
            .first()
        )

        if not setting:
            raise HTTPException(
                status_code=404,
                detail=f"Setting {extension_name}:{setting_key} not found",
            )

        db.delete(setting)
        db.commit()

    return {
        "status": "success",
        "message": f"Deleted setting {extension_name}:{setting_key}",
    }


# ============================================================================
# Server Extension Command Endpoints (for enabling/disabling commands)
# ============================================================================


class CommandStateItem(BaseModel):
    """A single command state item."""

    extension_name: str
    command_name: str
    enabled: bool


class ExtensionCommandsResponse(BaseModel):
    """Response containing extension commands with their states."""

    extensions: List[Dict[str, Any]]


class CommandStateUpdate(BaseModel):
    """Request to update a command's enabled state."""

    extension_name: str
    command_name: str
    enabled: bool


class BulkCommandUpdate(BaseModel):
    """Request to update multiple command states."""

    commands: List[CommandStateUpdate]


@app.get(
    "/v1/server/extension-commands",
    tags=["Server Extension Commands"],
    summary="Get all server extension command states (super admin only)",
    description="Returns all extensions with their commands and server-level enabled states.",
    dependencies=[Depends(verify_api_key)],
)
async def get_server_extension_commands(
    authorization: str = Header(None),
):
    """
    Get all server-level extension command states.
    Returns all available extensions with their commands and whether each
    command is enabled at the server level (default for all companies).
    """
    verify_super_admin(authorization)

    # Import Extensions class to get available extensions and commands
    from Extensions import Extensions

    extensions_manager = Extensions(agent_config={})
    available_extensions = extensions_manager.get_extensions()

    # Load server-level command states
    with get_session() as db:
        server_commands = db.query(ServerExtensionCommand).all()
        server_command_states = {
            f"{cmd.extension_name}:{cmd.command_name}": cmd.enabled
            for cmd in server_commands
        }

    # Build response with all extensions and their commands
    result = []
    for ext in available_extensions:
        ext_name = ext.get("extension_name", "")
        commands = ext.get("commands", [])

        command_list = []
        for cmd in commands:
            cmd_name = cmd.get("friendly_name", "") or cmd.get("name", "")
            if not cmd_name:
                continue

            # Check server-level state
            key = f"{ext_name}:{cmd_name}"
            enabled = server_command_states.get(key, False)

            command_list.append(
                {
                    "command_name": cmd_name,
                    "enabled": enabled,
                    "description": cmd.get("description", ""),
                }
            )

        if command_list:
            result.append(
                {
                    "extension_name": ext_name,
                    "friendly_name": ext.get("friendly_name", ext_name),
                    "category": ext.get("category", "Other"),
                    "commands": command_list,
                }
            )

    # Sort by extension name
    result.sort(key=lambda x: x["extension_name"].lower())

    return {"extensions": result}


@app.put(
    "/v1/server/extension-commands",
    tags=["Server Extension Commands"],
    summary="Update server extension command states (super admin only)",
    description="Set enabled/disabled state for commands at server level.",
    dependencies=[Depends(verify_api_key)],
)
async def update_server_extension_commands(
    updates: BulkCommandUpdate,
    authorization: str = Header(None),
):
    """
    Update server-level extension command states.
    These serve as defaults for all companies - commands enabled here
    will be available to all users unless overridden at company level.
    """
    verify_super_admin(authorization)

    updated = []
    errors = []

    with get_session() as db:
        for update in updates.commands:
            try:
                existing = (
                    db.query(ServerExtensionCommand)
                    .filter(
                        ServerExtensionCommand.extension_name == update.extension_name,
                        ServerExtensionCommand.command_name == update.command_name,
                    )
                    .first()
                )

                if existing:
                    existing.enabled = update.enabled
                else:
                    new_cmd = ServerExtensionCommand(
                        extension_name=update.extension_name,
                        command_name=update.command_name,
                        enabled=update.enabled,
                    )
                    db.add(new_cmd)

                updated.append(f"{update.extension_name}:{update.command_name}")
            except Exception as e:
                errors.append(
                    f"{update.extension_name}:{update.command_name}: {str(e)}"
                )

        db.commit()

    return {
        "status": "success" if not errors else "partial",
        "updated": updated,
        "errors": errors,
        "message": f"Updated {len(updated)} command states"
        + (f" with {len(errors)} errors" if errors else ""),
    }


@app.delete(
    "/v1/server/extension-commands/{extension_name}/{command_name}",
    tags=["Server Extension Commands"],
    summary="Delete a server extension command state (super admin only)",
    description="Remove a server-level command state, reverting to disabled.",
    dependencies=[Depends(verify_api_key)],
)
async def delete_server_extension_command(
    extension_name: str,
    command_name: str,
    authorization: str = Header(None),
):
    """
    Delete a server extension command state.
    The command will revert to disabled at server level.
    """
    verify_super_admin(authorization)

    with get_session() as db:
        cmd = (
            db.query(ServerExtensionCommand)
            .filter(
                ServerExtensionCommand.extension_name == extension_name,
                ServerExtensionCommand.command_name == command_name,
            )
            .first()
        )

        if not cmd:
            raise HTTPException(
                status_code=404,
                detail=f"Command state {extension_name}:{command_name} not found",
            )

        db.delete(cmd)
        db.commit()

    return {
        "status": "success",
        "message": f"Deleted command state {extension_name}:{command_name}",
    }


# ============================================================================
# OAuth Provider Settings Endpoints
# ============================================================================


class OAuthProviderSetting(BaseModel):
    """A single OAuth provider setting."""

    setting_key: str
    setting_value: Optional[str] = None
    is_sensitive: bool = False
    description: str = ""


class OAuthProviderItem(BaseModel):
    """An OAuth provider with its settings."""

    provider_name: str
    friendly_name: str
    scopes: List[str] = []
    authorize_url: Optional[str] = None
    pkce_required: bool = False
    is_configured: bool = False
    settings: List[OAuthProviderSetting] = []


class OAuthProvidersResponse(BaseModel):
    """Response containing all OAuth providers."""

    providers: List[OAuthProviderItem]


class OAuthProviderSettingUpdate(BaseModel):
    """Request to update an OAuth provider setting."""

    provider_name: str
    setting_key: str
    setting_value: str


class OAuthProviderSettingsUpdateRequest(BaseModel):
    """Request to update multiple OAuth provider settings."""

    settings: List[OAuthProviderSettingUpdate]


def find_extension_files():
    """Find all extension files recursively."""
    extension_files = []

    # Check main extensions directory
    extensions_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "extensions"
    )
    if os.path.exists(extensions_dir):
        for f in os.listdir(extensions_dir):
            if f.endswith(".py") and not f.startswith("_"):
                extension_files.append(os.path.join(extensions_dir, f))

    # Check extensions hub if configured
    hub_path = os.getenv("EXTENSIONS_HUB_PATH")
    if hub_path and os.path.exists(hub_path):
        for f in os.listdir(hub_path):
            if f.endswith(".py") and not f.startswith("_"):
                extension_files.append(os.path.join(hub_path, f))

    return extension_files


def import_extension_module(extension_file: str):
    """Safely import an extension module."""
    import importlib.util

    try:
        filename = os.path.basename(extension_file)
        module_name = filename.replace(".py", "")
        spec = importlib.util.spec_from_file_location(module_name, extension_file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    except Exception:
        pass
    return None


@app.get(
    "/v1/server/oauth-providers",
    tags=["Server OAuth Providers"],
    response_model=OAuthProvidersResponse,
    summary="Get all OAuth provider settings (super admin only)",
    description="Get all OAuth providers with their settings and current server-level values.",
    dependencies=[Depends(verify_api_key)],
)
async def get_server_oauth_providers(
    authorization: str = Header(None),
):
    """
    Get all OAuth providers and their settings.
    OAuth providers are extensions that support SSO login.
    """
    verify_super_admin(authorization)

    providers = []
    extension_files = find_extension_files()

    for extension_file in extension_files:
        module = import_extension_module(extension_file)
        if module is None:
            continue

        filename = os.path.basename(extension_file)
        module_name = filename.replace(".py", "")

        # Check if this is an OAuth provider (has SCOPES, AUTHORIZE, SSO class)
        has_scopes = hasattr(module, "SCOPES")
        has_authorize = hasattr(module, "AUTHORIZE")
        has_sso_class = any(
            hasattr(module, f"{module_name.capitalize()}SSO")
            or hasattr(module, f"{module_name.upper()}SSO")
            for _ in [1]
        )
        has_sso_function = hasattr(module, "sso")

        if not (has_scopes and has_authorize and (has_sso_class or has_sso_function)):
            continue

        # This is an OAuth provider
        provider_upper = module_name.upper()
        client_id_key = f"{provider_upper}_CLIENT_ID"
        client_secret_key = f"{provider_upper}_CLIENT_SECRET"

        # Get current values from environment
        client_id = os.getenv(client_id_key)
        client_secret = os.getenv(client_secret_key)

        settings = [
            OAuthProviderSetting(
                setting_key=client_id_key,
                setting_value=(
                    mask_sensitive_value(client_id, True) if client_id else None
                ),
                is_sensitive=True,
                description=f"OAuth Client ID for {module_name.capitalize()}",
            ),
            OAuthProviderSetting(
                setting_key=client_secret_key,
                setting_value=(
                    mask_sensitive_value(client_secret, True) if client_secret else None
                ),
                is_sensitive=True,
                description=f"OAuth Client Secret for {module_name.capitalize()}",
            ),
        ]

        providers.append(
            OAuthProviderItem(
                provider_name=module_name,
                friendly_name=module_name.replace("_", " ").title(),
                scopes=getattr(module, "SCOPES", []),
                authorize_url=getattr(module, "AUTHORIZE", None),
                pkce_required=getattr(module, "PKCE_REQUIRED", False),
                is_configured=bool(client_id and client_secret),
                settings=settings,
            )
        )

    # Sort by configured first, then by name
    providers.sort(key=lambda x: (not x.is_configured, x.friendly_name))

    return OAuthProvidersResponse(providers=providers)


@app.put(
    "/v1/server/oauth-providers",
    tags=["Server OAuth Providers"],
    summary="Update OAuth provider settings (super admin only)",
    description="Update OAuth provider CLIENT_ID and CLIENT_SECRET values.",
    dependencies=[Depends(verify_api_key)],
)
async def update_server_oauth_providers(
    request: OAuthProviderSettingsUpdateRequest,
    authorization: str = Header(None),
):
    """
    Update OAuth provider settings.
    These are stored in the ServerExtensionSetting table.
    """
    verify_super_admin(authorization)

    updated = []
    errors = []

    with get_session() as db:
        for setting in request.settings:
            try:
                # Validate this is a valid OAuth setting key
                if not (
                    setting.setting_key.endswith("_CLIENT_ID")
                    or setting.setting_key.endswith("_CLIENT_SECRET")
                ):
                    errors.append(f"Invalid OAuth setting key: {setting.setting_key}")
                    continue

                # Store in ServerExtensionSetting with provider name as extension_name
                existing = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == setting.provider_name,
                        ServerExtensionSetting.setting_key == setting.setting_key,
                    )
                    .first()
                )

                # Encrypt sensitive values
                encrypted_value = encrypt_config_value(setting.setting_value)

                if existing:
                    existing.setting_value = encrypted_value
                    existing.is_sensitive = True
                else:
                    new_setting = ServerExtensionSetting(
                        extension_name=setting.provider_name,
                        setting_key=setting.setting_key,
                        setting_value=encrypted_value,
                        is_sensitive=True,
                        description=f"OAuth setting for {setting.provider_name}",
                    )
                    db.add(new_setting)

                # Also update in-memory environment for immediate use
                os.environ[setting.setting_key] = setting.setting_value

                updated.append(f"{setting.provider_name}:{setting.setting_key}")
            except Exception as e:
                errors.append(
                    f"Error updating {setting.provider_name}:{setting.setting_key}: {str(e)}"
                )

        db.commit()

    return {
        "status": "success" if not errors else "partial",
        "updated": updated,
        "errors": errors,
    }
