"""
Server Configuration Endpoints

These endpoints allow super admins to manage server-level configuration
through the UI instead of requiring environment variable changes.
"""

import os
from fastapi import APIRouter, Header, HTTPException, Depends, Request
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from MagicalAuth import MagicalAuth, verify_api_key, send_email
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
    CompanyStorageSetting,
    Company,
    ServerExtensionSetting,
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
    agent_name: str
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
        agent_name=getenv("AGENT_NAME", getenv("AGIXT_AGENT", "XT")),
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

    # If EXTENSIONS_HUB was updated, hot-reload extension hubs
    if config_name == "EXTENSIONS_HUB":
        try:
            from ExtensionsHub import reload_extension_hubs

            reload_result = reload_extension_hubs()
            logging.info(f"Extension hub hot-reload result: {reload_result}")

            return {
                "status": "success",
                "message": f"Configuration '{config_name}' updated and extension hubs reloaded",
                "extension_reload": reload_result,
            }
        except Exception as e:
            logging.error(f"Failed to hot-reload extension hubs: {e}")
            return {
                "status": "success",
                "message": f"Configuration '{config_name}' updated (extension reload failed)",
                "extension_reload": {"success": False},
            }

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

    # If EXTENSIONS_HUB was updated, hot-reload extension hubs
    extension_reload = None
    if "EXTENSIONS_HUB" in updated:
        try:
            from ExtensionsHub import reload_extension_hubs

            extension_reload = reload_extension_hubs()
            logging.info(f"Extension hub hot-reload result: {extension_reload}")
        except Exception as e:
            logging.error(f"Failed to hot-reload extension hubs: {e}")
            extension_reload = {"success": False, "error": str(e)}

    logging.info(
        f"Server configs bulk updated by user {auth.user_id}: {', '.join(updated)}"
    )

    result = {
        "status": "success",
        "updated": updated,
        "errors": errors,
        "message": f"Updated {len(updated)} configuration(s)",
    }

    if extension_reload:
        result["extension_reload"] = extension_reload

    return result


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
                # Fall back to server config (checks env vars then database)
                env_value = getenv(setting_key)
                if not env_value:
                    # Check alternative env var names
                    for alt_name in ALT_ENV_VAR_NAMES.get(setting_key, []):
                        env_value = getenv(alt_name)
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
# Company Extension Settings Endpoints (for company admins to manage providers)
# ============================================================================


class CompanyExtensionSettingItem(BaseModel):
    """A single company extension setting item."""

    extension_name: str
    setting_key: str
    setting_value: Optional[str] = None
    is_sensitive: bool = False
    description: Optional[str] = None


class CompanyExtensionSettingUpdate(BaseModel):
    """Request to update a company extension setting."""

    extension_name: str
    setting_key: str
    setting_value: str


class CompanyExtensionSettingBulkUpdate(BaseModel):
    """Request to update multiple company extension settings."""

    settings: List[CompanyExtensionSettingUpdate]


class CompanyExtensionWithSettings(BaseModel):
    """Extension with its company-level settings."""

    extension_name: str
    friendly_name: str
    category: str
    settings: List[CompanyExtensionSettingItem]


class CompanyExtensionSettingsResponse(BaseModel):
    """Response containing company extension settings organized by extension."""

    extensions: List[CompanyExtensionWithSettings]


@app.get(
    "/v1/company/{company_id}/extension-settings",
    tags=["Company Extension Settings"],
    response_model=CompanyExtensionSettingsResponse,
    summary="Get company extension settings (company admin or super admin)",
    description="Get all extension settings with their company-level values. Company admins can view/edit their own company, super admins can access any company.",
    dependencies=[Depends(verify_api_key)],
)
async def get_company_extension_settings(
    company_id: str,
    authorization: str = Header(None),
):
    """
    Get all company extension settings.
    Returns all available extensions with their settings and current company-level values.
    Company admins can only access their own company, super admins can access any.
    """
    from Extensions import Extensions
    from DB import CompanyExtensionSetting

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization - must be company admin (role <= 2) or super admin
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins or super admins can manage company extension settings.",
        )

    # Get all available extension settings from Extensions class
    ext = Extensions()
    all_settings = ext.get_extension_settings()

    # Get extension metadata
    extensions_data = ext.get_extensions()
    extension_meta = {}
    for ext_data in extensions_data:
        extension_meta[ext_data["extension_name"].lower()] = {
            "friendly_name": ext_data.get("friendly_name")
            or ext_data["extension_name"],
            "category": ext_data.get("category") or "Other",
        }

    # Get current company-level values from database
    with get_session() as db:
        db_settings = (
            db.query(CompanyExtensionSetting)
            .filter(CompanyExtensionSetting.company_id == company_id)
            .all()
        )
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
        for setting_key, default_value in settings.items():
            db_key = f"{extension_name}:{setting_key}"
            db_data = db_values.get(db_key, {})

            # Determine if sensitive
            is_sensitive = db_data.get("is_sensitive", False)
            if not is_sensitive:
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

            # Get company-level value
            current_value = db_data.get("value") if db_key in db_values else None

            # Mask sensitive values
            if is_sensitive and current_value:
                current_value = mask_sensitive_value(current_value, True)

            setting_items.append(
                CompanyExtensionSettingItem(
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
                CompanyExtensionWithSettings(
                    extension_name=extension_name,
                    friendly_name=friendly_name,
                    category=category,
                    settings=setting_items,
                )
            )

    # Sort by category then name
    extensions.sort(key=lambda x: (x.category, x.friendly_name))

    return CompanyExtensionSettingsResponse(extensions=extensions)


@app.put(
    "/v1/company/{company_id}/extension-settings",
    tags=["Company Extension Settings"],
    summary="Update company extension settings (company admin or super admin)",
    description="Update company-level default values for extension settings.",
    dependencies=[Depends(verify_api_key)],
)
async def update_company_extension_settings(
    company_id: str,
    updates: CompanyExtensionSettingBulkUpdate,
    authorization: str = Header(None),
):
    """
    Update company extension settings.
    These become the default values for users in this company.
    """
    from DB import CompanyExtensionSetting, get_new_id

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins or super admins can manage company extension settings.",
        )

    updated = []
    errors = []

    with get_session() as db:
        for update in updates.settings:
            try:
                # Check if setting exists
                existing = (
                    db.query(CompanyExtensionSetting)
                    .filter(
                        CompanyExtensionSetting.company_id == company_id,
                        CompanyExtensionSetting.extension_name == update.extension_name,
                        CompanyExtensionSetting.setting_key == update.setting_key,
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
                    new_setting = CompanyExtensionSetting(
                        id=get_new_id(),
                        company_id=company_id,
                        extension_name=update.extension_name,
                        setting_key=update.setting_key,
                        setting_value=value,
                        is_sensitive=is_sensitive,
                        description=f"Company-level setting for {update.setting_key}",
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
        "message": f"Updated {len(updated)} company extension settings"
        + (f" with {len(errors)} errors" if errors else ""),
    }


@app.delete(
    "/v1/company/{company_id}/extension-settings/{extension_name}/{setting_key}",
    tags=["Company Extension Settings"],
    summary="Delete a company extension setting (company admin or super admin)",
    description="Remove a company-level extension setting, reverting to server default.",
    dependencies=[Depends(verify_api_key)],
)
async def delete_company_extension_setting(
    company_id: str,
    extension_name: str,
    setting_key: str,
    authorization: str = Header(None),
):
    """
    Delete a company extension setting.
    The setting will revert to server-level default or environment variable.
    """
    from DB import CompanyExtensionSetting

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins or super admins can manage company extension settings.",
        )

    with get_session() as db:
        setting = (
            db.query(CompanyExtensionSetting)
            .filter(
                CompanyExtensionSetting.company_id == company_id,
                CompanyExtensionSetting.extension_name == extension_name,
                CompanyExtensionSetting.setting_key == setting_key,
            )
            .first()
        )

        if not setting:
            raise HTTPException(
                status_code=404,
                detail=f"Company setting {extension_name}:{setting_key} not found",
            )

        db.delete(setting)
        db.commit()

    return {
        "status": "success",
        "message": f"Deleted company setting {extension_name}:{setting_key}. Will now use server default.",
    }


# ============================================================================
# Discord Bot Management Endpoints
# ============================================================================


class DiscordBotStatusResponse(BaseModel):
    """Response containing Discord bot status for a company."""

    company_id: str
    company_name: str
    is_running: bool
    started_at: Optional[str] = None
    guild_count: int = 0
    error: Optional[str] = None


class DiscordBotEnableRequest(BaseModel):
    """Request to enable/disable Discord bot for a company."""

    enabled: bool
    discord_bot_token: Optional[str] = None  # Only required when enabling


@app.get(
    "/v1/company/{company_id}/discord-bot/status",
    tags=["Company Discord Bot"],
    response_model=DiscordBotStatusResponse,
    summary="Get Discord bot status for company (company admin or super admin)",
    description="Get the current status of the Discord bot for a company.",
    dependencies=[Depends(verify_api_key)],
)
async def get_company_discord_bot_status(
    company_id: str,
    authorization: str = Header(None),
):
    """Get the Discord bot status for a company."""
    from DiscordBotManager import get_discord_bot_manager
    from DB import Company

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization - must be company admin (role <= 2) or super admin
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins or super admins can view Discord bot status.",
        )

    # Get company name
    with get_session() as db:
        company = db.query(Company).filter(Company.id == company_id).first()
        company_name = company.name if company else "Unknown"

    manager = get_discord_bot_manager()
    if not manager:
        return DiscordBotStatusResponse(
            company_id=company_id,
            company_name=company_name,
            is_running=False,
            error="Discord bot manager is not running",
        )

    status = manager.get_bot_status(company_id)
    if not status:
        return DiscordBotStatusResponse(
            company_id=company_id,
            company_name=company_name,
            is_running=False,
        )

    return DiscordBotStatusResponse(
        company_id=company_id,
        company_name=status.company_name,
        is_running=status.is_running,
        started_at=status.started_at.isoformat() if status.started_at else None,
        guild_count=status.guild_count,
        error=status.error,
    )


@app.post(
    "/v1/company/{company_id}/discord-bot/enable",
    tags=["Company Discord Bot"],
    summary="Enable or disable Discord bot for company (company admin or super admin)",
    description="Enable or disable the Discord bot for a company. When enabling, a Discord bot token is required.",
    dependencies=[Depends(verify_api_key)],
)
async def enable_company_discord_bot(
    company_id: str,
    request: DiscordBotEnableRequest,
    authorization: str = Header(None),
):
    """Enable or disable the Discord bot for a company."""
    from DiscordBotManager import get_discord_bot_manager
    from DB import CompanyExtensionSetting, get_new_id

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins or super admins can manage Discord bot.",
        )

    # Validate token if enabling
    if request.enabled and not request.discord_bot_token:
        # Check if token already exists in settings
        with get_session() as db:
            existing_token = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == "discord",
                    CompanyExtensionSetting.setting_key == "DISCORD_BOT_TOKEN",
                )
                .first()
            )
            if not existing_token or not existing_token.setting_value:
                raise HTTPException(
                    status_code=400,
                    detail="Discord bot token is required when enabling the bot.",
                )

    with get_session() as db:
        # Update or create the DISCORD_BOT_TOKEN setting if provided
        if request.discord_bot_token:
            existing_token = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == "discord",
                    CompanyExtensionSetting.setting_key == "DISCORD_BOT_TOKEN",
                )
                .first()
            )

            encrypted_token = encrypt_config_value(request.discord_bot_token)

            if existing_token:
                existing_token.setting_value = encrypted_token
                existing_token.is_sensitive = True
            else:
                new_setting = CompanyExtensionSetting(
                    id=get_new_id(),
                    company_id=company_id,
                    extension_name="discord",
                    setting_key="DISCORD_BOT_TOKEN",
                    setting_value=encrypted_token,
                    is_sensitive=True,
                    description="Discord bot token for company Discord bot",
                )
                db.add(new_setting)

        # Update or create the DISCORD_BOT_ENABLED setting
        existing_enabled = (
            db.query(CompanyExtensionSetting)
            .filter(
                CompanyExtensionSetting.company_id == company_id,
                CompanyExtensionSetting.extension_name == "discord",
                CompanyExtensionSetting.setting_key == "DISCORD_BOT_ENABLED",
            )
            .first()
        )

        enabled_value = "true" if request.enabled else "false"

        if existing_enabled:
            existing_enabled.setting_value = enabled_value
        else:
            new_setting = CompanyExtensionSetting(
                id=get_new_id(),
                company_id=company_id,
                extension_name="discord",
                setting_key="DISCORD_BOT_ENABLED",
                setting_value=enabled_value,
                is_sensitive=False,
                description="Whether the Discord bot is enabled for this company",
            )
            db.add(new_setting)

        db.commit()

    # Trigger bot sync
    manager = get_discord_bot_manager()
    if manager:
        try:
            await manager.sync_bots()
        except Exception as e:
            logging.error(f"Error syncing Discord bots: {e}")

    action = "enabled" if request.enabled else "disabled"
    return {
        "status": "success",
        "message": f"Discord bot {action} for company. Bot will start/stop within 60 seconds.",
    }


@app.post(
    "/v1/company/{company_id}/discord-bot/restart",
    tags=["Company Discord Bot"],
    summary="Restart Discord bot for company (company admin or super admin)",
    description="Restart the Discord bot for a company.",
    dependencies=[Depends(verify_api_key)],
)
async def restart_company_discord_bot(
    company_id: str,
    authorization: str = Header(None),
):
    """Restart the Discord bot for a company."""
    from DiscordBotManager import get_discord_bot_manager

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins or super admins can restart Discord bot.",
        )

    manager = get_discord_bot_manager()
    if not manager:
        raise HTTPException(
            status_code=503,
            detail="Discord bot manager is not running.",
        )

    # Stop and restart the bot
    await manager.stop_bot_for_company(company_id)
    await manager.sync_bots()

    return {
        "status": "success",
        "message": "Discord bot restart initiated. Bot will be back online shortly.",
    }


@app.get(
    "/v1/admin/discord-bots",
    tags=["Admin Discord Bots"],
    summary="Get all running Discord bots (super admin only)",
    description="Get status of all running Discord bots across all companies.",
    dependencies=[Depends(verify_api_key)],
)
async def get_all_discord_bots(
    authorization: str = Header(None),
):
    """Get status of all running Discord bots (super admin only)."""
    from DiscordBotManager import get_discord_bot_manager

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Super admin access required.",
        )

    manager = get_discord_bot_manager()
    if not manager:
        return {
            "status": "error",
            "message": "Discord bot manager is not running",
            "bots": [],
        }

    statuses = manager.get_status()
    return {
        "status": "success",
        "bots": [
            {
                "company_id": s.company_id,
                "company_name": s.company_name,
                "is_running": s.is_running,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "guild_count": s.guild_count,
                "error": s.error,
            }
            for s in statuses.values()
        ],
    }


# ============================================================================
# Multi-Platform Bot Management Endpoints
# ============================================================================


class BotStatusResponse(BaseModel):
    """Generic response for bot status."""

    company_id: str
    company_name: str
    platform: str
    is_running: bool
    started_at: Optional[str] = None
    messages_processed: int = 0
    error: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class BotPermissionMode:
    """Permission modes for bot interactions."""

    OWNER_ONLY = "owner_only"  # Only the user who set up the bot can interact
    RECOGNIZED_USERS = "recognized_users"  # Only users with AGiXT accounts can interact
    ANYONE = "anyone"  # Anyone can interact with the bot


class BotEnableRequest(BaseModel):
    """Request to enable/disable a bot for a company."""

    enabled: bool
    settings: Optional[Dict[str, str]] = None  # Platform-specific settings
    agent_id: Optional[str] = None  # The specific agent ID to use for this bot
    permission_mode: Optional[str] = None  # owner_only, recognized_users, or anyone


class AllBotsStatusResponse(BaseModel):
    """Response containing status for all bot platforms."""

    discord: Optional[BotStatusResponse] = None
    slack: Optional[BotStatusResponse] = None
    teams: Optional[BotStatusResponse] = None
    x: Optional[BotStatusResponse] = None
    facebook: Optional[BotStatusResponse] = None
    telegram: Optional[BotStatusResponse] = None
    whatsapp: Optional[BotStatusResponse] = None
    microsoft_email: Optional[BotStatusResponse] = None
    google_email: Optional[BotStatusResponse] = None
    sendgrid_email: Optional[BotStatusResponse] = None
    twilio_sms: Optional[BotStatusResponse] = None


class DeployedBotInfo(BaseModel):
    """Information about a deployed bot."""

    id: str  # Unique identifier (company_id + platform)
    platform: str  # Platform identifier (discord, slack, etc.)
    platform_name: str  # Display name
    company_id: str
    company_name: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    enabled: bool  # Whether the bot is configured as enabled
    is_running: bool  # Whether the bot is actually running
    is_paused: bool = False  # Whether the bot is paused (enabled but not running intentionally)
    is_server_level: bool = False  # Whether this is a server-level bot (vs company-level)
    permission_mode: str = "recognized_users"
    permission_mode_label: str = "Recognized Users"
    permission_privacy: str = "private"  # "private" or "public"
    status: str = "offline"  # running, paused, offline, error
    status_message: Optional[str] = None
    started_at: Optional[str] = None
    messages_processed: int = 0
    uses_oauth: bool = False
    oauth_connected: bool = False
    oauth_provider: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error: Optional[str] = None


class DeployedBotsResponse(BaseModel):
    """Response containing list of deployed bots."""

    bots: List[DeployedBotInfo]
    total_count: int
    running_count: int
    paused_count: int
    error_count: int


class BotPauseRequest(BaseModel):
    """Request to pause/unpause a bot."""

    paused: bool


# Bot permission modes with privacy levels
# PRIVATE modes: Only specific users can interact
# PUBLIC modes: Open to a wider audience
BOT_PERMISSION_MODES = [
    {
        "value": "owner_only",
        "label": "Owner Only",
        "description": "Only you can interact with the bot",
        "privacy": "private",
    },
    {
        "value": "recognized_users",
        "label": "Recognized Users",
        "description": "Users within your company who have linked their account",
        "privacy": "private",
    },
    {
        "value": "allowlist",
        "label": "Allowlist Only",
        "description": "Only users you manually add to the allowlist can interact",
        "privacy": "private",
    },
    {
        "value": "app_users",
        "label": "{app_name} Users",
        "description": "Anyone with an account on {app_name}, regardless of company",
        "privacy": "public",
    },
    {
        "value": "anyone",
        "label": "Anyone",
        "description": "Anyone can interact with the bot (no account required)",
        "privacy": "public",
    },
]

def get_permission_modes_with_app_name():
    """Get permission modes with app_name substituted."""
    from Globals import getenv
    app_name = getenv("APP_NAME") or "AGiXT"
    modes = []
    for mode in BOT_PERMISSION_MODES:
        mode_copy = mode.copy()
        mode_copy["label"] = mode_copy["label"].replace("{app_name}", app_name)
        mode_copy["description"] = mode_copy["description"].replace("{app_name}", app_name)
        modes.append(mode_copy)
    return modes


# Platform-specific setting requirements
# Platforms can use OAuth (oauth_provider set) or manual tokens (required settings)
# When oauth_provider is set, the bot uses OAuth credentials from the selected agent's connections
BOT_PLATFORM_SETTINGS = {
    "discord": {
        "required": ["DISCORD_BOT_TOKEN"],  # Discord bots need their own bot token (not user OAuth)
        "optional": [
            "DISCORD_BOT_ENABLED",
            "discord_bot_agent_id",
            "discord_bot_permission_mode",
            "discord_bot_owner_id",
            "discord_bot_allowlist",  # Comma-separated Discord user IDs
        ],
        "extension_name": "discord",
        "oauth_provider": None,  # Discord bot tokens are different from user OAuth
        "description": "Discord bots require a Bot Token from the Discord Developer Portal. User authentication uses OAuth.",
        "allowlist_type": "discord_user_ids",
        "allowlist_placeholder": "123456789012345678, 234567890123456789",
        "allowlist_help": "Enter Discord user IDs separated by commas. Right-click a user in Discord and select 'Copy User ID'.",
    },
    "slack": {
        "required": ["slack_bot_token", "slack_signing_secret"],
        "optional": [
            "slack_bot_enabled",
            "slack_bot_agent_id",
            "slack_bot_permission_mode",
            "slack_bot_owner_id",
            "slack_app_token",
            "slack_bot_allowlist",  # Comma-separated Slack user IDs
        ],
        "extension_name": "slack",
        "oauth_provider": None,  # Slack bots need app tokens, not user OAuth
        "description": "Slack bots require App-level tokens from the Slack API dashboard.",
        "allowlist_type": "slack_user_ids",
        "allowlist_placeholder": "U01234ABCDE, U05678FGHIJ",
        "allowlist_help": "Enter Slack user IDs (starting with 'U') separated by commas. Find user IDs in Slack user profiles.",
    },
    "teams": {
        "required": [],  # No longer required - use OAuth
        "optional": [
            "teams_bot_enabled",
            "teams_bot_agent_id",
            "teams_bot_permission_mode",
            "teams_bot_owner_id",
            "teams_bot_allowlist",  # Comma-separated Teams user IDs/emails
        ],
        "extension_name": "teams",
        "oauth_provider": "microsoft",  # Uses Microsoft OAuth
        "oauth_provider_display": "Microsoft",
        "description": "Connect your Microsoft account to enable Teams messaging.",
        "allowlist_type": "teams_user_ids",
        "allowlist_placeholder": "user@company.com, another@company.com",
        "allowlist_help": "Enter Microsoft/Teams email addresses separated by commas.",
    },
    "x": {
        "required": [],  # No longer required - use OAuth
        "optional": [
            "x_bot_enabled",
            "x_bot_agent_id",
            "x_bot_permission_mode",
            "x_bot_owner_id",
            "x_bot_allowlist",  # Comma-separated X/Twitter user IDs
        ],
        "extension_name": "x",
        "oauth_provider": "x",  # Uses X/Twitter OAuth
        "oauth_provider_display": "X (Twitter)",
        "description": "Connect your X account to enable posting and messaging.",
        "allowlist_type": "x_user_ids",
        "allowlist_placeholder": "elonmusk, jack, 12345678",
        "allowlist_help": "Enter X usernames (without @) or user IDs separated by commas.",
    },
    "facebook": {
        "required": [],  # No longer required - use OAuth
        "optional": [
            "facebook_bot_enabled",
            "facebook_bot_agent_id",
            "facebook_bot_permission_mode",
            "facebook_bot_owner_id",
            "facebook_bot_allowlist",  # Comma-separated Facebook user IDs
        ],
        "extension_name": "facebook",
        "oauth_provider": "facebook",  # Uses Facebook OAuth
        "oauth_provider_display": "Facebook",
        "description": "Connect your Facebook account and select a Page to enable messaging.",
        "allowlist_type": "facebook_user_ids",
        "allowlist_placeholder": "123456789012345, 234567890123456",
        "allowlist_help": "Enter Facebook user IDs (PSIDs from Messenger) separated by commas.",
    },
    "telegram": {
        "required": ["telegram_bot_token"],  # Telegram bots need BotFather tokens
        "optional": [
            "telegram_bot_enabled",
            "telegram_bot_agent_id",
            "telegram_bot_permission_mode",
            "telegram_bot_owner_id",
            "telegram_bot_allowlist",  # Comma-separated Telegram user IDs
        ],
        "extension_name": "telegram",
        "oauth_provider": None,  # Telegram bots use BotFather tokens, not OAuth
        "description": "Telegram bots require a token from @BotFather.",
        "allowlist_type": "telegram_user_ids",
        "allowlist_placeholder": "123456789, 987654321",
        "allowlist_help": "Enter Telegram user IDs (numbers) separated by commas. Users can get their ID from @userinfobot.",
    },
    "whatsapp": {
        "required": ["whatsapp_phone_number_id", "whatsapp_access_token"],
        "optional": [
            "whatsapp_bot_enabled",
            "whatsapp_bot_agent_id",
            "whatsapp_bot_permission_mode",
            "whatsapp_bot_owner_id",
            "whatsapp_bot_allowlist",  # Comma-separated phone numbers
        ],
        "extension_name": "whatsapp",
        "oauth_provider": None,  # WhatsApp Business API requires manual setup
        "description": "WhatsApp Business requires credentials from Meta Business Suite.",
        "allowlist_type": "phone_numbers",
        "allowlist_placeholder": "+1234567890, +0987654321",
        "allowlist_help": "Enter phone numbers with country code separated by commas (e.g., +1234567890).",
    },
    "microsoft_email": {
        "required": [],  # No longer required - use OAuth
        "optional": [
            "microsoft_email_bot_enabled",
            "microsoft_email_bot_agent_id",
            "microsoft_email_bot_permission_mode",
            "microsoft_email_bot_owner_id",
            "microsoft_email_bot_allowlist",  # Comma-separated email addresses
        ],
        "extension_name": "microsoft_email",
        "oauth_provider": "microsoft",  # Uses Microsoft OAuth
        "oauth_provider_display": "Microsoft (Outlook/365)",
        "description": "Connect your Microsoft account to enable email integration.",
        "allowlist_type": "email_addresses",
        "allowlist_placeholder": "user@example.com, client@company.com",
        "allowlist_help": "Enter email addresses separated by commas. Only emails from these senders will be processed.",
    },
    "google_email": {
        "required": [],  # No longer required - use OAuth
        "optional": [
            "google_email_bot_enabled",
            "google_email_bot_agent_id",
            "google_email_bot_permission_mode",
            "google_email_bot_owner_id",
            "google_email_bot_allowlist",  # Comma-separated email addresses
        ],
        "extension_name": "google_email",
        "oauth_provider": "google",  # Uses Google OAuth
        "oauth_provider_display": "Google (Gmail)",
        "description": "Connect your Google account to enable Gmail integration.",
        "allowlist_type": "email_addresses",
        "allowlist_placeholder": "user@example.com, client@company.com",
        "allowlist_help": "Enter email addresses separated by commas. Only emails from these senders will be processed.",
    },
    "sendgrid_email": {
        "required": ["SENDGRID_API_KEY", "SENDGRID_EMAIL"],
        "optional": [
            "sendgrid_email_bot_enabled",
            "sendgrid_email_bot_agent_id",
            "sendgrid_email_bot_permission_mode",
            "sendgrid_email_bot_owner_id",
            "sendgrid_email_bot_allowlist",  # Comma-separated email addresses
        ],
        "extension_name": "sendgrid_email",
        "oauth_provider": None,  # SendGrid uses API keys
        "description": "SendGrid requires an API key from the SendGrid dashboard.",
        "allowlist_type": "email_addresses",
        "allowlist_placeholder": "user@example.com, client@company.com",
        "allowlist_help": "Enter email addresses separated by commas. Only emails from these senders will be processed.",
    },
    "twilio_sms": {
        "required": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
        "optional": [
            "twilio_sms_bot_enabled",
            "twilio_sms_bot_agent_id",
            "twilio_sms_bot_permission_mode",
            "twilio_sms_bot_owner_id",
            "twilio_sms_bot_allowlist",  # Comma-separated phone numbers
        ],
        "extension_name": "twilio_sms",
        "oauth_provider": None,  # Twilio uses API credentials
        "description": "Twilio SMS requires credentials from the Twilio Console.",
        "allowlist_type": "phone_numbers",
        "allowlist_placeholder": "+1234567890, +0987654321",
        "allowlist_help": "Enter phone numbers with country code separated by commas (e.g., +1234567890).",
    },
    "github": {
        "required": [],  # Can use either token or GitHub App
        "optional": [
            "github_bot_enabled",
            "GITHUB_TOKEN",  # Personal access token (alternative to App)
            "GITHUB_APP_ID",  # GitHub App ID
            "GITHUB_APP_PRIVATE_KEY",  # GitHub App private key
            "GITHUB_WEBHOOK_SECRET",  # For verifying webhooks
            "github_bot_agent_id",
            "github_bot_permission_mode",
            "github_bot_owner_id",
            "github_bot_allowlist",  # Comma-separated GitHub usernames, repos, or orgs
            "github_bot_deployment_scope",  # single_repo, multi_repo, org, user
            "github_bot_target_repos",  # Comma-separated owner/repo list
            "github_bot_target_org",  # Organization name
            "github_bot_target_user",  # GitHub username
            "github_bot_auto_fix",  # Auto-fix issues
            "github_bot_auto_review",  # Auto-review PRs
            "github_bot_auto_tests",  # Auto-generate tests
        ],
        "extension_name": "github",
        "oauth_provider": None,  # Uses GitHub token or App credentials
        "description": "GitHub bot handles issues, PRs, and code reviews with AI assistance.",
        "allowlist_type": "github_identifiers",
        "allowlist_placeholder": "octocat, my-org, owner/repo",
        "allowlist_help": "Enter GitHub usernames, organization names, or repository names (owner/repo) separated by commas.",
    },
}


def _get_bot_manager(platform: str):
    """Get the bot manager for a specific platform."""
    try:
        if platform == "discord":
            from DiscordBotManager import get_discord_bot_status_from_redis

            return get_discord_bot_status_from_redis(company_id)
        elif platform == "slack":
            from SlackBotManager import get_slack_bot_manager

            return get_slack_bot_manager()
        elif platform == "teams":
            from TeamsBotManager import get_teams_bot_manager

            return get_teams_bot_manager()
        elif platform == "x":
            from XBotManager import get_x_bot_manager

            return get_x_bot_manager()
        elif platform == "facebook":
            from FacebookBotManager import get_facebook_bot_manager

            return get_facebook_bot_manager()
        elif platform == "telegram":
            from TelegramBotManager import get_telegram_bot_manager

            return get_telegram_bot_manager()
        elif platform == "whatsapp":
            from WhatsAppBotManager import get_whatsapp_bot_manager

            return get_whatsapp_bot_manager()
        elif platform == "microsoft_email":
            from MicrosoftEmailBotManager import get_microsoft_email_bot_manager

            return get_microsoft_email_bot_manager()
        elif platform == "google_email":
            from GoogleEmailBotManager import get_google_email_bot_manager

            return get_google_email_bot_manager()
        elif platform == "sendgrid_email":
            from SendGridEmailBotManager import get_sendgrid_email_bot_manager

            return get_sendgrid_email_bot_manager()
        elif platform == "twilio_sms":
            from TwilioSmsBotManager import get_twilio_sms_bot_manager

            return get_twilio_sms_bot_manager()
        elif platform == "github":
            from GitHubBotManager import get_github_bot_manager
            import asyncio
            return asyncio.get_event_loop().run_until_complete(get_github_bot_manager())
        return None
    except Exception as e:
        logging.warning(f"Error getting bot manager for {platform}: {e}")
        return None


def _get_bot_status_for_platform(
    platform: str, company_id: str, company_name: str
) -> Optional[BotStatusResponse]:
    """Get bot status for a specific platform and company."""
    try:
        # Special handling for Discord - it uses Redis for cross-process status
        if platform == "discord":
            from DiscordBotManager import get_discord_bot_status_from_redis
            
            status = get_discord_bot_status_from_redis(company_id)
            if not status:
                return BotStatusResponse(
                    company_id=company_id,
                    company_name=company_name,
                    platform=platform,
                    is_running=False,
                )
            
            return BotStatusResponse(
                company_id=company_id,
                company_name=status.company_name if hasattr(status, "company_name") else company_name,
                platform=platform,
                is_running=status.is_running if hasattr(status, "is_running") else False,
                started_at=(
                    status.started_at.isoformat()
                    if hasattr(status, "started_at") and status.started_at
                    else None
                ),
                messages_processed=0,
                error=status.error if hasattr(status, "error") else None,
                extra={"guild_count": status.guild_count} if hasattr(status, "guild_count") else None,
            )
        
        # For other platforms, use the manager pattern
        manager = _get_bot_manager(platform)
        if not manager:
            # Return "not running" status instead of null when manager unavailable
            return BotStatusResponse(
                company_id=company_id,
                company_name=company_name,
                platform=platform,
                is_running=False,
            )

        status = manager.get_bot_status(company_id)
        if not status:
            return BotStatusResponse(
                company_id=company_id,
                company_name=company_name,
                platform=platform,
                is_running=False,
            )

        # Build extra data based on platform
        extra = {}
        if platform == "discord" and hasattr(status, "guild_count"):
            extra["guild_count"] = status.guild_count

        return BotStatusResponse(
            company_id=company_id,
            company_name=(
                status.company_name if hasattr(status, "company_name") else company_name
            ),
            platform=platform,
            is_running=status.is_running if hasattr(status, "is_running") else False,
            started_at=(
                status.started_at.isoformat()
                if hasattr(status, "started_at") and status.started_at
                else None
            ),
            messages_processed=(
                status.messages_processed
                if hasattr(status, "messages_processed")
                else 0
            ),
            error=status.error if hasattr(status, "error") else None,
            extra=extra if extra else None,
        )
    except Exception as e:
        logging.warning(f"Error getting {platform} bot status: {e}")
        return None


@app.get(
    "/v1/company/{company_id}/bots",
    tags=["Company Bots"],
    response_model=AllBotsStatusResponse,
    summary="Get status of all bots for a company",
    description="Get the status of all bot platforms (Discord, Slack, Teams, X, Facebook, Telegram, WhatsApp) for a company.",
    dependencies=[Depends(verify_api_key)],
)
async def get_company_all_bots_status(
    company_id: str,
    authorization: str = Header(None),
):
    """Get the status of all bots for a company."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins or super admins can view bot status.",
        )

    # Get company name
    with get_session() as db:
        company = db.query(Company).filter(Company.id == company_id).first()
        company_name = company.name if company else "Unknown"

    return AllBotsStatusResponse(
        discord=_get_bot_status_for_platform("discord", company_id, company_name),
        slack=_get_bot_status_for_platform("slack", company_id, company_name),
        teams=_get_bot_status_for_platform("teams", company_id, company_name),
        x=_get_bot_status_for_platform("x", company_id, company_name),
        facebook=_get_bot_status_for_platform("facebook", company_id, company_name),
        telegram=_get_bot_status_for_platform("telegram", company_id, company_name),
        whatsapp=_get_bot_status_for_platform("whatsapp", company_id, company_name),
        microsoft_email=_get_bot_status_for_platform(
            "microsoft_email", company_id, company_name
        ),
        google_email=_get_bot_status_for_platform(
            "google_email", company_id, company_name
        ),
        sendgrid_email=_get_bot_status_for_platform(
            "sendgrid_email", company_id, company_name
        ),
        twilio_sms=_get_bot_status_for_platform("twilio_sms", company_id, company_name),
    )


@app.get(
    "/v1/company/{company_id}/deployed-bots",
    tags=["Company Bots"],
    response_model=DeployedBotsResponse,
    summary="Get list of deployed bots for a company",
    description="Get a list of all deployed (enabled) bots for a company with their status, agent, and configuration.",
    dependencies=[Depends(verify_api_key)],
)
async def get_company_deployed_bots(
    company_id: str,
    authorization: str = Header(None),
):
    """Get all deployed bots for a company."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins can view deployed bots.",
        )

    deployed_bots = []
    running_count = 0
    paused_count = 0
    error_count = 0

    with get_session() as db:
        company = db.query(Company).filter(Company.id == company_id).first()
        company_name = company.name if company else "Unknown"

        for platform, config in BOT_PLATFORM_SETTINGS.items():
            extension_name = config["extension_name"]
            
            # Check if bot is enabled for this platform
            enabled_key = f"{platform}_bot_enabled"
            if platform == "discord":
                enabled_key = "DISCORD_BOT_ENABLED"
            
            enabled_setting = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == extension_name,
                    CompanyExtensionSetting.setting_key == enabled_key,
                )
                .first()
            )
            
            is_enabled = enabled_setting and enabled_setting.setting_value and enabled_setting.setting_value.lower() == "true"
            
            if not is_enabled:
                continue  # Skip non-deployed bots
            
            # Get agent info
            agent_id_key = f"{platform}_bot_agent_id"
            if platform == "discord":
                agent_id_key = "discord_bot_agent_id"
                
            agent_setting = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == extension_name,
                    CompanyExtensionSetting.setting_key == agent_id_key,
                )
                .first()
            )
            agent_id = agent_setting.setting_value if agent_setting else None
            agent_name = None
            
            if agent_id:
                agent = db.query(Agent).filter(Agent.id == agent_id).first()
                agent_name = agent.name if agent else None
            
            # Get permission mode
            perm_mode_key = f"{platform}_bot_permission_mode"
            if platform == "discord":
                perm_mode_key = "discord_bot_permission_mode"
                
            perm_setting = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == extension_name,
                    CompanyExtensionSetting.setting_key == perm_mode_key,
                )
                .first()
            )
            permission_mode = perm_setting.setting_value if perm_setting else "recognized_users"
            
            # Get permission mode label and privacy using app-name substitution
            perm_modes = get_permission_modes_with_app_name()
            perm_mode_label = "Recognized Users"
            perm_privacy = "private"
            for mode in perm_modes:
                if mode["value"] == permission_mode:
                    perm_mode_label = mode["label"]
                    perm_privacy = mode.get("privacy", "private")
                    break
            
            # Check if bot is paused
            paused_key = f"{platform}_bot_paused"
            paused_setting = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == extension_name,
                    CompanyExtensionSetting.setting_key == paused_key,
                )
                .first()
            )
            is_paused = bool(paused_setting and paused_setting.setting_value and paused_setting.setting_value.lower() == "true")
            
            # Get runtime status
            runtime_status = _get_bot_status_for_platform(platform, company_id, company_name)
            is_running = runtime_status.is_running if runtime_status else False
            started_at = runtime_status.started_at if runtime_status else None
            messages_processed = runtime_status.messages_processed if runtime_status else 0
            error = runtime_status.error if runtime_status else None
            
            # Determine status
            if error:
                status = "error"
                status_message = error
                error_count += 1
            elif is_paused:
                status = "paused"
                status_message = "Bot is paused"
                paused_count += 1
            elif is_running:
                status = "running"
                status_message = "Bot is running"
                running_count += 1
            else:
                status = "offline"
                status_message = "Bot is not running"
            
            # Check OAuth connection for OAuth-based platforms
            uses_oauth = bool(config.get("oauth_provider"))
            oauth_connected = False
            oauth_provider = config.get("oauth_provider")
            
            if uses_oauth and agent_id:
                from MagicalAuth import get_agent_oauth_credentials
                agent_creds = get_agent_oauth_credentials(agent_id, oauth_provider)
                oauth_connected = agent_creds is not None
            
            # Get platform display name
            platform_name = _get_platform_display_name(platform)
            
            # Get timestamps from settings (use enabled setting as proxy for created_at)
            created_at = None
            updated_at = None
            if enabled_setting:
                if hasattr(enabled_setting, 'created_at') and enabled_setting.created_at:
                    created_at = enabled_setting.created_at.isoformat()
                if hasattr(enabled_setting, 'updated_at') and enabled_setting.updated_at:
                    updated_at = enabled_setting.updated_at.isoformat()
            
            deployed_bots.append(DeployedBotInfo(
                id=f"{company_id}_{platform}",
                platform=platform,
                platform_name=platform_name,
                company_id=company_id,
                company_name=company_name,
                agent_id=agent_id,
                agent_name=agent_name,
                enabled=is_enabled,
                is_running=is_running,
                is_paused=is_paused,
                is_server_level=False,  # Company-level bot
                permission_mode=permission_mode,
                permission_mode_label=perm_mode_label,
                permission_privacy=perm_privacy,
                status=status,
                status_message=status_message,
                started_at=started_at,
                messages_processed=messages_processed,
                uses_oauth=uses_oauth,
                oauth_connected=oauth_connected,
                oauth_provider=oauth_provider,
                created_at=created_at,
                updated_at=updated_at,
                error=error,
            ))
    
    return DeployedBotsResponse(
        bots=deployed_bots,
        total_count=len(deployed_bots),
        running_count=running_count,
        paused_count=paused_count,
        error_count=error_count,
    )


@app.get(
    "/v1/server/deployed-bots",
    tags=["Server Bots"],
    response_model=DeployedBotsResponse,
    summary="Get list of server-level deployed bots",
    description="Get a list of all server-level deployed bots. Super admin only.",
    dependencies=[Depends(verify_api_key)],
)
async def get_server_deployed_bots(
    authorization: str = Header(None),
):
    """Get all server-level deployed bots. Super admin only."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only super admins can view server-level bots.",
        )

    deployed_bots = []
    running_count = 0
    paused_count = 0
    error_count = 0
    
    from Globals import getenv
    app_name = getenv("APP_NAME") or "AGiXT"

    with get_session() as db:
        for platform, config in BOT_PLATFORM_SETTINGS.items():
            extension_name = config["extension_name"]
            
            # Check if server-level bot is enabled for this platform
            enabled_key = f"{platform}_bot_enabled"
            if platform == "discord":
                enabled_key = "DISCORD_BOT_ENABLED"
            
            # Check ServerExtensionSetting for server-level configuration
            enabled_setting = (
                db.query(ServerExtensionSetting)
                .filter(
                    ServerExtensionSetting.extension_name == extension_name,
                    ServerExtensionSetting.setting_key == enabled_key,
                )
                .first()
            )
            
            is_enabled = enabled_setting and enabled_setting.setting_value and enabled_setting.setting_value.lower() == "true"
            
            # Also check if token exists (for platforms that need it)
            token_key = config.get("required", [None])[0] if config.get("required") else None
            has_token = False
            uses_oauth = bool(config.get("oauth_provider"))
            
            if token_key:
                # Platform requires a token - check if it exists
                token_setting = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == extension_name,
                        ServerExtensionSetting.setting_key == token_key,
                    )
                    .first()
                )
                has_token = bool(token_setting and token_setting.setting_value)
            elif uses_oauth:
                # OAuth-based platform - only considered deployed if explicitly enabled
                # or has OAuth tokens configured at server level
                has_token = is_enabled
            else:
                # No required token and no OAuth - shouldn't happen, but default to enabled check
                has_token = is_enabled
            
            # Server bot is deployed if either enabled=true or has a token configured
            if not (is_enabled or has_token):
                continue
            
            # Get agent info (server-level)
            agent_id_key = f"{platform}_bot_agent_id"
            if platform == "discord":
                agent_id_key = "discord_bot_agent_id"
                
            agent_setting = (
                db.query(ServerExtensionSetting)
                .filter(
                    ServerExtensionSetting.extension_name == extension_name,
                    ServerExtensionSetting.setting_key == agent_id_key,
                )
                .first()
            )
            agent_id = agent_setting.setting_value if agent_setting else None
            agent_name = None
            
            if agent_id:
                agent = db.query(Agent).filter(Agent.id == agent_id).first()
                agent_name = agent.name if agent else None
            
            # Get permission mode
            perm_mode_key = f"{platform}_bot_permission_mode"
            if platform == "discord":
                perm_mode_key = "discord_bot_permission_mode"
                
            perm_setting = (
                db.query(ServerExtensionSetting)
                .filter(
                    ServerExtensionSetting.extension_name == extension_name,
                    ServerExtensionSetting.setting_key == perm_mode_key,
                )
                .first()
            )
            # Server-level bots default to app_users permission
            permission_mode = perm_setting.setting_value if perm_setting else "app_users"
            
            # Get permission mode label and privacy
            perm_modes = get_permission_modes_with_app_name()
            perm_mode_label = f"{app_name} Users"
            perm_privacy = "public"
            for mode in perm_modes:
                if mode["value"] == permission_mode:
                    perm_mode_label = mode["label"]
                    perm_privacy = mode.get("privacy", "public")
                    break
            
            # Check if bot is paused
            paused_key = f"{platform}_bot_paused"
            paused_setting = (
                db.query(ServerExtensionSetting)
                .filter(
                    ServerExtensionSetting.extension_name == extension_name,
                    ServerExtensionSetting.setting_key == paused_key,
                )
                .first()
            )
            is_paused = bool(paused_setting and paused_setting.setting_value and paused_setting.setting_value.lower() == "true")
            
            # Get runtime status - use "server" as company_id for server-level bots
            runtime_status = _get_bot_status_for_platform(platform, "server", f"{app_name} Server")
            is_running = runtime_status.is_running if runtime_status else False
            started_at = runtime_status.started_at if runtime_status else None
            messages_processed = runtime_status.messages_processed if runtime_status else 0
            error = runtime_status.error if runtime_status else None
            
            # Determine status
            if error:
                status = "error"
                status_message = error
                error_count += 1
            elif is_paused:
                status = "paused"
                status_message = "Bot is paused"
                paused_count += 1
            elif is_running:
                status = "running"
                status_message = "Bot is running"
                running_count += 1
            else:
                status = "offline"
                status_message = "Bot is not running"
            
            # Check OAuth connection
            uses_oauth = bool(config.get("oauth_provider"))
            oauth_connected = False
            oauth_provider = config.get("oauth_provider")
            
            # Get platform display name
            platform_name = _get_platform_display_name(platform)
            
            # Get timestamps
            created_at = None
            updated_at = None
            if enabled_setting:
                if hasattr(enabled_setting, 'created_at') and enabled_setting.created_at:
                    created_at = enabled_setting.created_at.isoformat()
                if hasattr(enabled_setting, 'updated_at') and enabled_setting.updated_at:
                    updated_at = enabled_setting.updated_at.isoformat()
            
            deployed_bots.append(DeployedBotInfo(
                id=f"server_{platform}",
                platform=platform,
                platform_name=platform_name,
                company_id="server",
                company_name=f"{app_name} Server",
                agent_id=agent_id,
                agent_name=agent_name,
                enabled=is_enabled or has_token,
                is_running=is_running,
                is_paused=is_paused,
                is_server_level=True,
                permission_mode=permission_mode,
                permission_mode_label=perm_mode_label,
                permission_privacy=perm_privacy,
                status=status,
                status_message=status_message,
                started_at=started_at,
                messages_processed=messages_processed,
                uses_oauth=uses_oauth,
                oauth_connected=oauth_connected,
                oauth_provider=oauth_provider,
                created_at=created_at,
                updated_at=updated_at,
                error=error,
            ))
    
    return DeployedBotsResponse(
        bots=deployed_bots,
        total_count=len(deployed_bots),
        running_count=running_count,
        paused_count=paused_count,
        error_count=error_count,
    )


@app.post(
    "/v1/company/{company_id}/bots/{platform}/pause",
    tags=["Company Bots"],
    summary="Pause or unpause a bot",
    description="Pause or unpause a deployed bot. Paused bots remain configured but don't process messages.",
    dependencies=[Depends(verify_api_key)],
)
async def pause_company_bot(
    company_id: str,
    platform: str,
    request: BotPauseRequest,
    authorization: str = Header(None),
):
    """Pause or unpause a bot."""
    if platform not in BOT_PLATFORM_SETTINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Valid platforms: {list(BOT_PLATFORM_SETTINGS.keys())}",
        )

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins can pause bots.",
        )

    platform_config = BOT_PLATFORM_SETTINGS[platform]
    extension_name = platform_config["extension_name"]
    paused_key = f"{platform}_bot_paused"

    with get_session() as db:
        # Get or create the paused setting
        existing = (
            db.query(CompanyExtensionSetting)
            .filter(
                CompanyExtensionSetting.company_id == company_id,
                CompanyExtensionSetting.extension_name == extension_name,
                CompanyExtensionSetting.setting_key == paused_key,
            )
            .first()
        )

        if existing:
            existing.setting_value = "true" if request.paused else "false"
        else:
            new_setting = CompanyExtensionSetting(
                company_id=company_id,
                extension_name=extension_name,
                setting_key=paused_key,
                setting_value="true" if request.paused else "false",
                is_sensitive=False,
            )
            db.add(new_setting)

        db.commit()

    action = "paused" if request.paused else "unpaused"
    platform_name = _get_platform_display_name(platform)

    return {
        "status": "success",
        "message": f"{platform_name} bot has been {action}",
        "paused": request.paused,
    }


@app.delete(
    "/v1/company/{company_id}/bots/{platform}",
    tags=["Company Bots"],
    summary="Remove/disconnect a deployed bot",
    description="Remove a deployed bot by disabling it and clearing its configuration.",
    dependencies=[Depends(verify_api_key)],
)
async def remove_company_bot(
    company_id: str,
    platform: str,
    authorization: str = Header(None),
):
    """Remove/disconnect a deployed bot."""
    if platform not in BOT_PLATFORM_SETTINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Valid platforms: {list(BOT_PLATFORM_SETTINGS.keys())}",
        )

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins can remove bots.",
        )

    platform_config = BOT_PLATFORM_SETTINGS[platform]
    extension_name = platform_config["extension_name"]
    
    # Disable the bot first (this will stop it if running)
    enabled_key = f"{platform}_bot_enabled"
    if platform == "discord":
        enabled_key = "DISCORD_BOT_ENABLED"

    with get_session() as db:
        # Set enabled to false
        enabled_setting = (
            db.query(CompanyExtensionSetting)
            .filter(
                CompanyExtensionSetting.company_id == company_id,
                CompanyExtensionSetting.extension_name == extension_name,
                CompanyExtensionSetting.setting_key == enabled_key,
            )
            .first()
        )
        
        if enabled_setting:
            enabled_setting.setting_value = "false"
            db.commit()
    
    # Stop the bot if it's running
    try:
        manager = _get_bot_manager(platform)
        if manager and hasattr(manager, 'stop_bot'):
            manager.stop_bot(company_id)
    except Exception as e:
        logging.warning(f"Error stopping {platform} bot during removal: {e}")

    platform_name = _get_platform_display_name(platform)

    return {
        "status": "success",
        "message": f"{platform_name} bot has been removed",
    }


# Server-level bot management endpoints (super admin only)

@app.post(
    "/v1/server/bots/{platform}/enable",
    tags=["Server Bots"],
    summary="Enable or disable a server-level bot",
    description="Enable or disable a server-level bot. Super admin only.",
    dependencies=[Depends(verify_api_key)],
)
async def enable_server_bot(
    platform: str,
    request: BotEnableRequest,
    authorization: str = Header(None),
):
    """Enable or disable a server-level bot. Super admin only."""
    if platform not in BOT_PLATFORM_SETTINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Valid platforms: {list(BOT_PLATFORM_SETTINGS.keys())}",
        )

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only super admins can manage server-level bots.",
        )

    platform_config = BOT_PLATFORM_SETTINGS[platform]
    extension_name = platform_config["extension_name"]
    
    enabled_key = f"{platform}_bot_enabled"
    if platform == "discord":
        enabled_key = "DISCORD_BOT_ENABLED"

    with get_session() as db:
        # Update or create the enabled setting
        enabled_setting = (
            db.query(ServerExtensionSetting)
            .filter(
                ServerExtensionSetting.extension_name == extension_name,
                ServerExtensionSetting.setting_key == enabled_key,
            )
            .first()
        )
        
        if enabled_setting:
            enabled_setting.setting_value = "true" if request.enabled else "false"
        else:
            enabled_setting = ServerExtensionSetting(
                extension_name=extension_name,
                setting_key=enabled_key,
                setting_value="true" if request.enabled else "false",
            )
            db.add(enabled_setting)
        
        # Update agent_id if provided
        if request.agent_id:
            agent_id_key = f"{platform}_bot_agent_id"
            if platform == "discord":
                agent_id_key = "discord_bot_agent_id"
            
            agent_setting = (
                db.query(ServerExtensionSetting)
                .filter(
                    ServerExtensionSetting.extension_name == extension_name,
                    ServerExtensionSetting.setting_key == agent_id_key,
                )
                .first()
            )
            
            if agent_setting:
                agent_setting.setting_value = request.agent_id
            else:
                agent_setting = ServerExtensionSetting(
                    extension_name=extension_name,
                    setting_key=agent_id_key,
                    setting_value=request.agent_id,
                )
                db.add(agent_setting)
        
        # Update permission_mode if provided
        if request.permission_mode:
            perm_mode_key = f"{platform}_bot_permission_mode"
            if platform == "discord":
                perm_mode_key = "discord_bot_permission_mode"
            
            perm_setting = (
                db.query(ServerExtensionSetting)
                .filter(
                    ServerExtensionSetting.extension_name == extension_name,
                    ServerExtensionSetting.setting_key == perm_mode_key,
                )
                .first()
            )
            
            if perm_setting:
                perm_setting.setting_value = request.permission_mode
            else:
                perm_setting = ServerExtensionSetting(
                    extension_name=extension_name,
                    setting_key=perm_mode_key,
                    setting_value=request.permission_mode,
                )
                db.add(perm_setting)
        
        # Update any additional settings
        if request.settings:
            for key, value in request.settings.items():
                setting = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == extension_name,
                        ServerExtensionSetting.setting_key == key,
                    )
                    .first()
                )
                
                is_sensitive = key.upper() in ["TOKEN", "SECRET", "KEY", "PASSWORD"] or "TOKEN" in key.upper() or "SECRET" in key.upper() or "KEY" in key.upper()
                
                if setting:
                    if is_sensitive and value:
                        setting.setting_value = encrypt_config_value(value)
                        setting.is_sensitive = True
                    else:
                        setting.setting_value = value
                else:
                    new_setting = ServerExtensionSetting(
                        extension_name=extension_name,
                        setting_key=key,
                        setting_value=encrypt_config_value(value) if is_sensitive and value else value,
                        is_sensitive=is_sensitive,
                    )
                    db.add(new_setting)
        
        db.commit()

    platform_name = _get_platform_display_name(platform)
    action = "enabled" if request.enabled else "disabled"

    return {
        "status": "success",
        "message": f"Server-level {platform_name} bot has been {action}",
    }


@app.post(
    "/v1/server/bots/{platform}/pause",
    tags=["Server Bots"],
    summary="Pause or unpause a server-level bot",
    description="Pause or unpause a server-level bot. Super admin only.",
    dependencies=[Depends(verify_api_key)],
)
async def pause_server_bot(
    platform: str,
    request: BotPauseRequest,
    authorization: str = Header(None),
):
    """Pause or unpause a server-level bot. Super admin only."""
    if platform not in BOT_PLATFORM_SETTINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Valid platforms: {list(BOT_PLATFORM_SETTINGS.keys())}",
        )

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only super admins can manage server-level bots.",
        )

    platform_config = BOT_PLATFORM_SETTINGS[platform]
    extension_name = platform_config["extension_name"]
    
    paused_key = f"{platform}_bot_paused"

    with get_session() as db:
        paused_setting = (
            db.query(ServerExtensionSetting)
            .filter(
                ServerExtensionSetting.extension_name == extension_name,
                ServerExtensionSetting.setting_key == paused_key,
            )
            .first()
        )
        
        if paused_setting:
            paused_setting.setting_value = "true" if request.paused else "false"
        else:
            paused_setting = ServerExtensionSetting(
                extension_name=extension_name,
                setting_key=paused_key,
                setting_value="true" if request.paused else "false",
            )
            db.add(paused_setting)
        
        db.commit()

    platform_name = _get_platform_display_name(platform)
    action = "paused" if request.paused else "resumed"

    return {
        "status": "success",
        "message": f"Server-level {platform_name} bot has been {action}",
        "paused": request.paused,
    }


@app.delete(
    "/v1/server/bots/{platform}",
    tags=["Server Bots"],
    summary="Remove a server-level bot",
    description="Remove/disconnect a server-level bot. Super admin only.",
    dependencies=[Depends(verify_api_key)],
)
async def remove_server_bot(
    platform: str,
    authorization: str = Header(None),
):
    """Remove a server-level bot. Super admin only."""
    if platform not in BOT_PLATFORM_SETTINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Valid platforms: {list(BOT_PLATFORM_SETTINGS.keys())}",
        )

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only super admins can manage server-level bots.",
        )

    platform_config = BOT_PLATFORM_SETTINGS[platform]
    extension_name = platform_config["extension_name"]
    
    enabled_key = f"{platform}_bot_enabled"
    if platform == "discord":
        enabled_key = "DISCORD_BOT_ENABLED"

    with get_session() as db:
        # Disable the bot
        enabled_setting = (
            db.query(ServerExtensionSetting)
            .filter(
                ServerExtensionSetting.extension_name == extension_name,
                ServerExtensionSetting.setting_key == enabled_key,
            )
            .first()
        )
        
        if enabled_setting:
            enabled_setting.setting_value = "false"
            db.commit()
    
    # Stop the bot if running
    try:
        manager = _get_bot_manager(platform)
        if manager and hasattr(manager, 'stop_bot'):
            manager.stop_bot("server")
    except Exception as e:
        logging.warning(f"Error stopping server-level {platform} bot during removal: {e}")

    platform_name = _get_platform_display_name(platform)

    return {
        "status": "success",
        "message": f"Server-level {platform_name} bot has been removed",
    }


@app.get(
    "/v1/company/{company_id}/bots/{platform}/status",
    tags=["Company Bots"],
    response_model=BotStatusResponse,
    summary="Get bot status for a specific platform",
    description="Get the status of a specific bot platform for a company.",
    dependencies=[Depends(verify_api_key)],
)
async def get_company_bot_status(
    company_id: str,
    platform: str,
    authorization: str = Header(None),
):
    """Get the status of a specific bot platform for a company."""
    if platform not in BOT_PLATFORM_SETTINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Valid platforms: {list(BOT_PLATFORM_SETTINGS.keys())}",
        )

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins or super admins can view bot status.",
        )

    # Get company name
    with get_session() as db:
        company = db.query(Company).filter(Company.id == company_id).first()
        company_name = company.name if company else "Unknown"

    status = _get_bot_status_for_platform(platform, company_id, company_name)
    if not status:
        return BotStatusResponse(
            company_id=company_id,
            company_name=company_name,
            platform=platform,
            is_running=False,
            error=f"{platform.title()} bot manager is not running or not available",
        )

    return status


@app.get(
    "/v1/company/{company_id}/bots/{platform}/settings",
    tags=["Company Bots"],
    summary="Get bot settings for a specific platform",
    description="Get the configured settings for a specific bot platform.",
    dependencies=[Depends(verify_api_key)],
)
async def get_company_bot_settings(
    company_id: str,
    platform: str,
    authorization: str = Header(None),
):
    """Get the settings for a specific bot platform."""
    if platform not in BOT_PLATFORM_SETTINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Valid platforms: {list(BOT_PLATFORM_SETTINGS.keys())}",
        )

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins can view bot settings.",
        )

    platform_config = BOT_PLATFORM_SETTINGS[platform]
    extension_name = platform_config["extension_name"]
    all_settings = platform_config["required"] + platform_config["optional"]

    settings = {}
    agent_id = None
    with get_session() as db:
        for setting_key in all_settings:
            setting = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == extension_name,
                    CompanyExtensionSetting.setting_key == setting_key,
                )
                .first()
            )

            if setting and setting.setting_value:
                # Mask sensitive values
                if setting.is_sensitive:
                    value = setting.setting_value
                    if len(value) > 8:
                        settings[setting_key] = (
                            f"{value[:4]}{'•' * (len(value) - 8)}{value[-4:]}"
                        )
                    else:
                        settings[setting_key] = "••••••••"
                else:
                    settings[setting_key] = setting.setting_value
                    
                # Track agent_id for OAuth lookup
                if setting_key.endswith('_agent_id'):
                    agent_id = setting.setting_value
            else:
                settings[setting_key] = None
                
        # Check for agent_id in standard location too
        if not agent_id:
            agent_setting = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == extension_name,
                    CompanyExtensionSetting.setting_key == f"{extension_name}_bot_agent_id",
                )
                .first()
            )
            if agent_setting:
                agent_id = agent_setting.setting_value

    # Build response with OAuth info if applicable
    response = {
        "platform": platform,
        "extension_name": extension_name,
        "settings": settings,
        "required_settings": platform_config["required"],
        "optional_settings": platform_config["optional"],
        # Allowlist metadata for the frontend
        "allowlist_type": platform_config.get("allowlist_type"),
        "allowlist_placeholder": platform_config.get("allowlist_placeholder"),
        "allowlist_help": platform_config.get("allowlist_help"),
    }
    
    # Add OAuth connection status for OAuth-based platforms
    oauth_provider = platform_config.get("oauth_provider")
    if oauth_provider:
        response["uses_oauth"] = True
        response["oauth_provider"] = oauth_provider
        response["oauth_provider_display"] = platform_config.get("oauth_provider_display", oauth_provider.title())
        
        # Check if agent has OAuth credentials
        if agent_id:
            from MagicalAuth import get_agent_oauth_credentials
            agent_creds = get_agent_oauth_credentials(agent_id, oauth_provider)
            if agent_creds:
                response["oauth_connected"] = True
                response["oauth_account_name"] = agent_creds.get("account_name", "Connected")
                response["oauth_is_agent_specific"] = agent_creds.get("is_agent_specific", False)
            else:
                response["oauth_connected"] = False
        else:
            response["oauth_connected"] = False
    else:
        response["uses_oauth"] = False
        
    return response


@app.post(
    "/v1/company/{company_id}/bots/{platform}/enable",
    tags=["Company Bots"],
    summary="Enable or disable a bot for a company",
    description="Enable or disable a specific bot platform for a company. When enabling, required settings must be provided (or OAuth must be connected for OAuth-based platforms).",
    dependencies=[Depends(verify_api_key)],
)
async def enable_company_bot(
    company_id: str,
    platform: str,
    request: BotEnableRequest,
    authorization: str = Header(None),
):
    """Enable or disable a bot platform for a company."""
    if platform not in BOT_PLATFORM_SETTINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Valid platforms: {list(BOT_PLATFORM_SETTINGS.keys())}",
        )

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins can manage bots.",
        )

    platform_config = BOT_PLATFORM_SETTINGS[platform]
    extension_name = platform_config["extension_name"]
    enabled_setting_key = f"{extension_name}_bot_enabled"
    if platform == "discord":
        enabled_setting_key = "DISCORD_BOT_ENABLED"

    with get_session() as db:
        # If enabling, check that required settings exist or OAuth is connected
        if request.enabled:
            oauth_provider = platform_config.get("oauth_provider")
            
            if oauth_provider and request.agent_id:
                # For OAuth-based platforms, check if agent has OAuth credentials
                from MagicalAuth import get_agent_oauth_credentials
                agent_creds = get_agent_oauth_credentials(request.agent_id, oauth_provider)
                
                if not agent_creds:
                    provider_display = platform_config.get("oauth_provider_display", oauth_provider.title())
                    raise HTTPException(
                        status_code=400,
                        detail=f"Please connect your {provider_display} account first. Go to Settings → Connections to link your account.",
                    )
            elif oauth_provider and not request.agent_id:
                # OAuth platform but no agent selected - need to select agent first
                raise HTTPException(
                    status_code=400,
                    detail="Please select an agent first. The bot will use the agent's connected OAuth credentials.",
                )
            else:
                # Non-OAuth platform - check required settings as before
                for required_key in platform_config["required"]:
                    # Check if provided in request
                    provided = (
                        request.settings
                        and required_key in request.settings
                        and request.settings[required_key]
                    )

                    # Check if exists in database
                    existing = (
                        db.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.company_id == company_id,
                            CompanyExtensionSetting.extension_name == extension_name,
                            CompanyExtensionSetting.setting_key == required_key,
                        )
                        .first()
                    )

                    if not provided and (not existing or not existing.setting_value):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Required setting '{required_key}' is missing. Required settings: {platform_config['required']}",
                        )

        # Save all provided settings
        if request.settings:
            for key, value in request.settings.items():
                if value is None:
                    continue

                existing = (
                    db.query(CompanyExtensionSetting)
                    .filter(
                        CompanyExtensionSetting.company_id == company_id,
                        CompanyExtensionSetting.extension_name == extension_name,
                        CompanyExtensionSetting.setting_key == key,
                    )
                    .first()
                )

                # Determine if sensitive
                is_sensitive = any(
                    x in key.lower()
                    for x in ["token", "secret", "password", "key", "access"]
                )

                # Encrypt if sensitive
                final_value = encrypt_config_value(value) if is_sensitive else value

                if existing:
                    existing.setting_value = final_value
                    existing.is_sensitive = is_sensitive
                else:
                    from DB import get_new_id

                    new_setting = CompanyExtensionSetting(
                        id=get_new_id(),
                        company_id=company_id,
                        extension_name=extension_name,
                        setting_key=key,
                        setting_value=final_value,
                        is_sensitive=is_sensitive,
                    )
                    db.add(new_setting)

        # Save agent_id if provided
        if request.agent_id:
            agent_id_key = f"{extension_name}_bot_agent_id"
            existing_agent = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == extension_name,
                    CompanyExtensionSetting.setting_key == agent_id_key,
                )
                .first()
            )
            if existing_agent:
                existing_agent.setting_value = request.agent_id
            else:
                from DB import get_new_id

                db.add(
                    CompanyExtensionSetting(
                        id=get_new_id(),
                        company_id=company_id,
                        extension_name=extension_name,
                        setting_key=agent_id_key,
                        setting_value=request.agent_id,
                        is_sensitive=False,
                    )
                )

        # Save permission_mode if provided
        if request.permission_mode:
            # Validate permission mode
            valid_modes = ["owner_only", "recognized_users", "allowlist", "app_users", "anyone"]
            if request.permission_mode not in valid_modes:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid permission_mode: {request.permission_mode}. Valid modes: {valid_modes}",
                )

            permission_key = f"{extension_name}_bot_permission_mode"
            existing_perm = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == extension_name,
                    CompanyExtensionSetting.setting_key == permission_key,
                )
                .first()
            )
            if existing_perm:
                existing_perm.setting_value = request.permission_mode
            else:
                from DB import get_new_id

                db.add(
                    CompanyExtensionSetting(
                        id=get_new_id(),
                        company_id=company_id,
                        extension_name=extension_name,
                        setting_key=permission_key,
                        setting_value=request.permission_mode,
                        is_sensitive=False,
                    )
                )

        # Save owner_id (the user who is enabling this bot)
        owner_id_key = f"{extension_name}_bot_owner_id"
        existing_owner = (
            db.query(CompanyExtensionSetting)
            .filter(
                CompanyExtensionSetting.company_id == company_id,
                CompanyExtensionSetting.extension_name == extension_name,
                CompanyExtensionSetting.setting_key == owner_id_key,
            )
            .first()
        )
        if not existing_owner:
            # Only set owner on first enable, don't overwrite
            from DB import get_new_id

            db.add(
                CompanyExtensionSetting(
                    id=get_new_id(),
                    company_id=company_id,
                    extension_name=extension_name,
                    setting_key=owner_id_key,
                    setting_value=str(auth.user_id),
                    is_sensitive=False,
                )
            )

        # Update enabled setting
        existing_enabled = (
            db.query(CompanyExtensionSetting)
            .filter(
                CompanyExtensionSetting.company_id == company_id,
                CompanyExtensionSetting.extension_name == extension_name,
                CompanyExtensionSetting.setting_key == enabled_setting_key,
            )
            .first()
        )

        enabled_value = "true" if request.enabled else "false"

        if existing_enabled:
            existing_enabled.setting_value = enabled_value
        else:
            from DB import get_new_id

            new_setting = CompanyExtensionSetting(
                id=get_new_id(),
                company_id=company_id,
                extension_name=extension_name,
                setting_key=enabled_setting_key,
                setting_value=enabled_value,
                is_sensitive=False,
            )
            db.add(new_setting)

        db.commit()

    # Trigger bot sync
    try:
        manager = _get_bot_manager(platform)
        if manager and hasattr(manager, "sync_bots"):
            import asyncio

            asyncio.create_task(manager.sync_bots())
    except Exception as e:
        logging.error(f"Error syncing {platform} bots: {e}")

    action = "enabled" if request.enabled else "disabled"
    return {
        "status": "success",
        "message": f"{platform.title()} bot {action} for company. Bot will start/stop within 60 seconds.",
    }


@app.post(
    "/v1/company/{company_id}/bots/{platform}/restart",
    tags=["Company Bots"],
    summary="Restart a bot for a company",
    description="Restart a specific bot platform for a company.",
    dependencies=[Depends(verify_api_key)],
)
async def restart_company_bot(
    company_id: str,
    platform: str,
    authorization: str = Header(None),
):
    """Restart a bot platform for a company."""
    if platform not in BOT_PLATFORM_SETTINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Valid platforms: {list(BOT_PLATFORM_SETTINGS.keys())}",
        )

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Check authorization
    user_role = auth.get_user_role(company_id)
    is_super_admin = auth.is_super_admin()

    if user_role > 2 and not is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only company admins can restart bots.",
        )

    manager = _get_bot_manager(platform)
    if not manager:
        raise HTTPException(
            status_code=503,
            detail=f"{platform.title()} bot manager is not running.",
        )

    # Stop and restart the bot
    try:
        if hasattr(manager, "stop_bot_for_company"):
            await manager.stop_bot_for_company(company_id)
        if hasattr(manager, "sync_bots"):
            await manager.sync_bots()
    except Exception as e:
        logging.error(f"Error restarting {platform} bot: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error restarting bot: {str(e)}",
        )

    return {
        "status": "success",
        "message": f"{platform.title()} bot restart initiated. Bot will be back online shortly.",
    }


@app.get(
    "/v1/admin/bots",
    tags=["Admin Bots"],
    summary="Get all running bots across all platforms (super admin only)",
    description="Get status of all running bots across all companies and platforms.",
    dependencies=[Depends(verify_api_key)],
)
async def get_all_bots_admin(
    authorization: str = Header(None),
):
    """Get status of all running bots across all platforms (super admin only)."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Super admin access required.",
        )

    all_bots = {}
    for platform in BOT_PLATFORM_SETTINGS.keys():
        try:
            manager = _get_bot_manager(platform)
            if not manager:
                all_bots[platform] = {"status": "not_running", "bots": []}
                continue

            # Get all statuses
            if hasattr(manager, "get_status"):
                statuses = manager.get_status()
                if isinstance(statuses, dict):
                    all_bots[platform] = {
                        "status": "running",
                        "bots": [
                            {
                                "company_id": (
                                    s.company_id if hasattr(s, "company_id") else k
                                ),
                                "company_name": (
                                    s.company_name
                                    if hasattr(s, "company_name")
                                    else "Unknown"
                                ),
                                "is_running": (
                                    s.is_running if hasattr(s, "is_running") else False
                                ),
                                "started_at": (
                                    s.started_at.isoformat()
                                    if hasattr(s, "started_at") and s.started_at
                                    else None
                                ),
                                "error": s.error if hasattr(s, "error") else None,
                            }
                            for k, s in statuses.items()
                        ],
                    }
                else:
                    all_bots[platform] = {"status": "running", "bots": []}
            elif hasattr(manager, "get_all_status"):
                statuses = manager.get_all_status()
                all_bots[platform] = {
                    "status": "running",
                    "bots": [
                        {
                            "company_id": (
                                s.company_id if hasattr(s, "company_id") else "unknown"
                            ),
                            "company_name": (
                                s.company_name
                                if hasattr(s, "company_name")
                                else "Unknown"
                            ),
                            "is_running": (
                                s.is_running if hasattr(s, "is_running") else False
                            ),
                            "started_at": (
                                s.started_at.isoformat()
                                if hasattr(s, "started_at") and s.started_at
                                else None
                            ),
                            "error": s.error if hasattr(s, "error") else None,
                        }
                        for s in statuses
                    ],
                }
            else:
                all_bots[platform] = {"status": "running", "bots": []}

        except Exception as e:
            logging.warning(f"Error getting {platform} bot statuses: {e}")
            all_bots[platform] = {"status": "error", "error": str(e), "bots": []}

    return {
        "status": "success",
        "platforms": all_bots,
    }


@app.get(
    "/v1/bots/platforms",
    tags=["Company Bots"],
    summary="Get available bot platforms and their configuration",
    description="Get list of available bot platforms with their required and optional settings.",
    dependencies=[Depends(verify_api_key)],
)
async def get_bot_platforms(
    authorization: str = Header(None),
):
    """Get available bot platforms and their configuration."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    platforms = []
    for platform, config in BOT_PLATFORM_SETTINGS.items():
        platform_info = {
            "id": platform,
            "name": _get_platform_display_name(platform),
            "extension_name": config["extension_name"],
            "required_settings": config["required"],
            "optional_settings": config["optional"],
            "description": config.get("description", _get_platform_description(platform)),
            "setup_url": _get_platform_setup_url(platform),
        }
        
        # Add OAuth info if this platform supports OAuth
        if config.get("oauth_provider"):
            platform_info["oauth_provider"] = config["oauth_provider"]
            platform_info["oauth_provider_display"] = config.get("oauth_provider_display", config["oauth_provider"].title())
            platform_info["uses_oauth"] = True
        else:
            platform_info["uses_oauth"] = False
            
        platforms.append(platform_info)

    return {
        "platforms": platforms,
        "permission_modes": get_permission_modes_with_app_name(),
    }


def _get_platform_description(platform: str) -> str:
    """Get description for a bot platform."""
    descriptions = {
        "discord": "Connect your AI agent to Discord servers for chat interactions.",
        "slack": "Integrate your AI agent with Slack workspaces.",
        "teams": "Deploy your AI agent to Microsoft Teams channels.",
        "x": "Connect your AI agent to X (Twitter) for DM and mention-based interactions.",
        "facebook": "Integrate your AI agent with Facebook Messenger for page conversations.",
        "telegram": "Deploy your AI agent as a Telegram bot.",
        "whatsapp": "Connect your AI agent to WhatsApp Business for messaging.",
        "microsoft_email": "Connect your AI agent to Microsoft Outlook/365 email for automated email responses.",
        "google_email": "Connect your AI agent to Gmail for automated email responses.",
        "sendgrid_email": "Connect your AI agent to SendGrid for inbound email processing and responses.",
        "twilio_sms": "Connect your AI agent to Twilio for SMS text message conversations.",
    }
    return descriptions.get(platform, "")


def _get_platform_setup_url(platform: str) -> str:
    """Get documentation/setup URL for a bot platform."""
    urls = {
        "discord": "https://discord.com/developers/applications",
        "slack": "https://api.slack.com/apps",
        "teams": "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
        "x": "https://developer.twitter.com/en/portal/dashboard",
        "facebook": "https://developers.facebook.com/apps/",
        "telegram": "https://core.telegram.org/bots#botfather",
        "whatsapp": "https://developers.facebook.com/docs/whatsapp/cloud-api",
        "microsoft_email": "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
        "google_email": "https://console.cloud.google.com/apis/credentials",
        "sendgrid_email": "https://app.sendgrid.com/settings/api_keys",
        "twilio_sms": "https://www.twilio.com/console",
    }
    return urls.get(platform, "")


def _get_platform_display_name(platform: str) -> str:
    """Get display name for a bot platform."""
    names = {
        "discord": "Discord",
        "slack": "Slack",
        "teams": "Microsoft Teams",
        "x": "X (Twitter)",
        "facebook": "Facebook Messenger",
        "telegram": "Telegram",
        "whatsapp": "WhatsApp",
        "microsoft_email": "Microsoft Outlook/365 Email",
        "google_email": "Gmail",
        "sendgrid_email": "SendGrid Email",
        "twilio_sms": "Twilio SMS",
        "github": "GitHub",
    }
    return names.get(platform, platform.title())


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
                logging.error(
                    f"Error updating {update.extension_name}:{update.command_name}: {str(e)}"
                )
                errors.append(
                    f"{update.extension_name}:{update.command_name}: update failed"
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
    bot_invite_url: Optional[str] = (
        None  # For providers with bot functionality (e.g., Discord)
    )


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
    hub_path = getenv("EXTENSIONS_HUB_PATH")
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

        # Get current values - check env vars first, then ServerExtensionSetting table
        def get_oauth_setting(provider_name: str, setting_key: str) -> Optional[str]:
            """Get OAuth setting from env var or database."""
            # First check environment variable
            env_value = os.getenv(setting_key)
            if env_value:
                return env_value
            # Then check ServerExtensionSetting table
            with get_session() as db:
                setting = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == provider_name,
                        ServerExtensionSetting.setting_key == setting_key,
                    )
                    .first()
                )
                if setting and setting.setting_value:
                    if setting.is_sensitive:
                        return decrypt_config_value(setting.setting_value)
                    return setting.setting_value
            return None

        client_id = get_oauth_setting(module_name, client_id_key)
        client_secret = get_oauth_setting(module_name, client_secret_key)

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

        # Add Discord-specific bot token setting and invite URL
        bot_invite_url = None
        if module_name.lower() == "discord":
            bot_token_key = "DISCORD_BOT_TOKEN"
            bot_token = get_oauth_setting(module_name, bot_token_key)
            settings.append(
                OAuthProviderSetting(
                    setting_key=bot_token_key,
                    setting_value=(
                        mask_sensitive_value(bot_token, True) if bot_token else None
                    ),
                    is_sensitive=True,
                    description="Discord Bot Token for server-level Discord bot integration",
                )
            )
            # Generate bot invite URL if client_id is configured
            # Permissions: VIEW_CHANNEL (1024) + SEND_MESSAGES (2048) + READ_MESSAGE_HISTORY (65536) + ADD_REACTIONS (64) = 68672
            # Plus EMBED_LINKS (16384), ATTACH_FILES (32768), USE_SLASH_COMMANDS (2147483648) = 2147601472
            if client_id:
                bot_permissions = 2147601472
                bot_invite_url = f"https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions={bot_permissions}&scope=bot%20applications.commands"

        providers.append(
            OAuthProviderItem(
                provider_name=module_name,
                friendly_name=module_name.replace("_", " ").title(),
                scopes=getattr(module, "SCOPES", []),
                authorize_url=getattr(module, "AUTHORIZE", None),
                pkce_required=getattr(module, "PKCE_REQUIRED", False),
                is_configured=bool(client_id and client_secret),
                settings=settings,
                bot_invite_url=bot_invite_url,
            )
        )

    # Sort by configured first, then by name
    providers.sort(key=lambda x: (not x.is_configured, x.friendly_name))

    return OAuthProvidersResponse(providers=providers)


@app.put(
    "/v1/server/oauth-providers",
    tags=["Server OAuth Providers"],
    summary="Update OAuth provider settings (super admin only)",
    description="Update OAuth provider CLIENT_ID, CLIENT_SECRET, and BOT_TOKEN values.",
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
                valid_suffixes = ("_CLIENT_ID", "_CLIENT_SECRET", "_BOT_TOKEN")
                if not any(
                    setting.setting_key.endswith(suffix) for suffix in valid_suffixes
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

    if errors:
        message = f"Partially updated {len(updated)} settings with {len(errors)} errors: {', '.join(errors)}"
        status = "partial"
    else:
        message = f"Successfully updated {len(updated)} OAuth settings"
        status = "success"

    return {
        "status": status,
        "message": message,
        "updated": updated,
        "errors": errors,
    }


# ========================================
# Company Storage Settings Endpoints
# ========================================


class CompanyStorageSettingResponse(BaseModel):
    """Response for company storage settings."""

    storage_backend: str = "server"  # 'server', 's3', 'azure', 'b2'
    storage_container: Optional[str] = None
    # AWS S3 / MinIO - masked
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
    s3_endpoint: Optional[str] = None
    s3_bucket: Optional[str] = None
    # Azure Blob - masked
    azure_storage_account_name: Optional[str] = None
    azure_storage_key: Optional[str] = None
    # Backblaze B2 - masked
    b2_key_id: Optional[str] = None
    b2_application_key: Optional[str] = None
    b2_region: Optional[str] = None
    # Server default info (for display)
    server_retention_days: int = 5
    app_name: str = "AGiXT"


class CompanyStorageSettingUpdate(BaseModel):
    """Request to update company storage settings."""

    storage_backend: str = Field(
        ..., description="Storage backend: 'server', 's3', 'azure', 'b2'"
    )
    storage_container: Optional[str] = None
    # AWS S3 / MinIO
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
    s3_endpoint: Optional[str] = None
    s3_bucket: Optional[str] = None
    # Azure Blob
    azure_storage_account_name: Optional[str] = None
    azure_storage_key: Optional[str] = None
    # Backblaze B2
    b2_key_id: Optional[str] = None
    b2_application_key: Optional[str] = None
    b2_region: Optional[str] = None


def verify_company_admin(authorization: str, company_id: str) -> MagicalAuth:
    """Verify that the user is an admin of the specified company."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Super admins can access any company
    if auth.is_super_admin():
        return auth

    # Check if user is admin of the company
    user_role = auth.get_user_role(company_id)
    if user_role not in ["admin", "Admin"]:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Company admin role required.",
        )
    return auth


def get_effective_company_for_storage(db, company_id: str) -> Optional[str]:
    """
    Get the company ID that provides storage settings.
    Checks up the parent chain until we find a company with custom storage settings.
    Returns None if server default should be used.
    """
    visited = set()
    current_company_id = company_id

    while current_company_id and current_company_id not in visited:
        visited.add(current_company_id)

        # Check if this company has storage settings
        storage_setting = (
            db.query(CompanyStorageSetting)
            .filter(CompanyStorageSetting.company_id == current_company_id)
            .first()
        )

        if storage_setting and storage_setting.storage_backend != "server":
            return current_company_id

        # Get parent company
        company = db.query(Company).filter(Company.id == current_company_id).first()
        if not company or not company.company_id:
            break
        current_company_id = str(company.company_id)

    return None  # Use server default


@app.get(
    "/v1/company/{company_id}/storage",
    tags=["Company Storage"],
    response_model=CompanyStorageSettingResponse,
    summary="Get company storage settings",
    description="Get the storage settings for a company. Company admins can view their own company's settings.",
    dependencies=[Depends(verify_api_key)],
)
async def get_company_storage_settings(
    company_id: str,
    authorization: str = Header(None),
):
    """
    Get storage settings for a company.
    Returns the current configuration or indicates if using server defaults.
    """
    verify_company_admin(authorization, company_id)

    app_name = getenv("APP_NAME", "AGiXT")
    retention_days = int(getenv("WORKSPACE_RETENTION_DAYS", "5"))

    with get_session() as db:
        setting = (
            db.query(CompanyStorageSetting)
            .filter(CompanyStorageSetting.company_id == company_id)
            .first()
        )

        if not setting:
            return CompanyStorageSettingResponse(
                storage_backend="server",
                server_retention_days=retention_days,
                app_name=app_name,
            )

        # Mask sensitive values
        def mask_value(val: Optional[str]) -> Optional[str]:
            if not val:
                return None
            decrypted = decrypt_config_value(val)
            if not decrypted:
                return None
            if len(decrypted) <= 8:
                return "••••••••"
            return f"{decrypted[:4]}{'•' * (len(decrypted) - 8)}{decrypted[-4:]}"

        return CompanyStorageSettingResponse(
            storage_backend=setting.storage_backend,
            storage_container=setting.storage_container,
            aws_access_key_id=mask_value(setting.aws_access_key_id),
            aws_secret_access_key=mask_value(setting.aws_secret_access_key),
            aws_region=setting.aws_region,
            s3_endpoint=setting.s3_endpoint,
            s3_bucket=setting.s3_bucket,
            azure_storage_account_name=setting.azure_storage_account_name,
            azure_storage_key=mask_value(setting.azure_storage_key),
            b2_key_id=mask_value(setting.b2_key_id),
            b2_application_key=mask_value(setting.b2_application_key),
            b2_region=setting.b2_region,
            server_retention_days=retention_days,
            app_name=app_name,
        )


@app.put(
    "/v1/company/{company_id}/storage",
    tags=["Company Storage"],
    summary="Update company storage settings",
    description="Update storage settings for a company. Company admins can configure their own storage.",
    dependencies=[Depends(verify_api_key)],
)
async def update_company_storage_settings(
    company_id: str,
    settings: CompanyStorageSettingUpdate,
    authorization: str = Header(None),
):
    """
    Update storage settings for a company.
    Setting storage_backend to 'server' removes custom settings and uses server defaults.
    """
    verify_company_admin(authorization, company_id)

    # Validate storage backend
    valid_backends = ["server", "s3", "azure", "b2"]
    if settings.storage_backend not in valid_backends:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid storage backend. Must be one of: {', '.join(valid_backends)}",
        )

    with get_session() as db:
        # Verify company exists
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        existing = (
            db.query(CompanyStorageSetting)
            .filter(CompanyStorageSetting.company_id == company_id)
            .first()
        )

        # If setting to server default, remove the custom setting
        if settings.storage_backend == "server":
            if existing:
                db.delete(existing)
                db.commit()
            return {
                "status": "success",
                "message": "Company will use server default storage",
            }

        # Validate required fields based on backend
        if settings.storage_backend == "s3":
            if not settings.aws_access_key_id or not settings.aws_secret_access_key:
                # Check if existing values should be preserved (masked values)
                if existing:
                    has_key = existing.aws_access_key_id and not (
                        settings.aws_access_key_id
                        and "•" not in settings.aws_access_key_id
                    )
                    has_secret = existing.aws_secret_access_key and not (
                        settings.aws_secret_access_key
                        and "•" not in settings.aws_secret_access_key
                    )
                    if not has_key or not has_secret:
                        raise HTTPException(
                            status_code=400,
                            detail="AWS Access Key ID and Secret Access Key are required for S3",
                        )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="AWS Access Key ID and Secret Access Key are required for S3",
                    )

        elif settings.storage_backend == "azure":
            if not settings.azure_storage_account_name:
                raise HTTPException(
                    status_code=400,
                    detail="Azure Storage Account Name is required for Azure Blob",
                )
            if not settings.azure_storage_key:
                if not existing or not existing.azure_storage_key:
                    raise HTTPException(
                        status_code=400,
                        detail="Azure Storage Key is required for Azure Blob",
                    )

        elif settings.storage_backend == "b2":
            if not settings.b2_key_id or not settings.b2_application_key:
                if (
                    not existing
                    or not existing.b2_key_id
                    or not existing.b2_application_key
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="B2 Key ID and Application Key are required for Backblaze B2",
                    )

        # Helper to encrypt sensitive values, preserving existing if masked
        def encrypt_or_preserve(
            new_val: Optional[str], existing_val: Optional[str]
        ) -> Optional[str]:
            if not new_val:
                return existing_val  # Preserve existing
            if "•" in new_val:
                return existing_val  # Value is masked, preserve existing
            return encrypt_config_value(new_val)

        if existing:
            existing.storage_backend = settings.storage_backend
            existing.storage_container = settings.storage_container
            # AWS S3
            existing.aws_access_key_id = encrypt_or_preserve(
                settings.aws_access_key_id, existing.aws_access_key_id
            )
            existing.aws_secret_access_key = encrypt_or_preserve(
                settings.aws_secret_access_key, existing.aws_secret_access_key
            )
            existing.aws_region = settings.aws_region or existing.aws_region
            existing.s3_endpoint = settings.s3_endpoint or existing.s3_endpoint
            existing.s3_bucket = settings.s3_bucket or existing.s3_bucket
            # Azure
            existing.azure_storage_account_name = (
                settings.azure_storage_account_name
                or existing.azure_storage_account_name
            )
            existing.azure_storage_key = encrypt_or_preserve(
                settings.azure_storage_key, existing.azure_storage_key
            )
            # B2
            existing.b2_key_id = encrypt_or_preserve(
                settings.b2_key_id, existing.b2_key_id
            )
            existing.b2_application_key = encrypt_or_preserve(
                settings.b2_application_key, existing.b2_application_key
            )
            existing.b2_region = settings.b2_region or existing.b2_region
        else:
            new_setting = CompanyStorageSetting(
                company_id=company_id,
                storage_backend=settings.storage_backend,
                storage_container=settings.storage_container,
                aws_access_key_id=(
                    encrypt_config_value(settings.aws_access_key_id)
                    if settings.aws_access_key_id
                    else None
                ),
                aws_secret_access_key=(
                    encrypt_config_value(settings.aws_secret_access_key)
                    if settings.aws_secret_access_key
                    else None
                ),
                aws_region=settings.aws_region,
                s3_endpoint=settings.s3_endpoint,
                s3_bucket=settings.s3_bucket,
                azure_storage_account_name=settings.azure_storage_account_name,
                azure_storage_key=(
                    encrypt_config_value(settings.azure_storage_key)
                    if settings.azure_storage_key
                    else None
                ),
                b2_key_id=(
                    encrypt_config_value(settings.b2_key_id)
                    if settings.b2_key_id
                    else None
                ),
                b2_application_key=(
                    encrypt_config_value(settings.b2_application_key)
                    if settings.b2_application_key
                    else None
                ),
                b2_region=settings.b2_region,
            )
            db.add(new_setting)

        db.commit()

    return {
        "status": "success",
        "message": f"Company storage configured to use {settings.storage_backend}",
    }


@app.delete(
    "/v1/company/{company_id}/storage",
    tags=["Company Storage"],
    summary="Delete company storage settings",
    description="Remove custom storage settings and revert to server defaults.",
    dependencies=[Depends(verify_api_key)],
)
async def delete_company_storage_settings(
    company_id: str,
    authorization: str = Header(None),
):
    """
    Delete custom storage settings for a company.
    The company will use server default storage after this.
    """
    verify_company_admin(authorization, company_id)

    with get_session() as db:
        existing = (
            db.query(CompanyStorageSetting)
            .filter(CompanyStorageSetting.company_id == company_id)
            .first()
        )

        if existing:
            db.delete(existing)
            db.commit()
            return {"status": "success", "message": "Custom storage settings removed"}

        return {"status": "success", "message": "No custom storage settings to remove"}


class TestEmailRequest(BaseModel):
    """Request to test email sending with a specific provider."""

    provider: str = Field(
        ..., description="Provider to test: sendgrid, mailgun, microsoft, google"
    )


class TestEmailResponse(BaseModel):
    """Response from email test."""

    success: bool
    provider: Optional[str] = None
    error: Optional[str] = None
    message: str


@app.post(
    "/v1/server/email/test",
    tags=["Server Config"],
    response_model=TestEmailResponse,
    summary="Test email configuration (super admin only)",
    description="Send a test email to the logged-in user to verify email provider configuration.",
    dependencies=[Depends(verify_api_key)],
)
async def test_email_provider(
    request: TestEmailRequest,
    authorization: str = Header(None),
):
    """
    Test email configuration by sending a test email to the logged-in user.

    The test will temporarily use the specified provider regardless of EMAIL_PROVIDER setting.
    """
    auth = verify_super_admin(authorization)
    user_email = auth.email
    app_name = getenv("APP_NAME") or "AGiXT"

    # Build test email content
    subject = f"[{app_name}] Email Provider Test"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #2563eb;">Email Test Successful! ✓</h2>
        <p>This is a test email from <strong>{app_name}</strong>.</p>
        <p><strong>Provider:</strong> {request.provider}</p>
        <p><strong>Recipient:</strong> {user_email}</p>
        <p style="color: #6b7280; font-size: 14px; margin-top: 20px;">
            If you received this email, your email provider is configured correctly.
        </p>
    </body>
    </html>
    """

    # Temporarily override the email provider for this test
    # We set it in the environment which takes priority in getenv()
    import os

    original_provider = os.environ.get("EMAIL_PROVIDER", "")
    os.environ["EMAIL_PROVIDER"] = request.provider

    try:
        # Send test email with detailed results
        result = send_email(
            email=user_email,
            subject=subject,
            body=body,
            return_details=True,
        )

        if result["success"]:
            return TestEmailResponse(
                success=True,
                provider=result["provider"],
                error=None,
                message=f"Test email sent successfully via {result['provider']} to {user_email}",
            )
        else:
            return TestEmailResponse(
                success=False,
                provider=request.provider,
                error=result["error"],
                message=f"Failed to send test email via {request.provider}",
            )
    finally:
        # Restore original provider setting
        if original_provider:
            os.environ["EMAIL_PROVIDER"] = original_provider
        elif "EMAIL_PROVIDER" in os.environ:
            del os.environ["EMAIL_PROVIDER"]


# ========================
# System Notification Endpoints
# ========================


class SystemNotificationCreate(BaseModel):
    """Request to create a new system-wide notification."""

    title: str = Field(..., description="Short title/summary of the notification")
    message: str = Field(..., description="Full notification message")
    expires_in_minutes: int = Field(
        default=60, description="Minutes until the notification expires (default 60)"
    )
    notification_type: str = Field(
        default="info",
        description="Type of notification: 'info', 'warning', 'critical'",
    )


class SystemNotificationResponse(BaseModel):
    """Response containing a system notification."""

    id: str
    title: str
    message: str
    created_by: str
    created_by_email: str
    created_at: str
    expires_at: str
    notified_count: int
    is_active: bool
    notification_type: str


class SystemNotificationListResponse(BaseModel):
    """Response containing a list of system notifications."""

    notifications: List[SystemNotificationResponse]
    total: int


class SystemNotificationDismissResponse(BaseModel):
    """Response after dismissing a notification."""

    success: bool
    message: str


@app.post(
    "/v1/notifications/system",
    tags=["System Notifications"],
    response_model=SystemNotificationResponse,
    summary="Create system-wide notification",
    description="Create a server-wide notification visible to all users. Super admin only.",
)
async def create_system_notification(
    request: SystemNotificationCreate,
    authorization: str = Header(None),
):
    """
    Create a system-wide notification that will be broadcast to all connected users.

    Only super admins (role_id=0) can create system notifications.

    The notification will:
    - Be immediately broadcast via WebSocket to all connected users
    - Appear in the mobile app as a push notification
    - Be logged with creator information for audit purposes
    - Automatically expire after the specified duration
    """
    from DB import SystemNotification, User, get_session
    from datetime import datetime, timedelta

    auth = verify_super_admin(authorization)

    # Calculate expiration time
    expires_at = datetime.now() + timedelta(minutes=request.expires_in_minutes)

    with get_session() as db:
        # Create the notification
        notification = SystemNotification(
            title=request.title,
            message=request.message,
            created_by=auth.user_id,
            expires_at=expires_at,
            notification_type=request.notification_type,
            is_active=True,
            notified_count=0,
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)

        # Get creator's email for the response
        creator = db.query(User).filter(User.id == auth.user_id).first()
        creator_email = creator.email if creator else "unknown"

        notification_id = str(notification.id)
        notification_data = {
            "id": notification_id,
            "title": notification.title,
            "message": notification.message,
            "notification_type": notification.notification_type,
            "expires_at": notification.expires_at.isoformat(),
            "created_at": notification.created_at.isoformat(),
        }

    # Broadcast to all connected users via WebSocket
    try:
        from endpoints.Conversation import broadcast_system_notification

        import asyncio

        asyncio.create_task(broadcast_system_notification(notification_data))
    except Exception as e:
        logging.warning(f"Failed to broadcast system notification: {e}")

    return SystemNotificationResponse(
        id=notification_id,
        title=request.title,
        message=request.message,
        created_by=str(auth.user_id),
        created_by_email=creator_email,
        created_at=notification_data["created_at"],
        expires_at=notification_data["expires_at"],
        notified_count=0,
        is_active=True,
        notification_type=request.notification_type,
    )


@app.get(
    "/v1/notifications/system",
    tags=["System Notifications"],
    response_model=SystemNotificationListResponse,
    summary="List system notifications",
    description="List all system notifications (super admin sees all, users see active only).",
)
async def list_system_notifications(
    include_expired: bool = False,
    authorization: str = Header(None),
):
    """
    List system notifications.

    For super admins: Returns all notifications (optionally including expired).
    For regular users: Returns only active, non-expired notifications.
    """
    from DB import SystemNotification, User, get_session
    from datetime import datetime

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    is_super = auth.is_super_admin()

    with get_session() as db:
        query = db.query(SystemNotification)

        if not is_super or not include_expired:
            # Only show active, non-expired notifications
            query = query.filter(
                SystemNotification.is_active == True,
                SystemNotification.expires_at > datetime.now(),
            )

        notifications = query.order_by(SystemNotification.created_at.desc()).all()

        result = []
        for n in notifications:
            creator = db.query(User).filter(User.id == n.created_by).first()
            creator_email = creator.email if creator else "unknown"

            result.append(
                SystemNotificationResponse(
                    id=str(n.id),
                    title=n.title,
                    message=n.message,
                    created_by=str(n.created_by),
                    created_by_email=creator_email,
                    created_at=n.created_at.isoformat(),
                    expires_at=n.expires_at.isoformat(),
                    notified_count=n.notified_count,
                    is_active=n.is_active,
                    notification_type=n.notification_type or "info",
                )
            )

        return SystemNotificationListResponse(notifications=result, total=len(result))


@app.post(
    "/v1/notifications/system/{notification_id}/dismiss",
    tags=["System Notifications"],
    response_model=SystemNotificationDismissResponse,
    summary="Dismiss a system notification",
    description="Mark a system notification as dismissed/received for the current user.",
)
async def dismiss_system_notification(
    notification_id: str,
    authorization: str = Header(None),
):
    """
    Mark a notification as received/dismissed for the current user.
    This prevents the notification from appearing again for this user.
    """
    from DB import SystemNotification, SystemNotificationReceipt, get_session
    from datetime import datetime

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    with get_session() as db:
        # Check if notification exists
        notification = (
            db.query(SystemNotification)
            .filter(SystemNotification.id == notification_id)
            .first()
        )

        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        # Check if already dismissed
        existing_receipt = (
            db.query(SystemNotificationReceipt)
            .filter(
                SystemNotificationReceipt.notification_id == notification_id,
                SystemNotificationReceipt.user_id == auth.user_id,
            )
            .first()
        )

        if existing_receipt:
            if existing_receipt.dismissed_at is None:
                existing_receipt.dismissed_at = datetime.now()
                db.commit()
                return SystemNotificationDismissResponse(
                    success=True, message="Notification dismissed"
                )
            return SystemNotificationDismissResponse(
                success=True, message="Notification already dismissed"
            )

        # Create new receipt with dismissed status
        receipt = SystemNotificationReceipt(
            notification_id=notification_id,
            user_id=auth.user_id,
            dismissed_at=datetime.now(),
        )
        db.add(receipt)
        db.commit()

        return SystemNotificationDismissResponse(
            success=True, message="Notification dismissed"
        )


@app.post(
    "/v1/notifications/system/{notification_id}/deactivate",
    tags=["System Notifications"],
    response_model=SystemNotificationResponse,
    summary="Deactivate a system notification",
    description="Deactivate a system notification (super admin only).",
)
async def deactivate_system_notification(
    notification_id: str,
    authorization: str = Header(None),
):
    """
    Deactivate a system notification so it no longer appears for users.
    Super admin only.
    """
    from DB import SystemNotification, User, get_session

    auth = verify_super_admin(authorization)

    with get_session() as db:
        notification = (
            db.query(SystemNotification)
            .filter(SystemNotification.id == notification_id)
            .first()
        )

        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        notification.is_active = False
        db.commit()
        db.refresh(notification)

        creator = db.query(User).filter(User.id == notification.created_by).first()
        creator_email = creator.email if creator else "unknown"

        return SystemNotificationResponse(
            id=str(notification.id),
            title=notification.title,
            message=notification.message,
            created_by=str(notification.created_by),
            created_by_email=creator_email,
            created_at=notification.created_at.isoformat(),
            expires_at=notification.expires_at.isoformat(),
            notified_count=notification.notified_count,
            is_active=notification.is_active,
            notification_type=notification.notification_type or "info",
        )


@app.get(
    "/v1/notifications/system/pending",
    tags=["System Notifications"],
    response_model=SystemNotificationListResponse,
    summary="Get pending system notifications for current user",
    description="Get system notifications the current user hasn't dismissed yet.",
)
async def get_pending_system_notifications(
    authorization: str = Header(None),
):
    """
    Get system notifications that the current user hasn't dismissed.
    Used by the frontend to show notification banners/toasts on load.
    """
    from DB import SystemNotification, SystemNotificationReceipt, User, get_session
    from datetime import datetime
    from sqlalchemy import and_

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    with get_session() as db:
        # Get all dismissed notification IDs for this user
        dismissed_ids = (
            db.query(SystemNotificationReceipt.notification_id)
            .filter(
                SystemNotificationReceipt.user_id == auth.user_id,
                SystemNotificationReceipt.dismissed_at.isnot(None),
            )
            .subquery()
        )

        # Get active, non-expired notifications not dismissed by this user
        notifications = (
            db.query(SystemNotification)
            .filter(
                SystemNotification.is_active == True,
                SystemNotification.expires_at > datetime.now(),
                ~SystemNotification.id.in_(dismissed_ids),
            )
            .order_by(SystemNotification.created_at.desc())
            .all()
        )

        result = []
        for n in notifications:
            creator = db.query(User).filter(User.id == n.created_by).first()
            creator_email = creator.email if creator else "unknown"

            # Record that this user received the notification
            existing_receipt = (
                db.query(SystemNotificationReceipt)
                .filter(
                    SystemNotificationReceipt.notification_id == n.id,
                    SystemNotificationReceipt.user_id == auth.user_id,
                )
                .first()
            )

            if not existing_receipt:
                receipt = SystemNotificationReceipt(
                    notification_id=n.id,
                    user_id=auth.user_id,
                )
                db.add(receipt)
                # Increment notified count
                n.notified_count = (n.notified_count or 0) + 1

            result.append(
                SystemNotificationResponse(
                    id=str(n.id),
                    title=n.title,
                    message=n.message,
                    created_by=str(n.created_by),
                    created_by_email=creator_email,
                    created_at=n.created_at.isoformat(),
                    expires_at=n.expires_at.isoformat(),
                    notified_count=n.notified_count or 0,
                    is_active=n.is_active,
                    notification_type=n.notification_type or "info",
                )
            )

        db.commit()

        return SystemNotificationListResponse(notifications=result, total=len(result))


# =====================
# GitHub Webhook Endpoint
# =====================


@app.post(
    "/v1/webhooks/github/{company_id}",
    tags=["Bot Webhooks"],
    summary="Receive GitHub webhook events",
    description="Endpoint for receiving webhook events from GitHub. Configure your GitHub webhook to point to this URL.",
)
async def github_webhook(
    company_id: str,
    request: Request,
):
    """
    Receive and process GitHub webhook events.

    This endpoint receives webhook events from GitHub (issues, pull_requests, etc.)
    and routes them to the appropriate GitHubBotManager for processing.

    The webhook signature is verified using the GITHUB_WEBHOOK_SECRET configured for
    the company's GitHub bot.

    Configure your GitHub webhook with:
    - Payload URL: https://your-server/v1/webhooks/github/{company_id}
    - Content type: application/json
    - Secret: Your configured GITHUB_WEBHOOK_SECRET
    - Events: Issues, Pull requests, Issue comments, Pull request reviews, Pull request review comments
    """
    import hmac
    import hashlib
    from DB import CompanyExtensionSetting, get_session, Company
    from Globals import getenv

    # Get the raw body for signature verification
    body = await request.body()
    payload = await request.json()

    # Get GitHub signature from headers
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    if not event_type:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    # Get the company and its GitHub bot settings
    with get_session() as db:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Check if GitHub bot is enabled
        bot_enabled_setting = (
            db.query(CompanyExtensionSetting)
            .filter(
                CompanyExtensionSetting.company_id == company_id,
                CompanyExtensionSetting.extension_name == "github",
                CompanyExtensionSetting.setting_key == "GITHUB_BOT_ENABLED",
            )
            .first()
        )

        if not bot_enabled_setting or bot_enabled_setting.setting_value.lower() != "true":
            raise HTTPException(
                status_code=400, detail="GitHub bot is not enabled for this company"
            )

        # Get webhook secret
        webhook_secret_setting = (
            db.query(CompanyExtensionSetting)
            .filter(
                CompanyExtensionSetting.company_id == company_id,
                CompanyExtensionSetting.extension_name == "github",
                CompanyExtensionSetting.setting_key == "GITHUB_WEBHOOK_SECRET",
            )
            .first()
        )

        webhook_secret = None
        if webhook_secret_setting and webhook_secret_setting.setting_value:
            webhook_secret = decrypt_config_value(webhook_secret_setting.setting_value)

    # Verify signature if webhook secret is configured
    if webhook_secret and signature_header:
        expected_signature = (
            "sha256="
            + hmac.new(
                webhook_secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
        )
        if not hmac.compare_digest(signature_header, expected_signature):
            logging.warning(
                f"GitHub webhook signature verification failed for company {company_id}"
            )
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    elif webhook_secret and not signature_header:
        logging.warning(
            f"GitHub webhook received without signature for company {company_id}"
        )
        raise HTTPException(
            status_code=401, detail="Webhook signature required but not provided"
        )

    # Log the event
    logging.info(
        f"GitHub webhook received: event={event_type}, delivery={delivery_id}, company={company_id}"
    )

    # Handle ping event (sent when webhook is first configured)
    if event_type == "ping":
        return {"status": "ok", "message": "Webhook configured successfully"}

    # Process the webhook event using GitHubBotManager
    try:
        from GitHubBotManager import GitHubBotManager

        manager = GitHubBotManager(company_id=company_id)
        result = await manager.handle_webhook(
            event_type=event_type, 
            payload=payload,
            company_id=company_id,
            skip_signature_check=True,  # Already verified above
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        logging.error(f"Error processing GitHub webhook: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error processing webhook: {str(e)}"
        )
