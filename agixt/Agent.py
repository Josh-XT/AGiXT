from DB import (
    Agent as AgentModel,
    AgentSetting as AgentSettingModel,
    AgentBrowsedLink,
    Command,
    AgentCommand,
    AgentProvider,
    AgentProviderSetting,
    ChainStep,
    ChainStepArgument,
    ChainStepResponse,
    Chain as ChainDB,
    Provider as ProviderModel,
    User,
    Extension,
    ExtensionCategory,
    UserPreferences,
    get_session,
    UserOAuth,
    OAuthProvider,
    TaskItem,
    WebhookIncoming,
    WebhookOutgoing,
    UserCompany,
)
from Extensions import Extensions
from SharedCache import (
    shared_cache,
    cache_agent_data,
    get_cached_agent_data,
    invalidate_agent_cache,
    cache_company_config,
    get_cached_company_config,
    invalidate_company_config_cache as shared_invalidate_company_config,
    cache_commands,
    get_cached_commands,
    invalidate_commands_cache as shared_invalidate_commands,
    cache_sso_providers,
    get_cached_sso_providers,
    invalidate_sso_providers_cache as shared_invalidate_sso_providers,
)
from Globals import getenv, get_tokens, DEFAULT_SETTINGS, DEFAULT_USER
from MagicalAuth import MagicalAuth, get_user_id
from Conversations import get_conversation_id_by_name
from middleware import log_silenced_exception
from typing import Any, Union
from fastapi import HTTPException
from datetime import datetime, timezone, timedelta
import logging
import json
import numpy as np
import base64
import jwt
import os
import re
import time
from solders.keypair import Keypair
from typing import Tuple
import binascii
from WebhookManager import WebhookEventEmitter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

# Initialize webhook event emitter
webhook_emitter = WebhookEventEmitter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


_command_owner_cache = None

# Cache for command_name -> friendly_name mapping
_command_name_to_friendly_cache = None

# Cache TTL constants
# NOTE: SharedCache handles cross-worker synchronization via Redis (if available)
# or falls back to local memory. TTLs are now safe to use.
_COMMANDS_CACHE_TTL = 300  # 5 minutes - commands rarely change
_COMPANY_CONFIG_CACHE_TTL = 60  # 1 minute - re-enabled with SharedCache
_AGENT_DATA_CACHE_TTL = 5  # 5 seconds - short TTL for request batching
_SSO_PROVIDERS_CACHE_TTL = 600  # 10 minutes - extensions rarely change


def get_sso_providers_cached():
    """
    Get list of SSO-enabled extensions with caching.
    Uses SharedCache for cross-worker consistency.
    Falls back to AST parsing if not in cache.
    """
    import ast

    # Try SharedCache first
    cached = get_cached_sso_providers()
    if cached is not None:
        return set(cached)

    sso_providers = set()
    extensions_dir = os.path.join(os.path.dirname(__file__), "extensions")

    try:
        extension_files = os.listdir(extensions_dir)
    except OSError:
        cache_sso_providers(list(sso_providers), ttl=_SSO_PROVIDERS_CACHE_TTL)
        return sso_providers

    for extension_file in extension_files:
        if extension_file.endswith(".py") and not extension_file.startswith("__"):
            try:
                extension_name = extension_file.replace(".py", "")
                file_path = os.path.join(extensions_dir, extension_file)

                # Use AST parsing instead of importing - much faster
                with open(file_path, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source, filename=file_path)

                # Look for SSO indicators in the AST
                has_sso_class = False
                has_sso_function = False
                has_oauth_scopes = False

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        if node.name == f"{extension_name.capitalize()}SSO":
                            has_sso_class = True
                    elif isinstance(node, ast.FunctionDef):
                        if node.name == "sso":
                            has_sso_function = True
                    elif isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == "SCOPES":
                                has_oauth_scopes = True

                if has_sso_class or has_sso_function or has_oauth_scopes:
                    sso_providers.add(extension_name)
            except Exception:
                continue

    # Cache in SharedCache
    cache_sso_providers(list(sso_providers), ttl=_SSO_PROVIDERS_CACHE_TTL)
    return sso_providers.copy()


def invalidate_sso_providers_cache():
    """Invalidate the SSO providers cache (uses SharedCache)"""
    shared_invalidate_sso_providers()


def get_company_agent_config_cached(company_id: str, company_agent):
    """Get company agent config with caching (uses SharedCache for cross-worker consistency)"""

    # Try SharedCache first
    cached = get_cached_company_config(str(company_id))
    if cached is not None:
        return cached

    # Get fresh config
    config = company_agent.get_agent_config()
    cache_company_config(str(company_id), config, ttl=_COMPANY_CONFIG_CACHE_TTL)
    return config


def invalidate_company_config_cache(company_id: str = None):
    """Invalidate company config cache (uses SharedCache)"""
    shared_invalidate_company_config(company_id)


def get_agent_data_cached(
    agent_id: str = None, agent_name: str = None, user_id: str = None
):
    """
    Get agent data (model, settings, commands) from cache if available and fresh.
    Uses SharedCache for cross-worker consistency.
    Returns dict or None if not cached.
    """
    if not agent_id or not user_id:
        return None

    return get_cached_agent_data(agent_id, user_id)


def set_agent_data_cache(agent_id: str, agent_name: str, user_id: str, data: dict):
    """
    Cache agent data (model info, settings, commands).
    Uses SharedCache for cross-worker consistency.
    """
    if not agent_id or not user_id:
        return

    cache_agent_data(agent_id, user_id, data, ttl=_AGENT_DATA_CACHE_TTL)


def invalidate_agent_data_cache(agent_id: str = None, user_id: str = None):
    """Invalidate agent data cache (uses SharedCache)"""
    invalidate_agent_cache(agent_id, user_id)


def get_all_commands_cached(session):
    """Get all commands with caching (uses SharedCache for cross-worker consistency)"""
    # Try SharedCache first - but we need to query DB if not cached
    # since commands are ORM objects
    # For now, use a local cache with short TTL since commands rarely change
    # and are used frequently within a single request
    global _all_commands_cache, _all_commands_cache_time

    if _all_commands_cache is not None:
        if (time.time() - _all_commands_cache_time) < _COMMANDS_CACHE_TTL:
            return _all_commands_cache

    _all_commands_cache = session.query(Command).all()
    _all_commands_cache_time = time.time()
    return _all_commands_cache


# Local cache for commands (ORM objects can't be serialized to Redis)
_all_commands_cache = None
_all_commands_cache_time = 0


def invalidate_commands_cache():
    """Invalidate the commands cache, forcing a refresh on next access"""
    global _all_commands_cache, _all_commands_cache_time
    _all_commands_cache = None
    _all_commands_cache_time = 0
    # Also invalidate SharedCache for any serializable command data
    shared_invalidate_commands()


def get_agents_lightweight(
    user_id: str,
    company_ids: list,
    default_agent_id: str = None,
    include_commands: bool = False,
) -> dict:
    """
    Get lightweight agent info for all user's companies in a single batch query.
    Returns {company_id: [agent_dicts]} where each agent has: id, name, companyId, default, status

    If include_commands=True, also includes 'commands' dict with {command_name: enabled_bool}
    for each agent. This is useful for the /v1/user endpoint to avoid separate API calls.

    This is optimized for the /v1/user endpoint to avoid the expensive get_agents() call.
    """
    session = get_session()
    try:
        # Get all agents owned by this user
        owned_agents = (
            session.query(AgentModel)
            .options(joinedload(AgentModel.settings))
            .filter(AgentModel.user_id == user_id)
            .all()
        )

        # Get all potential shared agents (not owned by this user) for companies
        shared_agents = []
        if company_ids:
            potential_shared = (
                session.query(AgentModel)
                .options(joinedload(AgentModel.settings))
                .filter(AgentModel.user_id != user_id)
                .all()
            )
            company_id_set = set(str(c) for c in company_ids)
            for agent in potential_shared:
                settings_dict = {s.name: s.value for s in agent.settings}
                is_shared = settings_dict.get("shared", "false") == "true"
                agent_company_id = settings_dict.get("company_id")
                if is_shared and agent_company_id in company_id_set:
                    shared_agents.append(agent)

        # Combine and organize by company
        all_agents = owned_agents + shared_agents
        result = {str(cid): [] for cid in company_ids}
        seen_by_company = {str(cid): set() for cid in company_ids}

        # If including commands, batch-fetch all command data
        commands_by_agent = {}
        if include_commands and all_agents:
            agent_ids = [str(a.id) for a in all_agents]

            # Get all commands (cached)
            all_commands = get_all_commands_cached(session)
            command_id_to_name = {c.id: c.name for c in all_commands}

            # Get enabled commands for all agents in one query
            agent_commands = (
                session.query(AgentCommand)
                .filter(AgentCommand.agent_id.in_(agent_ids))
                .filter(AgentCommand.state == True)
                .all()
            )

            # Build {agent_id: set of enabled command names}
            enabled_by_agent = {}
            for ac in agent_commands:
                agent_id_str = str(ac.agent_id)
                if agent_id_str not in enabled_by_agent:
                    enabled_by_agent[agent_id_str] = set()
                cmd_name = command_id_to_name.get(ac.command_id)
                if cmd_name:
                    enabled_by_agent[agent_id_str].add(cmd_name)

            # Build commands dict for each agent
            for agent in all_agents:
                agent_id_str = str(agent.id)
                enabled_commands = enabled_by_agent.get(agent_id_str, set())
                commands_by_agent[agent_id_str] = {
                    cmd_name: cmd_name in enabled_commands
                    for cmd_name in command_id_to_name.values()
                }

        for agent in all_agents:
            settings_dict = {s.name: s.value for s in agent.settings}
            agent_company_id = settings_dict.get("company_id")

            if not agent_company_id or agent_company_id not in result:
                continue

            if agent.name in seen_by_company[agent_company_id]:
                continue
            seen_by_company[agent_company_id].add(agent.name)

            status = settings_dict.get("status")
            if status is not None:
                try:
                    status = (
                        status.lower() == "true"
                        if isinstance(status, str)
                        else bool(status)
                    )
                except:
                    status = None

            agent_dict = {
                "id": str(agent.id),
                "name": agent.name,
                "companyId": agent_company_id,
                "default": (
                    str(agent.id) == str(default_agent_id)
                    if default_agent_id
                    else False
                ),
                "status": status,
            }

            # Add commands if requested
            if include_commands:
                agent_dict["commands"] = commands_by_agent.get(str(agent.id), {})

            result[agent_company_id].append(agent_dict)

        return result
    finally:
        session.close()


def get_agent_commands_only(agent_id: str, user_id: str) -> dict:
    """
    Get just the commands dict for an agent without loading full Agent config.

    This is a lightweight alternative to creating a full Agent object when
    you only need the commands dictionary.

    Args:
        agent_id: The agent's UUID
        user_id: The user's UUID (for authorization)

    Returns:
        Dict of {command_name: enabled_bool}
    """
    session = get_session()
    try:
        # Verify agent exists and user has access
        agent = session.query(AgentModel).filter(AgentModel.id == agent_id).first()
        if not agent:
            return {}

        # Get all commands using cache
        all_commands = get_all_commands_cached(session)

        # Get agent's enabled commands
        agent_commands = (
            session.query(AgentCommand).filter(AgentCommand.agent_id == agent_id).all()
        )

        # Build enabled command IDs set
        enabled_command_ids = {ac.command_id for ac in agent_commands if ac.state}

        # Build commands dict
        commands = {}
        for command in all_commands:
            commands[command.name] = command.id in enabled_command_ids

        return commands
    finally:
        session.close()


def _get_command_owner_cache():
    global _command_owner_cache
    if _command_owner_cache is not None:
        return _command_owner_cache

    cache = {}
    try:
        extensions = Extensions().get_extensions()
        for extension_data in extensions:
            extension_name = extension_data.get("extension_name")
            for command_data in extension_data.get("commands", []):
                friendly_name = command_data.get("friendly_name")
                if not friendly_name:
                    continue
                cache.setdefault(friendly_name.lower(), set()).add(extension_name)
    except Exception as e:
        logging.debug(f"Unable to build command owner cache: {e}")

    _command_owner_cache = cache
    return _command_owner_cache


def _get_command_name_to_friendly_cache():
    """
    Build a cache mapping command_name (function name) to friendly_name.
    This is used to resolve command lookups when the frontend sends
    the internal command_name instead of the friendly_name.
    """
    global _command_name_to_friendly_cache
    if _command_name_to_friendly_cache is not None:
        return _command_name_to_friendly_cache

    cache = {}
    try:
        extensions = Extensions().get_extensions()
        for extension_data in extensions:
            for command_data in extension_data.get("commands", []):
                command_name = command_data.get("command_name")
                friendly_name = command_data.get("friendly_name")
                if command_name and friendly_name and command_name != friendly_name:
                    # Map command_name -> friendly_name
                    cache[command_name] = friendly_name
    except Exception as e:
        logging.debug(f"Unable to build command name mapping cache: {e}")

    _command_name_to_friendly_cache = cache
    return _command_name_to_friendly_cache


def _resolve_command_by_name(session, command_name):
    if not command_name:
        return None

    # First, try to find by exact name match (friendly_name stored in DB)
    commands = (
        session.query(Command)
        .options(joinedload(Command.extension))
        .filter(Command.name == command_name)
        .all()
    )

    # If not found, try to map command_name (function name) to friendly_name
    if not commands:
        name_mapping = _get_command_name_to_friendly_cache()
        friendly_name = name_mapping.get(command_name)

        if friendly_name:
            # Now search by friendly_name
            commands = (
                session.query(Command)
                .options(joinedload(Command.extension))
                .filter(Command.name == friendly_name)
                .all()
            )

    if not commands:
        return None
    if len(commands) == 1:
        return commands[0]

    owners = _get_command_owner_cache().get(command_name.lower(), set())
    if owners:
        for command in commands:
            extension_name = command.extension.name if command.extension else None
            if extension_name in owners:
                return command

    logging.warning(
        "Multiple database entries found for command '%s'. Defaulting to first match.",
        command_name,
    )
    return commands[0]


# Define the standalone wallet creation function
def create_solana_wallet() -> Tuple[str, str, str]:
    """
    Creates a new Solana wallet keypair and generates a secure passphrase.

    Returns:
        Tuple[str, str, str]: A tuple containing the private key (hex string),
                              a generated passphrase (hex string), and the public key (string).
    """
    new_keypair = Keypair()
    private_key_hex = new_keypair.secret().hex()
    public_key_str = str(new_keypair.pubkey())
    # Generate a secure random passphrase (e.g., 16 bytes hex encoded)
    passphrase_hex = binascii.hexlify(os.urandom(16)).decode("utf-8")
    return private_key_hex, passphrase_hex, public_key_str


def impersonate_user(user_id: str):
    AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", "")
    # Get users email
    session = get_session()
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        session.close()
        raise HTTPException(status_code=404, detail="User not found.")
    user_id = str(user.id)
    email = user.email
    session.close()
    token = jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "exp": datetime.now() + timedelta(days=1),
        },
        AGIXT_API_KEY,
        algorithm="HS256",
    )
    return token


class AIProviderManager:
    """
    Manages AI Provider extensions for an agent.

    Discovers configured AI Provider extensions, handles provider selection based on
    token limits and service requirements, and implements fallback logic.

    Settings hierarchy (highest to lowest priority):
    1. Agent settings (user-level)
    2. Company settings (via company agent)
    3. Server config (database)
    4. Environment variables
    5. Default values
    """

    def __init__(
        self, agent_settings: dict, extensions_instance=None, company_id: str = None
    ):
        """
        Initialize the AI Provider Manager.

        Args:
            agent_settings: Dictionary of agent settings (includes extension settings)
            extensions_instance: Optional Extensions instance to discover providers from
            company_id: Optional company ID to resolve company-level settings
        """
        self.agent_settings = agent_settings
        self.extensions_instance = extensions_instance
        self.company_id = company_id
        self.providers = {}
        self.failed_providers = set()

        # Intelligence tier preference (smartest to least smart)
        smartest = agent_settings.get(
            "SMARTEST_PROVIDER",
            getenv("SMARTEST_PROVIDER", "anthropic,google,openai,ezlocalai"),
        )
        if "," in str(smartest):
            self.intelligence_tiers = [p.strip() for p in smartest.split(",")]
        else:
            self.intelligence_tiers = [smartest] if smartest else ["ezlocalai"]

        # Excluded providers that shouldn't be part of rotation
        self.excluded_providers = {"rotation", "gpt4free", "default"}
        rotation_exclusions = agent_settings.get(
            "ROTATION_EXCLUSIONS", getenv("ROTATION_EXCLUSIONS", "")
        )
        if rotation_exclusions:
            for exclusion in rotation_exclusions.split(","):
                self.excluded_providers.add(exclusion.strip().lower())

        # Discover and load AI Provider extensions
        self._discover_providers()

    def _get_merged_provider_settings(self):
        """
        Merge settings from all configuration levels for AI providers.

        Priority (highest to lowest):
        1. Agent settings (user-level, passed in agent_settings)
        2. Company extension settings (team/company-level from CompanyExtensionSetting table)
        3. Server extension settings (admin configured API keys in ServerExtensionSetting table)
        4. Environment variables (for local development/overrides)
        5. Default values from provider extensions

        This hierarchy ensures that:
        - Users can override with their own API keys if allowed
        - Teams/companies can configure shared provider settings
        - Server admins can set defaults for all users
        - Environment variables work for local development
        """
        from DB import (
            ServerExtensionSetting,
            CompanyExtensionSetting,
            get_session,
            decrypt_config_value,
        )

        # Map of setting keys to extension names for lookup
        # This maps the setting key pattern to the extension name used in ServerExtensionSetting
        provider_setting_keys = [
            # Anthropic
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AI_MODEL",
            "ANTHROPIC_MAX_TOKENS",
            "ANTHROPIC_TEMPERATURE",
            # Azure
            "AZURE_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_DEPLOYMENT_NAME",
            "AZURE_MAX_TOKENS",
            "AZURE_TEMPERATURE",
            "AZURE_TOP_P",
            # DeepSeek
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_MODEL",
            "DEEPSEEK_MAX_TOKENS",
            "DEEPSEEK_TEMPERATURE",
            "DEEPSEEK_TOP_P",
            # Google/Gemini
            "GOOGLE_API_KEY",
            "GOOGLE_AI_MODEL",
            "GOOGLE_MAX_TOKENS",
            "GOOGLE_TEMPERATURE",
            # OpenAI
            "OPENAI_API_KEY",
            "OPENAI_API_URI",
            "OPENAI_AI_MODEL",
            "OPENAI_MAX_TOKENS",
            "OPENAI_TEMPERATURE",
            "OPENAI_TOP_P",
            # xAI
            "XAI_API_KEY",
            "XAI_AI_MODEL",
            "XAI_MAX_TOKENS",
            "XAI_TEMPERATURE",
            "XAI_TOP_P",
            # ezLocalai
            "EZLOCALAI_API_KEY",
            "EZLOCALAI_API_URI",
            "EZLOCALAI_AI_MODEL",
            "EZLOCALAI_CODING_MODEL",
            "EZLOCALAI_MAX_TOKENS",
            "EZLOCALAI_TEMPERATURE",
            "EZLOCALAI_TOP_P",
            "EZLOCALAI_VOICE",
            "EZLOCALAI_LANGUAGE",
            "EZLOCALAI_TRANSCRIPTION_MODEL",
            # OpenRouter
            "OPENROUTER_API_KEY",
            "OPENROUTER_AI_MODEL",
            "OPENROUTER_MAX_TOKENS",
            "OPENROUTER_TEMPERATURE",
            "OPENROUTER_TOP_P",
            # DeepInfra
            "DEEPINFRA_API_KEY",
            "DEEPINFRA_MODEL",
            "DEEPINFRA_MAX_TOKENS",
            "DEEPINFRA_TEMPERATURE",
            "DEEPINFRA_TOP_P",
            # HuggingFace
            "HUGGINGFACE_API_KEY",
            "HUGGINGFACE_MODEL",
            "HUGGINGFACE_MAX_TOKENS",
            # Chutes
            "CHUTES_API_KEY",
            "CHUTES_MODEL",
            "CHUTES_MAX_TOKENS",
            "CHUTES_TEMPERATURE",
            "CHUTES_TOP_P",
            # ElevenLabs
            "ELEVENLABS_API_KEY",
            "ELEVENLABS_VOICE",
        ]

        merged_settings = {}

        # Priority order (lowest to highest, later values override earlier):
        # 4. Environment variables (lowest priority, for local dev)
        # 3. Server extension settings
        # 2. Company extension settings
        # 1. Agent settings (highest priority)

        # Step 1: Start with environment variables (lowest priority)
        for key in provider_setting_keys:
            env_value = os.getenv(key)
            if env_value:
                merged_settings[key] = env_value

        # Step 2: Apply server extension settings (overrides env vars)
        with get_session() as session:
            server_ext_settings = (
                session.query(ServerExtensionSetting)
                .filter(ServerExtensionSetting.setting_key.in_(provider_setting_keys))
                .all()
            )
            server_keys_found = []
            for setting in server_ext_settings:
                value = setting.setting_value
                if setting.is_sensitive and value:
                    value = decrypt_config_value(value)
                if value:  # Only add non-empty values
                    merged_settings[setting.setting_key] = value
                    server_keys_found.append(setting.setting_key)

            if server_keys_found:
                logging.debug(
                    f"[AIProviderManager] Found server-level settings: {server_keys_found}"
                )

            # Step 3: Apply company extension settings if company_id is available (overrides server)
            if self.company_id:
                company_ext_settings = (
                    session.query(CompanyExtensionSetting)
                    .filter(
                        CompanyExtensionSetting.company_id == self.company_id,
                        CompanyExtensionSetting.setting_key.in_(provider_setting_keys),
                    )
                    .all()
                )
                company_keys_found = []
                for setting in company_ext_settings:
                    value = setting.setting_value
                    if setting.is_sensitive and value:
                        value = decrypt_config_value(value)
                    if value:  # Only add non-empty values
                        merged_settings[setting.setting_key] = value
                        company_keys_found.append(setting.setting_key)

                if company_keys_found:
                    logging.debug(
                        f"[AIProviderManager] Found company-level settings for company {self.company_id}: {company_keys_found}"
                    )
            else:
                logging.debug(
                    "[AIProviderManager] No company_id provided, skipping company-level settings lookup"
                )

        # Step 4: Agent settings are applied later (highest priority) when providers are instantiated
        # by merging self.agent_settings into the final settings dict

        # Step 5: Apply agent-level provider settings (highest priority - user's own API keys)
        # This allows users to override with their own API keys if configured
        for key in provider_setting_keys:
            if key in self.agent_settings and self.agent_settings[key]:
                merged_settings[key] = self.agent_settings[key]

        # Add non-provider agent settings (like mode, persona, etc.)
        # These are settings that should be stored at agent level
        non_provider_keys = [
            "mode",
            "prompt_name",
            "prompt_category",
            "persona",
            "tts",
            "websearch",
            "websearch_depth",
            "analyze_user_input",
            "complexity_scaling_enabled",
            "thinking_budget_enabled",
            "thinking_budget_override",
            "answer_review_enabled",
            "planning_phase_enabled",
            "SMARTEST_PROVIDER",
        ]
        for key in non_provider_keys:
            if key in self.agent_settings and self.agent_settings[key]:
                merged_settings[key] = self.agent_settings[key]

        return merged_settings

    def _discover_providers(self):
        """Discover all configured AI Provider extensions by their CATEGORY attribute"""
        from ExtensionsHub import (
            find_extension_files,
            import_extension_module,
            get_extension_class_name,
        )

        # Get merged settings from all configuration levels
        merged_settings = self._get_merged_provider_settings()

        extension_files = find_extension_files()

        for ext_file in extension_files:
            filename = os.path.basename(ext_file)

            module = import_extension_module(ext_file)
            if module is None:
                continue

            class_name = get_extension_class_name(filename)
            if not hasattr(module, class_name):
                continue

            # Skip excluded providers
            provider_name = class_name.lower()
            if provider_name in self.excluded_providers:
                continue

            try:
                provider_class = getattr(module, class_name)

                # Check if it's an AI Provider (has CATEGORY = "AI Provider")
                if (
                    not hasattr(provider_class, "CATEGORY")
                    or provider_class.CATEGORY != "AI Provider"
                ):
                    continue

                # Instantiate with merged settings (respecting hierarchy)
                provider_instance = provider_class(**merged_settings)

                # Only add if configured
                if (
                    hasattr(provider_instance, "configured")
                    and provider_instance.configured
                ):
                    # Ensure max_tokens is always an integer for proper comparison
                    raw_max_tokens = (
                        provider_instance.get_max_tokens()
                        if hasattr(provider_instance, "get_max_tokens")
                        else 32000
                    )
                    self.providers[provider_name] = {
                        "instance": provider_instance,
                        "max_tokens": int(raw_max_tokens) if raw_max_tokens else 32000,
                        "services": (
                            provider_instance.services()
                            if hasattr(provider_instance, "services")
                            else ["llm"]
                        ),
                    }

            except Exception as e:
                logging.debug(
                    f"[AIProviderManager] Could not load provider from {filename}: {e}"
                )

        if not self.providers:
            logging.warning(
                "[AIProviderManager] No AI Provider extensions configured. Will fall back to legacy providers."
            )
        else:
            # Log summary of all discovered providers
            provider_summary = {
                name: f"{p['max_tokens']} tokens"
                for name, p in sorted(
                    self.providers.items(), key=lambda x: x[1]["max_tokens"]
                )
            }

    def get_provider_for_service(
        self, service: str = "llm", tokens: int = 0, use_smartest: bool = False
    ):
        """
        Select the best available provider for a service based on token limits.

        The selection strategy is:
        1. Filter out providers that don't support the requested service
        2. Filter out providers that can't handle the required token count
        3. If use_smartest=True, prefer providers in intelligence_tiers order
        4. Otherwise, select the provider with the lowest max_tokens that can handle the request
           (this ensures we use the cheapest/smallest provider for smaller requests)

        Args:
            service: The service type needed (llm, tts, image, transcription, etc.)
            tokens: Required token count (0 if unknown - all providers considered suitable)
            use_smartest: Whether to prefer the smartest provider

        Returns:
            Provider instance or None if no suitable provider found
        """
        # Build a dict of provider token limits for logging
        provider_token_limits = {
            name: provider["max_tokens"] for name, provider in self.providers.items()
        }

        # Filter providers that support the service and have sufficient token limits
        suitable = {}
        for name, provider in self.providers.items():
            if name in self.failed_providers:
                logging.debug(f"[AIProviderManager] Skipping failed provider: {name}")
                continue
            if service not in provider["services"]:
                continue
            if tokens > 0 and provider["max_tokens"] < tokens:
                continue
            suitable[name] = provider

        if not suitable:
            # Reset failed providers and try again
            if self.failed_providers:
                self.failed_providers.clear()
                return self.get_provider_for_service(service, tokens, use_smartest)
            return None

        suitable_with_tokens = {
            name: provider["max_tokens"] for name, provider in suitable.items()
        }

        # If use_smartest, try intelligence tiers in order
        if use_smartest:
            for tier in self.intelligence_tiers:
                if tier in suitable:
                    logging.debug(
                        f"[AIProviderManager] Selected smartest provider: {tier} (max_tokens: {suitable[tier]['max_tokens']}) for {tokens} tokens"
                    )
                    return suitable[tier]["instance"]

        # Otherwise, select provider with lowest max_tokens that can handle the request
        # (prefer to use smaller/cheaper providers for smaller requests)
        selected_name = min(suitable.keys(), key=lambda k: suitable[k]["max_tokens"])
        logging.debug(
            f"[AIProviderManager] Selected provider: {selected_name} (max_tokens: {suitable[selected_name]['max_tokens']}) for {tokens} tokens"
        )
        return suitable[selected_name]["instance"]

    def has_service(self, service: str) -> bool:
        """Check if any provider supports a given service without instantiating/selecting."""
        for name, provider in self.providers.items():
            if service in provider["services"]:
                return True
        return False

    def mark_provider_failed(self, provider_name: str):
        """Mark a provider as failed for this session"""
        self.failed_providers.add(provider_name)
        logging.warning(
            f"[AIProviderManager] Marked provider as failed: {provider_name}"
        )

    def has_providers(self) -> bool:
        """Check if any AI providers are available"""
        return len(self.providers) > 0

    def get_provider_names(self) -> list:
        """Get list of available provider names"""
        return list(self.providers.keys())


def can_user_access_agent(user_id, agent_id, auth: MagicalAuth = None):
    """
    Check if a user can access an agent.
    Returns: (can_access: bool, is_owner: bool, access_level: str)
    """
    session = get_session()

    # Get the agent
    agent = session.query(AgentModel).filter(AgentModel.id == agent_id).first()
    if not agent:
        session.close()
        return (False, False, None)

    # User is owner
    if str(agent.user_id) == str(user_id):
        session.close()
        return (True, True, "owner")

    # Check if shared and user is in same company
    agent_settings = (
        session.query(AgentSettingModel)
        .filter(AgentSettingModel.agent_id == agent_id)
        .all()
    )

    settings_dict = {s.name: s.value for s in agent_settings}
    is_shared = settings_dict.get("shared", "false") == "true"
    agent_company_id = settings_dict.get("company_id")

    if not is_shared or not agent_company_id:
        session.close()
        return (False, False, None)

    # Use MagicalAuth helper to get user's companies
    if not auth:
        token = impersonate_user(user_id=str(user_id))
        auth = MagicalAuth(token=token)

    user_company_ids = auth.get_user_companies()

    # Check if agent's company is in user's companies
    has_access = agent_company_id in user_company_ids
    session.close()

    return (has_access, False, "viewer" if has_access else None)


def add_agent(agent_name, provider_settings=None, commands=None, user=DEFAULT_USER):
    if not agent_name:
        return {"message": "Agent name cannot be empty."}
    session = get_session()
    # Check if agent already exists
    agent = (
        session.query(AgentModel)
        .filter(AgentModel.name == agent_name, AgentModel.user.has(email=user))
        .first()
    )
    if agent:
        # Agent already exists, return its info instead of creating a duplicate
        agent_id = str(agent.id)
        session.close()
        return {"message": f"Agent {agent_name} already exists.", "id": agent_id}
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id

    if provider_settings is None or provider_settings == "" or provider_settings == {}:
        provider_settings = DEFAULT_SETTINGS
    if "company_id" not in provider_settings:
        token = impersonate_user(user_id=str(user_id))
        auth = MagicalAuth(token=token)
        provider_settings["company_id"] = (
            str(auth.company_id) if auth.company_id is not None else None
        )
    # Iterate over DEFAULT_SETTINGS and add any missing keys
    for key in DEFAULT_SETTINGS:
        if key not in provider_settings:
            provider_settings[key] = DEFAULT_SETTINGS[key]
    if commands is None or commands == "" or commands == {}:
        commands = {}
    # Get provider ID based on provider name from provider_settings["provider"]
    if "provider" not in provider_settings:
        provider_settings["provider"] = "rotation"
    provider = (
        session.query(ProviderModel)
        .filter_by(name=provider_settings["provider"])
        .first()
    )
    # If provider not found, create it (for built-in providers like "rotation")
    if provider is None:
        provider = ProviderModel(name=provider_settings["provider"])
        session.add(provider)
        session.commit()
    agent = AgentModel(name=agent_name, user_id=user_id, provider_id=provider.id)
    session.add(agent)
    session.commit()

    # Emit webhook event for agent creation (async without await since this is sync function)
    import asyncio

    # Use the company_id already set in provider_settings
    company_id = provider_settings.get("company_id")
    if company_id and str(company_id).lower() in ["none", "null", ""]:
        company_id = None

    try:
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="agent.created",
                data={
                    "agent_id": str(agent.id),
                    "agent_name": agent_name,
                    "user_id": str(user_id),
                    "provider": provider_settings.get("provider", "rotation"),
                    "timestamp": datetime.now().isoformat(),
                },
                user_id=str(user_id),
                company_id=str(company_id) if company_id else None,
            )
        )
    except Exception as e:
        # If we're not in an async context, just log it
        log_silenced_exception(e, "add_agent: emitting webhook event")

    for key, value in provider_settings.items():
        agent_setting = AgentSettingModel(
            agent_id=agent.id,
            name=key,
            value=value,
        )
        session.add(agent_setting)

    # Auto-enable commands from Core Abilities category
    core_abilities_category = (
        session.query(ExtensionCategory)
        .filter(ExtensionCategory.name == "Core Abilities")
        .first()
    )

    if core_abilities_category:
        core_extensions = (
            session.query(Extension)
            .filter(Extension.category_id == core_abilities_category.id)
            .all()
        )

        for extension in core_extensions:
            # Get all commands from this extension
            extension_commands = (
                session.query(Command)
                .filter(Command.extension_id == extension.id)
                .all()
            )
            # Enable all commands from these extensions
            for command in extension_commands:
                # Check if agent command already exists (from commands parameter)
                existing_agent_command = (
                    session.query(AgentCommand)
                    .filter(
                        AgentCommand.agent_id == agent.id,
                        AgentCommand.command_id == command.id,
                    )
                    .first()
                )
                if not existing_agent_command:
                    agent_command = AgentCommand(
                        agent_id=agent.id, command_id=command.id, state=True
                    )
                    session.add(agent_command)

    # Handle any additional commands passed in the commands parameter
    if commands:
        for command_name, enabled in commands.items():
            command = _resolve_command_by_name(session, command_name)
            if command:
                # Check if agent command already exists (from auto-enabled extensions)
                existing_agent_command = (
                    session.query(AgentCommand)
                    .filter(
                        AgentCommand.agent_id == agent.id,
                        AgentCommand.command_id == command.id,
                    )
                    .first()
                )
                if existing_agent_command:
                    # Update existing command state
                    existing_agent_command.state = enabled
                else:
                    # Create new agent command
                    agent_command = AgentCommand(
                        agent_id=agent.id, command_id=command.id, state=enabled
                    )
                    session.add(agent_command)

    session.commit()
    agent_id = str(agent.id)
    session.close()
    return {"message": f"Agent {agent_name} created.", "id": agent_id}


def delete_agent(agent_name=None, agent_id=None, user=DEFAULT_USER):
    """Delete an agent and all dependent data.

    Supports targeting by either agent name or agent ID to avoid ambiguity.
    Returns a tuple of ({"message": str}, http_status_code).
    """

    if agent_name is None and agent_id is None:
        return {"message": "agent_name or agent_id is required."}, 400

    session = get_session()
    deleted = False
    agent_name_value = agent_name
    agent_id_value = agent_id
    user_id = None

    try:
        user_data = session.query(User).filter(User.email == user).first()
        if not user_data:
            logging.warning(f"User {user} not found while deleting agent.")
            return {"message": f"User {user} not found."}, 404

        user_id = user_data.id

        agent_query = session.query(AgentModel).filter(AgentModel.user_id == user_id)
        if agent_id is not None:
            agent = agent_query.filter(AgentModel.id == agent_id).first()
        else:
            agent = agent_query.filter(AgentModel.name == agent_name).first()

        if not agent:
            return {
                "message": (
                    f"Agent {agent_name or agent_id} not found for user {user}."
                )
            }, 404

        agent_name_value = agent.name
        agent_id_value = str(agent.id)

        total_agents = agent_query.count()
        if total_agents <= 1:
            return {"message": "You cannot delete your last agent."}, 401

        # Delete associated browsed links
        session.query(AgentBrowsedLink).filter_by(agent_id=agent.id).delete(
            synchronize_session=False
        )

        # Delete associated chain steps, arguments, and responses
        chain_steps = session.query(ChainStep).filter_by(agent_id=agent.id).all()
        for chain_step in chain_steps:
            session.query(ChainStepArgument).filter_by(
                chain_step_id=chain_step.id
            ).delete(synchronize_session=False)
            session.query(ChainStepResponse).filter_by(
                chain_step_id=chain_step.id
            ).delete(synchronize_session=False)
            session.delete(chain_step)

        # Delete associated agent commands
        agent_commands = session.query(AgentCommand).filter_by(agent_id=agent.id).all()
        for agent_command in agent_commands:
            session.delete(agent_command)

        # Delete associated agent provider records and settings
        agent_providers = (
            session.query(AgentProvider).filter_by(agent_id=agent.id).all()
        )
        for agent_provider in agent_providers:
            session.query(AgentProviderSetting).filter_by(
                agent_provider_id=agent_provider.id
            ).delete(synchronize_session=False)
            session.delete(agent_provider)

        # Delete associated agent settings
        session.query(AgentSettingModel).filter_by(agent_id=agent.id).delete(
            synchronize_session=False
        )

        # Null out optional relationships referencing the agent
        session.query(TaskItem).filter(TaskItem.agent_id == agent.id).update(
            {TaskItem.agent_id: None}, synchronize_session=False
        )
        session.query(WebhookOutgoing).filter(
            WebhookOutgoing.agent_id == agent.id
        ).update({WebhookOutgoing.agent_id: None}, synchronize_session=False)

        # Delete dependent records that require the agent
        session.query(WebhookIncoming).filter_by(agent_id=agent.id).delete(
            synchronize_session=False
        )

        # Finally delete the agent
        session.delete(agent)
        session.commit()
        deleted = True
    except IntegrityError as e:
        session.rollback()
        logging.error(
            f"Integrity error deleting agent {agent_name or agent_id}: {str(e)}"
        )
        return {
            "message": "Failed to delete agent due to related records.",
            "details": str(e),
        }, 500
    finally:
        session.close()

    if not deleted:
        return {"message": "Agent deletion was not completed."}, 500

    # Invalidate agent data cache
    invalidate_agent_data_cache(agent_id=agent_id_value)

    # Emit webhook event for agent deletion
    import asyncio

    try:
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="agent.deleted",
                data={
                    "agent_id": agent_id_value,
                    "agent_name": agent_name_value,
                    "user_id": str(user_id) if user_id else None,
                    "timestamp": datetime.now().isoformat(),
                },
                user_id=str(user_id) if user_id else None,
            )
        )
    except Exception:
        logging.debug(
            f"Could not emit webhook event for agent deletion: {agent_name_value}"
        )

    return {"message": f"Agent {agent_name_value} deleted."}, 200


def rename_agent(agent_name, new_name, user=DEFAULT_USER, company_id=None):
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id
    if not company_id:
        agent = (
            session.query(AgentModel)
            .filter(AgentModel.name == agent_name, AgentModel.user_id == user_id)
            .first()
        )
    else:
        agent = (
            session.query(AgentModel)
            .filter(AgentModel.name == agent_name, AgentModel.user_id == user_id)
            .filter(AgentModel.company_id == company_id)
            .first()
        )
    if not agent:
        session.close()
        return {"message": f"Agent {agent_name} not found."}, 404
    old_name = agent.name
    agent.name = new_name
    session.commit()

    # Invalidate agent data cache
    invalidate_agent_data_cache(agent_id=str(agent.id))

    # Emit webhook event for agent rename
    import asyncio

    try:
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="agent.updated",
                data={
                    "agent_id": str(agent.id),
                    "old_name": old_name,
                    "new_name": new_name,
                    "user_id": str(user_id),
                    "update_type": "rename",
                    "timestamp": datetime.now().isoformat(),
                },
                user_id=str(user_id),
            )
        )
    except:
        logging.debug(
            f"Could not emit webhook event for agent rename: {old_name} -> {new_name}"
        )

    session.close()
    return {"message": f"Agent {agent_name} renamed to {new_name}."}, 200


def get_agent_name_by_id(agent_id: str, user: str = DEFAULT_USER) -> str:
    """
    Standalone function to look up an agent name by ID.
    Checks user's agents first, then falls back to global agents.

    Args:
        agent_id: The UUID of the agent
        user: The user email to check for agent ownership

    Returns:
        The agent name if found

    Raises:
        ValueError if agent is not found
    """
    session = get_session()
    try:
        user_data = session.query(User).filter(User.email == user).first()
        if not user_data:
            raise ValueError(f"User {user} not found")

        # First check user's own agents
        agent = (
            session.query(AgentModel)
            .filter(AgentModel.id == agent_id, AgentModel.user_id == user_data.id)
            .first()
        )
        if not agent:
            # Try to find in global agents (DEFAULT_USER)
            global_user = session.query(User).filter(User.email == DEFAULT_USER).first()
            if global_user:
                agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.id == agent_id,
                        AgentModel.user_id == global_user.id,
                    )
                    .first()
                )
        if not agent:
            raise ValueError(f"Agent with ID {agent_id} not found for user {user}")
        return agent.name
    finally:
        session.close()


def get_agent_id_by_name(agent_name: str, user: str = DEFAULT_USER) -> str:
    """
    Standalone function to look up an agent ID by name.
    Checks user's agents first, then falls back to global agents.

    Args:
        agent_name: The name of the agent
        user: The user email to check for agent ownership

    Returns:
        The agent ID if found

    Raises:
        ValueError if agent is not found
    """
    session = get_session()
    try:
        user_data = session.query(User).filter(User.email == user).first()
        if not user_data:
            raise ValueError(f"User {user} not found")

        # First check user's own agents
        agent = (
            session.query(AgentModel)
            .filter(AgentModel.name == agent_name, AgentModel.user_id == user_data.id)
            .first()
        )
        if not agent:
            # Try to find in global agents (DEFAULT_USER)
            global_user = session.query(User).filter(User.email == DEFAULT_USER).first()
            if global_user:
                agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.name == agent_name,
                        AgentModel.user_id == global_user.id,
                    )
                    .first()
                )
        if not agent:
            raise ValueError(f"Agent with name {agent_name} not found for user {user}")
        return str(agent.id)
    finally:
        session.close()


def get_agents(user=DEFAULT_USER, company=None):
    """
    Get all agents accessible to a user (owned + shared via company).
    Optimized to reduce database queries using batch loading.
    """
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    if not user_data:
        session.close()
        return []

    try:
        default_agent_id = str(
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == user_data.id)
            .filter(UserPreferences.pref_key == "agent_id")
            .first()
            .pref_value
        )
    except:
        default_agent_id = ""

    # Get user's companies using MagicalAuth
    token = impersonate_user(user_id=str(user_data.id))
    auth = MagicalAuth(token=token)
    user_company_ids = auth.get_user_companies()

    # Query owned agents with eager loading
    owned_agents = (
        session.query(AgentModel)
        .options(joinedload(AgentModel.settings))
        .filter(AgentModel.user_id == user_data.id)
        .all()
    )

    # Query shared agents if user has companies
    shared_agents = []
    if user_company_ids:
        # Get all agents that are not owned by this user, with settings pre-loaded
        potential_shared = (
            session.query(AgentModel)
            .options(joinedload(AgentModel.settings))
            .filter(AgentModel.user_id != user_data.id)
            .all()
        )

        for agent in potential_shared:
            # Use pre-loaded settings instead of separate query
            settings_dict = {s.name: s.value for s in agent.settings}

            is_shared = settings_dict.get("shared", "false") == "true"
            agent_company_id = settings_dict.get("company_id")

            if is_shared and agent_company_id in user_company_ids:
                shared_agents.append(agent)

    # Combine owned and shared agents
    all_agents = owned_agents + shared_agents

    if default_agent_id == "" and all_agents:
        # Add a user preference of the first agent's ID in the agent list
        user_preference = UserPreferences(
            user_id=user_data.id, pref_key="agent_id", pref_value=all_agents[0].id
        )
        session.add(user_preference)
        session.commit()
        default_agent_id = str(all_agents[0].id)
    elif not all_agents:
        session.close()
        return []

    # Collect agents needing onboarding for batch processing
    agents_needing_onboard = []
    agents_needing_company = []

    output = []
    seen_names = set()

    for agent in all_agents:
        # Check if the agent is in the output already
        if agent.name in seen_names:
            continue
        seen_names.add(agent.name)

        # Use pre-loaded settings instead of separate query
        settings_dict = {s.name: s.value for s in agent.settings}
        company_id = settings_dict.get("company_id")
        agentonboarded11182025 = settings_dict.get("agentonboarded11182025")

        if company_id and company:
            if company_id != company:
                continue

        if not company_id:
            # Queue for batch update instead of immediate commit
            agents_needing_company.append(agent)
            company_id = str(auth.company_id) if auth.company_id is not None else None

        # Queue agents needing onboarding instead of processing inline
        if not agentonboarded11182025 or agentonboarded11182025.lower() != "true":
            agents_needing_onboard.append(agent.id)

        is_owner = agent.user_id == user_data.id
        is_shared = settings_dict.get("shared", "false") == "true"

        output.append(
            {
                "name": agent.name,
                "id": agent.id,
                "status": False,
                "company_id": company_id,
                "default": str(agent.id) == str(default_agent_id),
                "is_owner": is_owner,
                "is_shared": is_shared,
                "access_level": "owner" if is_owner else "viewer",
            }
        )

    # Batch update agents needing company_id
    if agents_needing_company:
        company_id_value = str(auth.company_id) if auth.company_id is not None else None
        for agent in agents_needing_company:
            agent_setting = AgentSettingModel(
                agent_id=agent.id,
                name="company_id",
                value=company_id_value,
            )
            session.add(agent_setting)
        session.commit()

    # Process agent onboarding asynchronously/in background if needed
    # For now, do a single batch onboard instead of per-agent
    if agents_needing_onboard:
        _batch_onboard_agents(session, agents_needing_onboard)

    session.close()
    return output


def _batch_onboard_agents(session, agent_ids):
    """
    Batch onboard multiple agents - enables Core Abilities commands.
    This is more efficient than processing one at a time.
    """
    if not agent_ids:
        return

    # Get Core Abilities category and its extensions once
    core_abilities_category = (
        session.query(ExtensionCategory)
        .filter(ExtensionCategory.name == "Core Abilities")
        .first()
    )

    if not core_abilities_category:
        # Mark all agents as onboarded even if no Core Abilities found
        for agent_id in agent_ids:
            agent_setting = AgentSettingModel(
                agent_id=agent_id,
                name="agentonboarded11182025",
                value="true",
            )
            session.add(agent_setting)
        session.commit()
        return

    # Get all Core Abilities commands in one query
    core_commands = (
        session.query(Command)
        .join(Extension)
        .filter(Extension.category_id == core_abilities_category.id)
        .all()
    )

    if not core_commands:
        # Mark all agents as onboarded even if no commands found
        for agent_id in agent_ids:
            agent_setting = AgentSettingModel(
                agent_id=agent_id,
                name="agentonboarded11182025",
                value="true",
            )
            session.add(agent_setting)
        session.commit()
        return

    # Get existing agent commands for all agents in one query
    existing_agent_commands = (
        session.query(AgentCommand).filter(AgentCommand.agent_id.in_(agent_ids)).all()
    )

    # Build lookup set for existing commands
    existing_lookup = {(ac.agent_id, ac.command_id) for ac in existing_agent_commands}

    # Add missing commands and update disabled ones
    for agent_id in agent_ids:
        for command in core_commands:
            key = (agent_id, command.id)
            if key not in existing_lookup:
                agent_command = AgentCommand(
                    agent_id=agent_id, command_id=command.id, state=True
                )
                session.add(agent_command)

        # Mark agent as onboarded
        agent_setting = AgentSettingModel(
            agent_id=agent_id,
            name="agentonboarded11182025",
            value="true",
        )
        session.add(agent_setting)

    # Enable any disabled commands
    for ac in existing_agent_commands:
        if ac.agent_id in agent_ids and not ac.state:
            # Check if this is a core command
            if ac.command_id in {c.id for c in core_commands}:
                ac.state = True

    session.commit()


def clone_agent(agent_id, new_agent_name, user=DEFAULT_USER):
    """
    Clone an agent, copying all settings and commands.
    User must have access to the source agent.
    """
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()

    # Check access to source agent
    can_access, is_owner, access_level = can_user_access_agent(
        user_id=user_data.id, agent_id=agent_id
    )

    if not can_access:
        session.close()
        raise HTTPException(status_code=403, detail="No access to source agent")

    # Get source agent
    source_agent = session.query(AgentModel).filter(AgentModel.id == agent_id).first()

    if not source_agent:
        session.close()
        raise HTTPException(status_code=404, detail="Source agent not found")

    # Get source agent settings
    source_settings = (
        session.query(AgentSettingModel)
        .filter(AgentSettingModel.agent_id == agent_id)
        .all()
    )

    settings_dict = {s.name: s.value for s in source_settings}

    # Remove shared flag - cloned agents are private by default
    settings_dict.pop("shared", None)

    # Get source agent commands
    source_commands = (
        session.query(AgentCommand).filter(AgentCommand.agent_id == agent_id).all()
    )

    # Batch load all commands referenced by the agent commands
    command_ids = [ac.command_id for ac in source_commands]
    commands_map = {}
    if command_ids:
        commands = session.query(Command).filter(Command.id.in_(command_ids)).all()
        commands_map = {c.id: c.name for c in commands}

    commands_dict = {}
    for ac in source_commands:
        command_name = commands_map.get(ac.command_id)
        if command_name:
            commands_dict[command_name] = ac.state

    session.close()

    # Create new agent using existing add_agent function
    result = add_agent(
        agent_name=new_agent_name,
        provider_settings=settings_dict,
        commands=commands_dict,
        user=user,
    )

    return result


class Agent:
    def __init__(
        self,
        agent_name=None,
        agent_id=None,
        user=DEFAULT_USER,
        ApiClient: Any = None,
    ):
        # Validate that either agent_name or agent_id is provided, but not both
        if agent_name is not None and agent_id is not None:
            raise ValueError(
                "Cannot specify both agent_name and agent_id. Please provide only one."
            )
        if agent_name is None and agent_id is None:
            agent_name = "AGiXT"  # Default fallback

        self.agent_name = agent_name
        self.agent_id = agent_id
        # Handle user dict from verify_api_key
        if isinstance(user, dict):
            user = user.get("email", DEFAULT_USER)
        user = user if user is not None else DEFAULT_USER
        self.user = user.lower()
        self.user_id = get_user_id(user=self.user)
        token = impersonate_user(user_id=str(self.user_id))
        self.auth = MagicalAuth(token=token)
        self.company_id = None

        # If agent_id was provided, check if it's a valid UUID or actually a name
        if self.agent_id is not None:
            try:
                # Try to parse as UUID - if it works, it's a real ID
                import uuid as uuid_module

                uuid_module.UUID(str(self.agent_id))
                self.agent_name = self.get_agent_name_by_id()
            except ValueError:
                # Not a valid UUID - treat it as agent_name instead
                self.agent_name = self.agent_id
                self.agent_id = None
                agent_id_result = self.get_agent_id()
                self.agent_id = (
                    str(agent_id_result) if agent_id_result is not None else None
                )
        else:
            agent_id_result = self.get_agent_id()
            self.agent_id = (
                str(agent_id_result) if agent_id_result is not None else None
            )

        self.AGENT_CONFIG = self.get_agent_config()
        self.load_config_keys()
        if "settings" not in self.AGENT_CONFIG:
            self.AGENT_CONFIG["settings"] = {}
        self.PROVIDER_SETTINGS = (
            self.AGENT_CONFIG["settings"] if "settings" in self.AGENT_CONFIG else {}
        )
        for setting in DEFAULT_SETTINGS:
            if setting not in self.PROVIDER_SETTINGS:
                self.PROVIDER_SETTINGS[setting] = DEFAULT_SETTINGS[setting]

        # Clean up settings that shouldn't be passed to providers
        for key in ["name", "ApiClient", "agent_name", "user", "user_id", "api_key"]:
            if key in self.PROVIDER_SETTINGS:
                del self.PROVIDER_SETTINGS[key]

        # Extract company_id early for AIProviderManager to use for company-level settings
        # This allows the provider manager to query CompanyExtensionSetting table
        early_company_id = self.AGENT_CONFIG.get("settings", {}).get("company_id")
        if early_company_id and str(early_company_id).lower() in ["none", "null", ""]:
            early_company_id = None

        # Initialize AI Provider Manager to discover AI Provider extensions
        self.ai_provider_manager = AIProviderManager(
            agent_settings=self.PROVIDER_SETTINGS,
            company_id=str(early_company_id) if early_company_id else None,
        )

        # Store ApiClient and token for provider access
        self._ApiClient = ApiClient
        self._token = token

        # Set up service availability flags from AI Provider Manager
        logging.debug(
            f"[Agent] Using AI Provider extensions: {self.ai_provider_manager.get_provider_names()}"
        )
        self.PROVIDER = None  # Will use ai_provider_manager in inference methods
        self.VISION_PROVIDER = None
        self.TTS_PROVIDER = (
            True if self.ai_provider_manager.has_service("tts") else None
        )  # Flag for availability
        self.TRANSCRIPTION_PROVIDER = (
            True if self.ai_provider_manager.has_service("transcription") else None
        )
        self.TRANSLATION_PROVIDER = (
            True if self.ai_provider_manager.has_service("translation") else None
        )
        self.IMAGE_PROVIDER = (
            True if self.ai_provider_manager.has_service("image") else None
        )

        try:
            self.max_input_tokens = int(self.AGENT_CONFIG["settings"]["MAX_TOKENS"])
        except Exception as e:
            self.max_input_tokens = 32000
        self.chunk_size = 256
        self.extensions = Extensions(
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            agent_config=self.AGENT_CONFIG,
            ApiClient=ApiClient,
            api_key=ApiClient.headers.get("Authorization"),
            user=self.user,
        )
        self.available_commands = self.extensions.get_available_commands()

        # CodeQL ultra-safe pattern: Create secure workspace directory
        base_workspace = "WORKSPACE"
        os.makedirs(base_workspace, exist_ok=True)

        # Create agent-specific directory using hash of agent_id for security
        import hashlib

        if self.agent_id:
            agent_hash = hashlib.sha256(str(self.agent_id).encode()).hexdigest()[:16]
            agent_workspace = f"{base_workspace}/agent_{agent_hash}"
        else:
            agent_workspace = f"{base_workspace}/default_agent"

        os.makedirs(agent_workspace, exist_ok=True)
        self.working_directory = agent_workspace
        if "company_id" in self.AGENT_CONFIG["settings"]:
            company_id_value = self.AGENT_CONFIG["settings"]["company_id"]
            # Handle various None representations
            if company_id_value is None or str(company_id_value).lower() in [
                "none",
                "null",
                "",
            ]:
                self.company_id = None
            else:
                self.company_id = str(company_id_value)
        else:
            self.company_id = None
        self.PROVIDER_SETTINGS["company_id"] = self.company_id
        self.company_agent = None
        if self.company_id:
            self.company_agent = self.get_company_agent()

    def get_company_agent(self):
        # Check for actual None or "None" string
        if self.company_id and str(self.company_id).lower() != "none":
            company_agent_session = self.auth.get_company_agent_session(
                company_id=self.company_id
            )
            if not company_agent_session:
                return None
            # Company agents have email format: {company_id}@{company_id}.xt
            company_email = f"{self.company_id}@{self.company_id}.xt"
            agent = Agent(
                agent_name="AGiXT",
                user=company_email,
                ApiClient=company_agent_session,
            )
            return agent
        else:
            return None

    def get_company_agent_extensions(self):
        agent_extensions = self.get_agent_extensions()
        if self.company_id:
            agent = self.get_company_agent()
            company_extensions = agent.get_agent_extensions()
            # We want to find out if any commands are enabled in company_extensions and set them to enabled for agent_extensions
            for company_extension in company_extensions:
                for agent_extension in agent_extensions:
                    if (
                        company_extension["extension_name"]
                        == agent_extension["extension_name"]
                    ):
                        for company_command in company_extension["commands"]:
                            for agent_command in agent_extension["commands"]:
                                if (
                                    company_command["friendly_name"]
                                    == agent_command["friendly_name"]
                                ):
                                    if (
                                        str(company_command["enabled"]).lower()
                                        == "true"
                                    ):
                                        agent_command["enabled"] = True
            return agent_extensions
        else:
            return agent_extensions

    def load_config_keys(self):
        config_keys = [
            "AI_MODEL",
            "AI_TEMPERATURE",
            "MAX_TOKENS",
            "embedder",
        ]
        for key in config_keys:
            if key in self.AGENT_CONFIG:
                setattr(self, key, self.AGENT_CONFIG[key])

    def get_registration_requirement_settings(self):
        with open("registration_requirements.json", "r") as read_file:
            data = json.load(read_file)
        agent_settings = {}
        user_preferences_keys = []
        for key in data:
            user_preferences_keys.append(key)
        session = get_session()
        user_preferences = (
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == self.user_id)
            .all()
        )
        for user_preference in user_preferences:
            if user_preference.pref_key in user_preferences_keys:
                agent_settings[user_preference.pref_key] = str(
                    user_preference.pref_value
                )
        session.close()
        return agent_settings

    def get_agent_settings_only(self):
        """
        Lightweight method to get just agent settings without commands, wallet creation, etc.
        Use this when you only need settings like embeddings_provider or MAX_TOKENS.
        Much faster than get_agent_config() for read-only operations.
        """
        session = get_session()
        try:
            # Find agent
            agent = None
            if (
                hasattr(self, "agent_id")
                and self.agent_id
                and str(self.agent_id) != "None"
            ):
                agent = (
                    session.query(AgentModel)
                    .filter(AgentModel.id == self.agent_id)
                    .first()
                )
            if not agent:
                agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.name == self.agent_name,
                        AgentModel.user_id == self.user_id,
                    )
                    .first()
                )

            if not agent:
                return {"embeddings_provider": "default"}

            # Get settings in one query
            settings = {}
            agent_settings = (
                session.query(AgentSettingModel).filter_by(agent_id=agent.id).all()
            )
            for setting in agent_settings:
                if setting.value:
                    settings[setting.name] = setting.value

            return settings
        finally:
            session.close()

    def get_agent_config(self):
        # Check cache first - short TTL for request batching
        cached = get_agent_data_cached(
            agent_id=str(self.agent_id) if self.agent_id else None,
            agent_name=self.agent_name,
            user_id=str(self.user_id),
        )
        if cached and cached.get("config"):
            # Update agent_id from cache if we didn't have it
            if not self.agent_id and cached.get("agent_id"):
                self.agent_id = cached["agent_id"]
            return cached["config"].copy()  # Return copy to prevent mutation

        session = get_session()

        # CRITICAL: Begin a new transaction to ensure we see committed data from other workers
        # SQLite with multiple processes can have stale reads without this
        try:
            session.execute("SELECT 1")  # Force connection to be active
            session.commit()  # Commit any implicit transaction to release locks
        except Exception:
            pass  # Ignore if already in a good state

        # If we have agent_id, use it to find the agent
        if (
            hasattr(self, "agent_id")
            and self.agent_id is not None
            and str(self.agent_id) != "None"
        ):
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.id == self.agent_id, AgentModel.user_id == self.user_id
                )
                .first()
            )
            if not agent:
                # Try to find in global agents (DEFAULT_USER)
                global_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                if global_user:
                    agent = (
                        session.query(AgentModel)
                        .filter(
                            AgentModel.id == self.agent_id,
                            AgentModel.user_id == global_user.id,
                        )
                        .first()
                    )
            if not agent:
                # Check for company-shared agent access using can_user_access_agent
                can_access, is_owner, access_level = can_user_access_agent(
                    user_id=self.user_id, agent_id=self.agent_id, auth=self.auth
                )
                if can_access:
                    # User has access to a shared agent, get it directly by ID
                    agent = (
                        session.query(AgentModel)
                        .filter(AgentModel.id == self.agent_id)
                        .first()
                    )
        else:
            # Use agent_name to find the agent
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user_id == self.user_id,
                )
                .first()
            )
            if not agent:
                agent = (
                    session.query(AgentModel)
                    .filter(AgentModel.user_id == self.user_id)
                    .first()
                )
                if not agent:
                    # Create an agent.
                    add_agent(agent_name=self.agent_name, user=self.user)
                    # Close the current session and get a new one to see the newly committed agent
                    session.close()
                    session = get_session()
                    # Get the agent
                    agent = (
                        session.query(AgentModel)
                        .filter(
                            AgentModel.name == self.agent_name,
                            AgentModel.user_id == self.user_id,
                        )
                        .first()
                    )
            self.agent_id = str(agent.id) if agent else None
        config = {"settings": {}, "commands": {}}

        # Wallet Creation Logic - Runs only if agent exists
        if agent:
            # Get ALL wallet settings in a single query (optimized from 3 separate queries)
            wallet_setting_names = [
                "SOLANA_WALLET_ADDRESS",
                "SOLANA_WALLET_API_KEY",
                "SOLANA_WALLET_PASSPHRASE_API_KEY",
            ]
            all_wallet_settings = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name.in_(wallet_setting_names),
                )
                .all()
            )

            # Group by setting name
            wallet_settings_by_name = {}
            for setting in all_wallet_settings:
                if setting.name not in wallet_settings_by_name:
                    wallet_settings_by_name[setting.name] = []
                wallet_settings_by_name[setting.name].append(setting)

            all_wallet_addresses = wallet_settings_by_name.get(
                "SOLANA_WALLET_ADDRESS", []
            )
            all_private_keys = wallet_settings_by_name.get("SOLANA_WALLET_API_KEY", [])
            all_passphrases = wallet_settings_by_name.get(
                "SOLANA_WALLET_PASSPHRASE_API_KEY", []
            )

            # Clean up duplicates - keep only the first one with a value, or first one if none have values
            def cleanup_duplicates(settings_list):
                if len(settings_list) <= 1:
                    return settings_list[0] if settings_list else None

                # Find the first setting with a non-empty value
                keeper = None
                for setting in settings_list:
                    if setting.value:
                        keeper = setting
                        break

                # If no setting has a value, keep the first one
                if keeper is None:
                    keeper = settings_list[0]

                # Delete all duplicates except the keeper
                for setting in settings_list:
                    if setting.id != keeper.id:
                        session.delete(setting)

                return keeper

            existing_wallet_address = cleanup_duplicates(all_wallet_addresses)
            existing_private_key = cleanup_duplicates(all_private_keys)
            existing_passphrase = cleanup_duplicates(all_passphrases)

            # Commit duplicate cleanup before checking if wallet needs creation
            try:
                session.commit()
            except Exception as e:
                logging.warning(f"Error cleaning up duplicate wallet settings: {e}")
                session.rollback()

            # Check if wallet doesn't exist or any of the critical settings are empty
            wallet_needs_creation = (
                not existing_wallet_address
                or not existing_private_key
                or not existing_passphrase
                or not (existing_wallet_address and existing_wallet_address.value)
                or not (existing_private_key and existing_private_key.value)
                or not (existing_passphrase and existing_passphrase.value)
            )

            if wallet_needs_creation:
                # Wallet doesn't exist or is incomplete, create and save it
                logging.debug(
                    f"Solana wallet missing or incomplete for agent {agent.name} ({agent.id}). Creating new wallet..."
                )
                try:
                    private_key, passphrase, address = create_solana_wallet()

                    # Update or create the settings
                    if existing_private_key:
                        existing_private_key.value = private_key
                    else:
                        session.add(
                            AgentSettingModel(
                                agent_id=agent.id,
                                name="SOLANA_WALLET_API_KEY",
                                value=private_key,
                            )
                        )

                    if existing_passphrase:
                        existing_passphrase.value = passphrase
                    else:
                        session.add(
                            AgentSettingModel(
                                agent_id=agent.id,
                                name="SOLANA_WALLET_PASSPHRASE_API_KEY",
                                value=passphrase,
                            )
                        )

                    if existing_wallet_address:
                        existing_wallet_address.value = address
                    else:
                        session.add(
                            AgentSettingModel(
                                agent_id=agent.id,
                                name="SOLANA_WALLET_ADDRESS",
                                value=address,
                            )
                        )

                    session.commit()
                    logging.debug(
                        f"Successfully created and saved Solana wallet for agent {agent.name} ({agent.id})."
                    )

                    # Refresh agent_settings to include newly created wallet settings
                    agent_settings = (
                        session.query(AgentSettingModel)
                        .filter_by(agent_id=agent.id)
                        .all()
                    )
                except Exception as e:
                    logging.error(
                        f"Error creating/saving Solana wallet for agent {agent.name} ({agent.id}): {e}"
                    )
                    session.rollback()  # Rollback DB changes on error

        if agent:
            # Force fresh read from database - critical for multi-worker consistency
            # Without this, SQLAlchemy may return stale cached data from previous queries
            session.expire_all()

            # Use cached commands to avoid repeated queries
            all_commands = get_all_commands_cached(session)
            # Only query agent_settings if not already refreshed after wallet creation
            if "agent_settings" not in locals():
                agent_settings = (
                    session.query(AgentSettingModel).filter_by(agent_id=agent.id).all()
                )

            agent_commands = (
                session.query(AgentCommand)
                .filter(AgentCommand.agent_id == agent.id)
                .all()
            )

            # Build a set of enabled command IDs for O(1) lookup (optimized from O(n*m))
            enabled_command_ids = {ac.command_id for ac in agent_commands if ac.state}

            # Process all commands, including chains
            for command in all_commands:
                config["commands"][command.name] = command.id in enabled_command_ids
            for setting in agent_settings:
                # Don't skip wallet-related settings even if they're empty (they should have been created above)
                # but skip other empty settings as before
                if setting.value == "" and not setting.name.startswith("SOLANA_WALLET"):
                    continue
                config["settings"][setting.name] = setting.value
            user_settings = self.get_registration_requirement_settings()
            for key, value in user_settings.items():
                config["settings"][key] = value
        else:
            config = {"settings": DEFAULT_SETTINGS, "commands": {}}
            user_settings = self.get_registration_requirement_settings()
            for key, value in user_settings.items():
                if value == "":
                    continue
                config["settings"][key] = value
        session.close()
        company_id = config["settings"].get("company_id")
        if company_id:
            self.company_id = company_id
            if str(self.user).endswith(".xt"):
                return config
            company_agent = self.get_company_agent()
            if company_agent:
                # Use cached company agent config to avoid expensive recursive call
                company_agent_config = get_company_agent_config_cached(
                    company_id, company_agent
                )
                company_settings = company_agent_config.get("settings")
                for key, value in company_settings.items():
                    if key not in config["settings"]:
                        if value == "":
                            continue
                        config["settings"][key] = value
                comand_agent_commands = company_agent_config.get("commands")
                for key, value in comand_agent_commands.items():
                    if key not in config["commands"]:
                        config["commands"][key] = value
        else:
            company_id = self.auth.company_id
            self.update_agent_config(
                new_config={"company_id": company_id}, config_key="settings"
            )
        enabled_commands = getenv("ENABLED_COMMANDS")
        if "," in enabled_commands:
            enabled_commands = enabled_commands.split(",")
        else:
            enabled_commands = [enabled_commands]
        for command in enabled_commands:
            config["commands"][command] = True
        session.close()

        # Cache the result for short-term reuse within request cycle
        set_agent_data_cache(
            agent_id=str(self.agent_id) if self.agent_id else None,
            agent_name=self.agent_name,
            user_id=str(self.user_id),
            data={
                "agent_id": str(self.agent_id) if self.agent_id else None,
                "agent_name": self.agent_name,
                "config": config,
            },
        )
        return config

    async def inference(
        self,
        prompt: str,
        images: list = [],
        use_smartest: bool = False,
        stream: bool = False,
        max_retries: int = 3,
    ):
        if not prompt:
            return ""

        # Pre-check billing balance before running inference
        # This will raise HTTPException 402 if billing is enabled and balance is insufficient
        self.auth.check_billing_balance()

        input_tokens = get_tokens(prompt)
        service = "vision" if images else "llm"
        last_error = None

        # Retry loop - try different providers on failure
        for attempt in range(max_retries):
            # Get provider from AI Provider Manager (intelligent rotation built-in)
            provider = self.ai_provider_manager.get_provider_for_service(
                service=service,
                tokens=input_tokens,
                use_smartest=use_smartest,
            )
            if provider is None:
                if attempt == 0:
                    raise HTTPException(
                        status_code=503,
                        detail="No AI providers available for inference",
                    )
                # No more providers available after failures
                logging.warning(
                    f"[Inference] No more providers available after {attempt} failed attempt(s)"
                )
                break

            provider_name = provider.__class__.__name__.replace("aiprovider_", "")

            # Emit webhook event for inference start
            await webhook_emitter.emit_event(
                event_type="agent.inference.started",
                data={
                    "agent_id": str(self.agent_id),
                    "agent_name": self.agent_name,
                    "user_id": str(self.user_id),
                    "provider": provider_name,
                    "input_tokens": input_tokens,
                    "use_smartest": use_smartest,
                    "has_images": len(images) > 0,
                    "attempt": attempt + 1,
                    "timestamp": datetime.now().isoformat(),
                },
                user_id=str(self.user_id),
            )

            try:
                if stream:
                    # For streaming, return the stream object for the caller to handle
                    # Note: streaming doesn't support retry since we return the stream directly
                    return await provider.inference(
                        prompt=prompt,
                        tokens=input_tokens,
                        images=images,
                        stream=True,
                        use_smartest=use_smartest,
                    )
                else:
                    # Non-streaming path
                    answer = await provider.inference(
                        prompt=prompt,
                        tokens=input_tokens,
                        images=images,
                        use_smartest=use_smartest,
                    )
                    output_tokens = get_tokens(answer)
                    self.auth.increase_token_counts(
                        input_tokens=input_tokens, output_tokens=output_tokens
                    )

                    answer = str(answer).replace("\\_", "_")
                    if answer.endswith("\n\n"):
                        answer = answer[:-2]

                    # Emit webhook event for successful inference
                    await webhook_emitter.emit_event(
                        event_type="agent.inference.completed",
                        data={
                            "agent_id": str(self.agent_id),
                            "agent_name": self.agent_name,
                            "user_id": str(self.user_id),
                            "provider": provider_name,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "timestamp": datetime.now().isoformat(),
                        },
                        user_id=str(self.user_id),
                    )
                    return answer

            except Exception as e:
                last_error = str(e)
                logging.error(
                    f"Error in inference with provider '{provider_name}': {last_error}"
                )
                # Mark provider as failed for rotation tracking
                self.ai_provider_manager.mark_provider_failed(provider_name)

                # Emit webhook event for failed inference
                await webhook_emitter.emit_event(
                    event_type="agent.inference.failed",
                    data={
                        "agent_id": str(self.agent_id),
                        "agent_name": self.agent_name,
                        "user_id": str(self.user_id),
                        "provider": provider_name,
                        "error": last_error,
                        "attempt": attempt + 1,
                        "will_retry": attempt + 1 < max_retries,
                        "timestamp": datetime.now().isoformat(),
                    },
                    user_id=str(self.user_id),
                )

                # If not the last attempt, log that we're retrying
                if attempt + 1 < max_retries:
                    logging.info(
                        f"[Inference] Provider '{provider_name}' failed, attempting rotation to next provider..."
                    )
                continue

        # All retries exhausted
        logging.error(
            f"[Inference] All {max_retries} provider attempts failed. Last error: {last_error}"
        )
        return "<answer>Unable to process request.</answer>"

    async def vision_inference(
        self, prompt: str, images: list = [], use_smartest: bool = False
    ):
        if not prompt:
            return ""

        # Pre-check billing balance before running inference
        self.auth.check_billing_balance()

        input_tokens = get_tokens(prompt)

        # Get vision provider from AI Provider Manager
        provider = self.ai_provider_manager.get_provider_for_service(
            service="vision",
            tokens=input_tokens,
            use_smartest=use_smartest,
        )
        if provider is None:
            return ""

        provider_name = provider.__class__.__name__.replace("aiprovider_", "")
        try:
            answer = await provider.inference(
                prompt=prompt,
                tokens=input_tokens,
                images=images,
                use_smartest=use_smartest,
            )
            output_tokens = get_tokens(answer)
            self.auth.increase_token_counts(
                input_tokens=input_tokens, output_tokens=output_tokens
            )

            answer = str(answer).replace("\\_", "_")
            if answer.endswith("\n\n"):
                answer = answer[:-2]
        except Exception as e:
            logging.error(f"Error in vision inference: {str(e)}")
            answer = "<answer>Unable to process request.</answer>"
        return answer

    def embeddings(self, input) -> np.ndarray:
        from Memories import embed

        return embed(input=input)

    async def transcribe_audio(self, audio_path: str):
        provider = self.ai_provider_manager.get_provider_for_service("transcription")
        if provider is None:
            raise HTTPException(
                status_code=400,
                detail="No transcription provider available",
            )
        return await provider.transcribe_audio(audio_path=audio_path)

    async def translate_audio(self, audio_path: str):
        provider = self.ai_provider_manager.get_provider_for_service("translation")
        if provider is None:
            raise HTTPException(
                status_code=400,
                detail="No translation provider available",
            )
        return await provider.translate_audio(audio_path=audio_path)

    async def generate_image(self, prompt: str, conversation_id: str = None):
        provider = self.ai_provider_manager.get_provider_for_service("image")
        if provider is None:
            raise HTTPException(
                status_code=400,
                detail="This agent is not configured with an image-capable provider.",
            )

        if not conversation_id or conversation_id == "-":
            conversation_id = get_conversation_id_by_name(
                conversation_name="-", user_id=self.user_id
            )

        # Get the base64 encoded image from the provider
        image_content = await provider.generate_image(prompt=prompt)

        # Handle the image storage similar to TTS
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        import tempfile
        import shutil

        def sanitize_path_component(component: str) -> str:
            """Sanitize a path component to prevent path traversal attacks"""
            if not component or not isinstance(component, str):
                raise ValueError("Invalid path component")
            sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", str(component))
            if (
                not sanitized
                or sanitized
                != component.replace("-", "").replace("_", "").replace(" ", "")
                or ".." in component
            ):
                sanitized = re.sub(r"[^a-zA-Z0-9-]", "", str(component))
            if not sanitized:
                raise ValueError("Invalid path component after sanitization")
            return sanitized

        safe_agent_id = sanitize_path_component(self.agent_id)
        safe_conversation_id = sanitize_path_component(conversation_id)

        with tempfile.TemporaryDirectory() as temp_base:
            secure_filename = f"image_{timestamp}.png"
            temp_image_path = f"{temp_base}/{secure_filename}"

            with open(temp_image_path, "wb") as f:
                f.write(base64.b64decode(image_content))

            workspace_base = os.path.realpath("WORKSPACE")

            def safe_workspace_path(base: str, *components: str) -> str:
                """Construct a safe path within workspace, preventing traversal."""
                constructed = os.path.join(base, *components)
                resolved = os.path.realpath(constructed)
                if not resolved.startswith(
                    os.path.realpath(base) + os.sep
                ) and resolved != os.path.realpath(base):
                    raise ValueError("Path traversal attempt blocked")
                return resolved

            workspace_outputs = safe_workspace_path(
                workspace_base, safe_agent_id, safe_conversation_id
            )
            os.makedirs(workspace_outputs, exist_ok=True)

            final_image_path = safe_workspace_path(
                workspace_base, safe_agent_id, safe_conversation_id, secure_filename
            )
            shutil.move(temp_image_path, final_image_path)

            agixt_uri = getenv("AGIXT_URI")
            output_url = f"{agixt_uri}/outputs/{safe_agent_id}/{safe_conversation_id}/{secure_filename}"
            return output_url

    async def text_to_speech(self, text: str, conversation_id: str = None):
        if not text:
            raise HTTPException(
                status_code=400,
                detail="No text provided for text-to-speech.",
            )
        if not conversation_id or conversation_id == "-":
            conversation_id = get_conversation_id_by_name(
                conversation_name="-", user_id=self.user_id
            )

        # Get TTS provider from AI Provider Manager
        tts_provider = self.ai_provider_manager.get_provider_for_service("tts")

        if tts_provider is not None:
            if "```" in text:
                text = re.sub(
                    r"```[^```]+```",
                    "See the chat for the full code block.",
                    text,
                )
            # If links are in there, replace them with a placeholder "The link provided in the chat."
            if "https://" in text:
                text = re.sub(
                    r"https://[^\s]+",
                    "The link provided in the chat.",
                    text,
                )
            if "http://" in text:
                text = re.sub(
                    r"http://[^\s]+",
                    "The link provided in the chat.",
                    text,
                )
            tts_content = await tts_provider.text_to_speech(text=text)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

            # CodeQL ultra-safe pattern: Complete data flow isolation
            import tempfile
            import shutil
            import re

            # Validate agent_id and conversation_id to prevent path traversal
            def sanitize_path_component(component: str) -> str:
                """Sanitize a path component to prevent path traversal attacks"""
                if not component or not isinstance(component, str):
                    raise ValueError("Invalid path component")
                # Only allow alphanumeric characters, hyphens, and underscores
                sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", str(component))
                if (
                    not sanitized
                    or sanitized
                    != component.replace("-", "").replace("_", "").replace(" ", "")
                    or ".." in component
                ):
                    # UUID format should be alphanumeric with hyphens
                    sanitized = re.sub(r"[^a-zA-Z0-9-]", "", str(component))
                if not sanitized:
                    raise ValueError("Invalid path component after sanitization")
                return sanitized

            safe_agent_id = sanitize_path_component(self.agent_id)
            safe_conversation_id = sanitize_path_component(conversation_id)

            # Create secure temporary directory completely isolated from user input
            with tempfile.TemporaryDirectory() as temp_base:
                # Create secure filename using only system-generated data
                secure_filename = f"agent_{timestamp}.wav"

                # Write audio data to secure temp file
                temp_audio_path = f"{temp_base}/{secure_filename}"
                with open(temp_audio_path, "wb") as f:
                    f.write(base64.b64decode(tts_content))

                # Create final secure location in workspace using validated paths only
                workspace_base = os.path.realpath("WORKSPACE")

                # Use a safe path construction helper to isolate tainted data
                def safe_workspace_path(base: str, *components: str) -> str:
                    """Construct a safe path within workspace, preventing traversal."""
                    # Build path from sanitized components only
                    constructed = os.path.join(base, *components)
                    resolved = os.path.realpath(constructed)
                    # Verify resolved path stays within base
                    if not resolved.startswith(
                        os.path.realpath(base) + os.sep
                    ) and resolved != os.path.realpath(base):
                        raise ValueError("Path traversal attempt blocked")
                    return resolved

                # Construct paths using only sanitized components
                workspace_outputs = safe_workspace_path(
                    workspace_base, safe_agent_id, safe_conversation_id
                )
                os.makedirs(
                    workspace_outputs, exist_ok=True
                )  # nosec B108 - path validated by safe_workspace_path

                # Construct final path using only validated components
                final_audio_path = safe_workspace_path(
                    workspace_base, safe_agent_id, safe_conversation_id, secure_filename
                )
                shutil.move(
                    temp_audio_path, final_audio_path
                )  # nosec B108 - path validated by safe_workspace_path
                agixt_uri = getenv("AGIXT_URI")
                output_url = f"{agixt_uri}/outputs/{safe_agent_id}/{safe_conversation_id}/{secure_filename}"
                return output_url

    async def text_to_speech_stream(self, text: str):
        """
        Stream TTS audio as it's generated, chunk by chunk.

        This enables real-time playback without waiting for the entire audio
        to be generated. Dramatically reduces time-to-first-word.

        Args:
            text: Text to convert to speech

        Yields:
            bytes: Binary audio data chunks
        """
        if not text:
            raise HTTPException(
                status_code=400,
                detail="No text provided for text-to-speech.",
            )

        # Get TTS provider from AI Provider Manager
        tts_provider = self.ai_provider_manager.get_provider_for_service("tts")

        if tts_provider is None:
            raise HTTPException(
                status_code=400,
                detail="No TTS provider configured for this agent.",
            )

        # Check if provider supports streaming
        if not hasattr(tts_provider, "text_to_speech_stream"):
            raise HTTPException(
                status_code=400,
                detail="TTS provider does not support streaming.",
            )

        # Clean text for TTS
        if "```" in text:
            text = re.sub(
                r"```[^```]+```",
                "See the chat for the full code block.",
                text,
            )
        if "https://" in text:
            text = re.sub(
                r"https://[^\s]+",
                "The link provided in the chat.",
                text,
            )
        if "http://" in text:
            text = re.sub(
                r"http://[^\s]+",
                "The link provided in the chat.",
                text,
            )

        async for chunk in tts_provider.text_to_speech_stream(text=text):
            yield chunk

    def get_agent_extensions(self):
        extensions = self.extensions.get_extensions()
        new_extensions = []
        session = get_session()

        # Batch queries - get user data once
        user_oauth = (
            session.query(UserOAuth).filter(UserOAuth.user_id == self.user_id).all()
        )
        user = session.query(User).filter(User.id == self.user_id).first()

        # Get SSO-enabled extensions from cache (expensive filesystem scan)
        sso_providers_set = get_sso_providers_cached()
        sso_providers = {name: False for name in sso_providers_set}

        # Check if this is a company agent (synthetic user with email {company_id}@{company_id}.xt)
        is_company_agent = user and str(user.email).lower().endswith(".xt")

        if is_company_agent:
            # For company agents, check OAuth connections from company admins/members
            # Extract company_id from email: {company_id}@{company_id}.xt
            company_email = str(user.email).lower()
            company_id = company_email.split("@")[0] if "@" in company_email else None

            if company_id:
                # Get all users who are members of this company
                company_user_ids = (
                    session.query(UserCompany.user_id)
                    .filter(UserCompany.company_id == company_id)
                    .all()
                )
                company_user_ids = [uid[0] for uid in company_user_ids]

                if company_user_ids:
                    # Get OAuth connections from any company member
                    company_oauth = (
                        session.query(UserOAuth)
                        .filter(UserOAuth.user_id.in_(company_user_ids))
                        .all()
                    )

                    if company_oauth:
                        provider_ids = [oauth.provider_id for oauth in company_oauth]
                        if provider_ids:
                            providers = (
                                session.query(OAuthProvider)
                                .filter(OAuthProvider.id.in_(provider_ids))
                                .all()
                            )
                            provider_names = {p.id: p.name for p in providers}

                            for oauth in company_oauth:
                                provider_name = provider_names.get(oauth.provider_id)
                                if provider_name:
                                    if str(provider_name).lower() in sso_providers:
                                        sso_providers[str(provider_name).lower()] = True
        else:
            # Regular user - check their own OAuth connections
            # Batch get OAuth provider names for user's connected providers
            if user_oauth:
                provider_ids = [oauth.provider_id for oauth in user_oauth]
                if provider_ids:
                    providers = (
                        session.query(OAuthProvider)
                        .filter(OAuthProvider.id.in_(provider_ids))
                        .all()
                    )
                    provider_names = {p.id: p.name for p in providers}

                    for oauth in user_oauth:
                        provider_name = provider_names.get(oauth.provider_id)
                        if provider_name:
                            if str(provider_name).lower() in sso_providers:
                                sso_providers[str(provider_name).lower()] = True

        for extension in extensions:
            extension_name_lower = str(extension["extension_name"]).lower()
            if extension_name_lower in sso_providers:
                # Special handling for wallet extension
                if extension_name_lower == "wallet":
                    # For wallet extensions, check if user is authenticated via wallet
                    # (user email ends with @crypto.wallet)
                    is_wallet_user = user and str(user.email).endswith("@crypto.wallet")
                    if not is_wallet_user:
                        continue  # Skip wallet extension for non-wallet users
                else:
                    # Regular OAuth provider logic
                    if not sso_providers[extension_name_lower]:
                        continue
                if extension_name_lower == "github":
                    extension["settings"] = []
            required_keys = extension["settings"]
            new_extension = extension.copy()

            # Transform settings from list of keys to list of objects with values
            settings_with_values = []
            has_configured_setting = False
            for key in required_keys:
                is_sensitive = any(
                    kw in key.upper()
                    for kw in ["API_KEY", "SECRET", "PASSWORD", "TOKEN", "PRIVATE"]
                )

                if key not in self.AGENT_CONFIG["settings"]:
                    if "missing_keys" not in new_extension:
                        new_extension["missing_keys"] = []
                    new_extension["missing_keys"].append(key)
                    settings_with_values.append(
                        {
                            "setting_key": key,
                            "setting_value": None,
                            "is_sensitive": is_sensitive,
                        }
                    )
                else:
                    value = self.AGENT_CONFIG["settings"][key]
                    if value == "" or value is None:
                        settings_with_values.append(
                            {
                                "setting_key": key,
                                "setting_value": None,
                                "is_sensitive": is_sensitive,
                            }
                        )
                    else:
                        has_configured_setting = True
                        # Mask sensitive values
                        if is_sensitive:
                            masked_value = (
                                "***" + str(value)[-4:]
                                if len(str(value)) > 4
                                else "****"
                            )
                        else:
                            masked_value = value
                        settings_with_values.append(
                            {
                                "setting_key": key,
                                "setting_value": masked_value,
                                "is_sensitive": is_sensitive,
                            }
                        )

            new_extension["settings"] = settings_with_values

            # Only disable commands if NO settings are configured
            if not has_configured_setting and required_keys:
                new_extension["commands"] = []

            if new_extension["commands"] == [] and not settings_with_values:
                continue
            new_extensions.append(new_extension)

        for extension in new_extensions:
            for command in extension["commands"]:
                friendly_name = command["friendly_name"]
                if friendly_name in self.AGENT_CONFIG["commands"]:
                    raw_value = self.AGENT_CONFIG["commands"][friendly_name]
                    computed_enabled = str(raw_value).lower() == "true"
                    command["enabled"] = computed_enabled
                else:
                    command["enabled"] = False
        session.close()
        return new_extensions

    def update_agent_config(self, new_config, config_key):
        session = get_session()

        # If we have agent_id, use it to find the agent
        if (
            hasattr(self, "agent_id")
            and self.agent_id is not None
            and str(self.agent_id) != "None"
        ):
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.id == self.agent_id, AgentModel.user_id == self.user_id
                )
                .first()
            )
            if not agent:
                # Try to find in global agents
                global_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                if global_user:
                    agent = (
                        session.query(AgentModel)
                        .filter(
                            AgentModel.id == self.agent_id,
                            AgentModel.user_id == global_user.id,
                        )
                        .first()
                    )
            if not agent:
                # Check for shared access (e.g., company agents)
                can_access, is_owner, access_level = can_user_access_agent(
                    user_id=self.user_id, agent_id=self.agent_id, auth=self.auth
                )
                if can_access:
                    agent = (
                        session.query(AgentModel)
                        .filter(AgentModel.id == self.agent_id)
                        .first()
                    )
        else:
            # Use agent_name to find the agent
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user_id == self.user_id,
                )
                .first()
            )
            if not agent:
                if self.user == DEFAULT_USER:
                    return f"Agent {self.agent_name} not found."
                # Check if it is a global agent and copy it if necessary
                global_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                global_agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.name == self.agent_name,
                        AgentModel.user_id == global_user.id,
                    )
                    .first()
                )
                if global_agent:
                    agent = AgentModel(
                        name=self.agent_name,
                        user_id=self.user_id,
                        provider_id=global_agent.provider_id,
                    )
                    session.add(agent)
                    session.commit()
                self.agent_id = str(agent.id)
                # Copy settings and commands from global agent
                for setting in global_agent.settings:
                    new_setting = AgentSettingModel(
                        agent_id=self.agent_id,
                        name=setting.name,
                        value=setting.value,
                    )
                    session.add(new_setting)
                for command in global_agent.commands:
                    new_command = AgentCommand(
                        agent_id=self.agent_id,
                        command_id=command.command_id,
                        state=command.state,
                    )
                    session.add(new_command)
                session.commit()

        if config_key == "commands":
            for command_name, enabled in new_config.items():
                # Protect against empty command names
                if not command_name or command_name.strip() == "":
                    logging.error("Empty command name provided in config, skipping")
                    continue

                # First try to find an existing command
                command = _resolve_command_by_name(session, command_name)

                if not command:
                    # Check if this is a chain command
                    chain = session.query(ChainDB).filter_by(name=command_name).first()
                    if chain:
                        # Find or create the Custom Automation extension
                        extension = (
                            session.query(Extension)
                            .filter_by(name="Custom Automation")
                            .first()
                        )
                        if not extension:
                            extension = Extension(name="Custom Automation")
                            session.add(extension)
                            session.commit()

                        # Create a new command entry for the chain
                        command = Command(name=command_name, extension_id=extension.id)
                        session.add(command)
                        session.commit()
                        # Invalidate the commands cache since we added a new command
                        invalidate_commands_cache()
                    else:
                        logging.error(f"Command {command_name} not found.")
                        continue

                # Now handle the agent command association
                agent_command = (
                    session.query(AgentCommand)
                    .filter_by(agent_id=self.agent_id, command_id=command.id)
                    .first()
                )

                if agent_command:
                    agent_command.state = enabled
                else:
                    agent_command = AgentCommand(
                        agent_id=self.agent_id,
                        command_id=command.id,
                        state=enabled,
                    )
                    session.add(agent_command)

                # Force flush to ensure the change is staged
                session.flush()
        else:
            for setting_name, setting_value in new_config.items():
                agent_setting = (
                    session.query(AgentSettingModel)
                    .filter_by(agent_id=self.agent_id, name=setting_name)
                    .first()
                )
                if agent_setting:
                    if setting_value == "":
                        session.delete(agent_setting)
                    else:
                        agent_setting.value = str(setting_value)
                else:
                    agent_setting = AgentSettingModel(
                        agent_id=self.agent_id,
                        name=setting_name,
                        value=str(setting_value),
                    )
                    session.add(agent_setting)

        try:
            session.commit()

            # Invalidate ALL caches to ensure other workers see the updated data
            # This is critical for multi-worker scenarios
            invalidate_company_config_cache()  # Clear company config cache
            invalidate_commands_cache()  # Clear commands cache
            invalidate_agent_data_cache(
                agent_id=str(self.agent_id)
            )  # Clear agent data cache

            # Emit webhook event for agent configuration update
            import asyncio

            try:
                asyncio.create_task(
                    webhook_emitter.emit_event(
                        event_type="agent.settings.updated",
                        data={
                            "agent_id": str(self.agent_id),
                            "agent_name": self.agent_name,
                            "user_id": str(self.user_id),
                            "config_key": config_key,
                            "updated_config": new_config,
                            "timestamp": datetime.now().isoformat(),
                        },
                        user_id=str(self.user_id),
                        company_id=str(self.company_id) if self.company_id else None,
                    )
                )
            except:
                logging.debug(
                    f"Could not emit webhook event for agent configuration update: {self.agent_name}"
                )
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating agent configuration: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error updating agent configuration: {str(e)}"
            )
        finally:
            session.close()

        return f"Agent {self.agent_name} configuration updated."

    def get_browsed_links(self, conversation_id=None):
        """
        Get the list of URLs that have been browsed by the agent.

        Returns:
            list: The list of URLs that have been browsed by the agent.
        """
        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            session.close()
            return []
        browsed_links = (
            session.query(AgentBrowsedLink)
            .filter_by(agent_id=agent.id, conversation_id=conversation_id)
            .order_by(AgentBrowsedLink.id.desc())
            .all()
        )
        session.close()
        if not browsed_links:
            return []
        return browsed_links

    def browsed_recently(self, url, conversation_id=None) -> bool:
        """
        Check if the given URL has been browsed by the agent within the last 24 hours.

        Args:
            url (str): The URL to check.

        Returns:
            bool: True if the URL has been browsed within the last 24 hours, False otherwise.
        """
        browsed_links = self.get_browsed_links(conversation_id=conversation_id)
        if not browsed_links:
            return False
        for link in browsed_links:
            if link["url"] == url:
                if link["timestamp"] >= datetime.now(timezone.utc) - timedelta(days=1):
                    return True
        return False

    def add_browsed_link(self, url, conversation_id=None):
        """
        Add a URL to the list of browsed links for the agent.

        Args:
            url (str): The URL to add.

        Returns:
            str: The response message.
        """
        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            return f"Agent {self.agent_name} not found."

        # Handle conversation_id conversion - convert "0" or invalid UUIDs to None
        if conversation_id == "0" or conversation_id == 0 or not conversation_id:
            conversation_id = None
        elif conversation_id:
            # Validate that it's a proper UUID string
            try:
                import uuid

                uuid.UUID(str(conversation_id))
                conversation_id = str(conversation_id)
            except (ValueError, TypeError):
                conversation_id = None

        browsed_link = AgentBrowsedLink(
            agent_id=agent.id, link=url, conversation_id=conversation_id
        )
        session.add(browsed_link)
        session.commit()
        session.close()
        return f"Link {url} added to browsed links."

    def delete_browsed_link(self, url, conversation_id=None):
        """
        Delete a URL from the list of browsed links for the agent.

        Args:
            url (str): The URL to delete.

        Returns:
            str: The response message.
        """
        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name,
                AgentModel.user_id == self.user_id,
            )
            .first()
        )
        if not agent:
            return f"Agent {self.agent_name} not found."
        browsed_link = (
            session.query(AgentBrowsedLink)
            .filter_by(agent_id=agent.id, link=url, conversation_id=conversation_id)
            .first()
        )
        if not browsed_link:
            return f"Link {url} not found."
        session.delete(browsed_link)
        session.commit()
        session.close()
        return f"Link {url} deleted from browsed links."

    def get_agent_name_by_id(self):
        """Get agent name by agent_id, checking ownership and shared access"""
        session = get_session()
        try:
            # First try to find agent owned by user
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.id == self.agent_id, AgentModel.user_id == self.user_id
                )
                .first()
            )
            if agent:
                return agent.name

            # Try to find in global agents (DEFAULT_USER)
            global_user = session.query(User).filter(User.email == DEFAULT_USER).first()
            if global_user:
                agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.id == self.agent_id,
                        AgentModel.user_id == global_user.id,
                    )
                    .first()
                )
                if agent:
                    return agent.name

            # Check if user has shared access to this agent
            can_access, is_owner, access_level = can_user_access_agent(
                user_id=self.user_id, agent_id=self.agent_id, auth=self.auth
            )
            if can_access:
                agent = (
                    session.query(AgentModel)
                    .filter(AgentModel.id == self.agent_id)
                    .first()
                )
                if agent:
                    return agent.name

            raise ValueError(
                f"Agent with ID {self.agent_id} not found or not accessible for user {self.user}"
            )
        finally:
            session.close()

    def get_agent_id(self):
        # Check cache first
        cached = get_agent_data_cached(
            agent_name=self.agent_name, user_id=str(self.user_id)
        )
        if cached and cached.get("agent_id"):
            return cached["agent_id"]

        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user.has(email=DEFAULT_USER),
                )
                .first()
            )
            session.close()
            if not agent:
                return None
        session.close()
        return agent.id

    @staticmethod
    def sanitize_path_component(component):
        """
        Sanitize a path component to prevent path traversal attacks.
        Implements CodeQL recommended security patterns.

        Args:
            component (str): The path component to sanitize

        Returns:
            str: The sanitized path component

        Raises:
            ValueError: If the component contains invalid characters
        """
        import re
        import os

        if not component or not isinstance(component, str):
            raise ValueError("Path component must be a non-empty string")

        # Strip whitespace
        component = component.strip()

        if not component:
            raise ValueError("Path component is empty after stripping whitespace")

        # Check for any path separators or dangerous sequences
        dangerous_patterns = [
            os.sep,  # OS-specific path separator
            os.altsep,  # Alternative path separator (Windows)
            "/",  # Forward slash
            "\\",  # Backslash
            "..",  # Parent directory
            ".",  # Current directory (except single char names)
            "~",  # Home directory
            "\0",  # Null byte
        ]

        for pattern in dangerous_patterns:
            if pattern and pattern in component:
                raise ValueError(
                    f"Invalid path component contains dangerous pattern: {repr(pattern)}"
                )

        # Use strict allowlist: only alphanumeric, hyphens, and underscores
        # This follows CodeQL recommendation for allowlist validation
        if not re.match(r"^[a-zA-Z0-9_-]+$", component):
            raise ValueError(f"Path component contains invalid characters: {component}")

        # Additional length check for security
        if len(component) > 255:
            raise ValueError("Path component too long")

        return component

    def get_conversation_tasks(self, conversation_id: str) -> str:
        """Get all tasks assigned to an agent"""
        session = None
        try:
            session = get_session()
            tasks = (
                session.query(TaskItem)
                .filter(
                    TaskItem.agent_id == self.agent_id,
                    TaskItem.user_id == self.user_id,
                    TaskItem.completed == False,
                    TaskItem.memory_collection == conversation_id,
                )
                .all()
            )
            if not tasks:
                return ""

            markdown_tasks = "## The Assistant's Scheduled Tasks\n**The assistant currently has the following tasks scheduled:**\n"
            for task in tasks:
                string_due_date = task.due_date.strftime("%Y-%m-%d %H:%M:%S")
                markdown_tasks += (
                    f"### Task: {task.title}\n"
                    f"**Description:** {task.description}\n"
                    f"**Will be completed at:** {string_due_date}\n"
                )
            return markdown_tasks
        except Exception as e:
            logging.error(f"Error getting tasks by agent: {str(e)}")
            return ""
        finally:
            if session:
                try:
                    session.close()
                except Exception as close_e:
                    logging.error(
                        f"Error closing session in get_conversation_tasks: {close_e}"
                    )

    def get_all_pending_tasks(self) -> list:
        """Get all tasks assigned to an agent"""
        session = None
        try:
            session = get_session()
            tasks = (
                session.query(TaskItem)
                .filter(
                    TaskItem.agent_id == self.agent_id,
                    TaskItem.user_id == self.user_id,
                    TaskItem.completed == False,
                )
                .all()
            )
            return tasks
        except Exception as e:
            logging.error(f"Error getting tasks by agent: {str(e)}")
            return []
        finally:
            if session:
                try:
                    session.close()
                except Exception as close_e:
                    logging.error(
                        f"Error closing session in get_all_pending_tasks: {close_e}"
                    )

    def get_all_commands_markdown(self):
        command_list = [
            available_command["friendly_name"]
            for available_command in self.available_commands
            if available_command["enabled"] == True
        ]
        if self.company_id and self.company_agent:
            company_command_list = [
                available_command["friendly_name"]
                for available_command in self.company_agent.available_commands
                if available_command["enabled"] == True
            ]
            # Check if anything enabled in company commands
            if len(company_command_list) > 0:
                # Check if the enabled items are already enabled for the user available commands
                for company_command in company_command_list:
                    if company_command not in command_list:
                        command_list.append(company_command)
        if len(command_list) > 0:
            try:
                agent_extensions = self.get_company_agent_extensions()
                if agent_extensions == "":
                    agent_extensions = self.get_agent_extensions()
            except Exception as e:
                logging.error(f"Error getting agent extensions: {str(e)}")
                agent_extensions = self.get_agent_extensions()
            agent_commands = "## Available Commands\n\n**See command examples of commands that the assistant has access to below:**\n"
            for extension in agent_extensions:
                if extension["commands"] == []:
                    continue
                extension_name = extension["extension_name"]
                extension_description = extension["description"]
                agent_commands += (
                    f"\n### {extension_name}\nDescription: {extension_description}\n"
                )
                for command in extension["commands"]:
                    command_friendly_name = command["friendly_name"]
                    command_description = command["description"]
                    agent_commands += f"\n#### {command_friendly_name}\nDescription: {command_description}\n"
                    for arg_name in command["command_args"].keys():
                        if arg_name != "chain_name":
                            agent_commands += f"<{arg_name}>The assistant will fill in the value based on relevance to the conversation.</{arg_name}>\n"
                        else:
                            agent_commands += (
                                f"<chain_name>{command_friendly_name}</chain_name>\n"
                            )
                    agent_commands += "</execute>\n"
            agent_commands += f"""## Command Usage Guidelines
- **The assistant has commands available to use if they would be useful to provide a better user experience.**
- Reference examples for correct syntax and usage of commands.
- All inputs are strings and must be appropriately filled in with the correct values.
- The assistant can execute a command anywhere in the response, and the commands will be executed in the order they appear.
- The assistant will receive the command output before the user does and will be able to reference the output in the response.
- The assistant can choose to execute as many commands as needed in the response in the order that they should be executed.
- Once the assistant executes a command, it should stop at </execute> and wait for the command output before continuing.
- If the command output indicates a failure status, try changing your approach and trying again, don't try to execute it with the same parameters if it fails, try something different.
- The assistant should never generate a <output> tag in the response. The assistant will receive the command output and will be able to reference the output in the response.
- If there is an <output> tag in the assistants previous responses in context, it refers to the command execution output. Use this output to determine if the command was successful, and to course correct if needed.
- Any time the assistant executes a command, the text generation should end with </execute>. The assistant will be informed of the command output before the user receives the response to give the assistant the opportunity to evaluate the output and ensure it is correct, exploring different options if needed.
- After command execution, increase step budget by 5, continue thinking, executing more commands if necessary for self-error correct unless user intervention is required, and then respond to the user.
- Command executions should all take place BEFORE the <answer> block! Never inside the <answer> block. Only the response to the user goes inside the <answer> block.
- Ensure that command names are EXACTLY as written in the command execution examples. A natural language friendly name is used.
- **THE ASSISTANT CANNOT EXECUTE A COMMAND THAT IS NOT ON THE LIST OF EXAMPLES!**"""
            return agent_commands
        return ""

    def get_commands_prompt(
        self, conversation_id, running_command=None, selected_commands=None
    ):
        """
        Get the commands prompt for the agent.

        Args:
            conversation_id: The conversation ID
            running_command: Command currently being executed (to exclude)
            selected_commands: List of command names to include. If None, includes all enabled commands.

        Returns:
            str: The formatted commands prompt
        """
        command_list = [
            available_command["friendly_name"]
            for available_command in self.available_commands
            if available_command["enabled"] == True
        ]

        if self.company_id and self.company_agent:
            company_command_list = [
                available_command["friendly_name"]
                for available_command in self.company_agent.available_commands
                if available_command["enabled"] == True
            ]
            # Check if anything enabled in company commands
            if len(company_command_list) > 0:
                # Check if the enabled items are already enabled for the user available commands
                for company_command in company_command_list:
                    if company_command not in command_list:
                        command_list.append(company_command)
        if len(command_list) > 0:
            working_directory = f"{self.working_directory}/{conversation_id}"
            conversation_outputs = (
                f"http://localhost:7437/outputs/{self.agent_id}/{conversation_id}/"
            )
            try:
                agent_extensions = self.get_company_agent_extensions()
                if agent_extensions == "":
                    agent_extensions = self.get_agent_extensions()
            except Exception as e:
                logging.error(f"Error getting agent extensions: {str(e)}")
                agent_extensions = self.get_agent_extensions()

            # Collect client-defined tools (extension_name == "__client__") from available_commands
            client_commands = [
                cmd
                for cmd in self.available_commands
                if cmd.get("extension_name") == "__client__"
                and cmd.get("enabled", False)
            ]
            if client_commands:
                logging.info(
                    f"[get_commands_prompt] Found {len(client_commands)} client-defined tools: {[c['friendly_name'] for c in client_commands]}"
                )

            agent_commands = "## Available Commands\n\n**See command execution examples of commands that the assistant has access to below:**\n"

            # First add client-defined tools as a special extension section
            if client_commands:
                agent_commands += f"\n### Client-Defined Tools\nDescription: These commands are executed on the client's machine (e.g., CLI terminal).\n"
                for command in client_commands:
                    if running_command and command["friendly_name"] == running_command:
                        continue
                    # If selected_commands is provided, only include selected ones
                    if (
                        selected_commands
                        and command["friendly_name"] not in selected_commands
                    ):
                        continue
                    command_friendly_name = command["friendly_name"]
                    command_description = command.get(
                        "description", f"Client-defined tool: {command_friendly_name}"
                    )
                    agent_commands += f"\n#### {command_friendly_name}\nDescription: {command_description}\nCommand execution format:\n"
                    agent_commands += (
                        f"<execute>\n<name>{command_friendly_name}</name>\n"
                    )
                    command_args = command.get("args", {})
                    for arg_name in command_args.keys():
                        agent_commands += f"<{arg_name}>The assistant will fill in the value based on relevance to the conversation.</{arg_name}>\n"
                    agent_commands += "</execute>\n"

            for extension in agent_extensions:
                if extension["commands"] == []:
                    continue
                extension_name = extension["extension_name"]
                extension_description = extension["description"]
                enabled_commands = [
                    command
                    for command in extension["commands"]
                    if command["enabled"] == True
                ]
                if running_command:
                    # Remove the running command from enabled commands
                    enabled_commands = [
                        command
                        for command in enabled_commands
                        if command["friendly_name"] != running_command
                    ]
                # If selected_commands is provided, filter to only selected ones
                if selected_commands:
                    enabled_commands = [
                        command
                        for command in enabled_commands
                        if command["friendly_name"] in selected_commands
                    ]
                if enabled_commands == []:
                    continue
                agent_commands += (
                    f"\n### {extension_name}\nDescription: {extension_description}\n"
                )
                for command in enabled_commands:
                    command_friendly_name = command["friendly_name"]
                    command_description = command["description"]
                    agent_commands += f"\n#### {command_friendly_name}\nDescription: {command_description}\nCommand execution format:\n"
                    agent_commands += (
                        f"<execute>\n<name>{command_friendly_name}</name>\n"
                    )
                    for arg_name in command["command_args"].keys():
                        if arg_name != "chain_name":
                            agent_commands += f"<{arg_name}>The assistant will fill in the value based on relevance to the conversation.</{arg_name}>\n"
                        else:
                            agent_commands += (
                                f"<chain_name>{command_friendly_name}</chain_name>\n"
                            )
                    agent_commands += "</execute>\n"

            agent_commands += f"""## Command Execution Guidelines
- **The assistant has commands available to use if they would be useful to provide a better user experience.**
- Reference examples for correct syntax and usage of commands.
- To execute a command, the assistant should use the following format:

<execute>
<name>FULL COMMAND NAME</name>
<ARG1_NAME>ARG1_VALUE</ARG1_NAME>
<ARG2_NAME>ARG2_VALUE</ARG2_NAME>
...
</execute>

- All inputs are strings and must be appropriately filled in with the correct values.
- The assistant can execute a command anywhere in the response, and the commands will be executed in the order they appear.
- If referencing a file path, use the assistant's working directory as the file path. The assistant's working directory is {working_directory}.
- Only reference files in the working directory! The assistant cannot access files outside of the working directory.
- All files in the working directory will be immediately available to the user and agent in this folder: {conversation_outputs}
- The assistant will receive the command output before the user does and will be able to reference the output in the response.
- The assistant can choose to execute as many commands as needed in the response in the order that they should be executed.
- Once the assistant executes a command, it should stop at </execute> and wait for the command output before continuing.
- The assistant should never generate a <output> tag in the response. The assistant will receive the command output and will be able to reference the output in the response.
- If there is an <output> tag in the assistants previous responses in context, it refers to the command execution output. Use this output to determine if the command was successful, and to course correct if needed.
- Any time the assistant executes a command, the text generation should end with </execute>. The assistant will be informed of the command output before the user receives the response to give the assistant the opportunity to evaluate the output and ensure it is correct, exploring different options if needed.
- After command execution, increase step budget by 5, continue thinking, executing more commands if necessary for self-error correct unless user intervention is required, and then respond to the user.
- Command executions should all take place BEFORE the <answer> block! Never inside the <answer> block. Only the response to the user goes inside the <answer> block.
- Ensure that command names are EXACTLY as written in the command execution examples. A natural language friendly name is used.
- **THE ASSISTANT CANNOT EXECUTE A COMMAND THAT IS NOT ON THE LIST OF EXAMPLES!**"""
            return agent_commands
        return ""

    def get_commands_for_selection(self):
        """
        Get all available commands with their descriptions for the tool selection phase.
        Returns a formatted string listing all commands grouped by extension.

        Returns:
            tuple: (formatted_string, list_of_command_names)
        """
        command_list = [
            available_command["friendly_name"]
            for available_command in self.available_commands
            if available_command["enabled"] == True
        ]

        if self.company_id and self.company_agent:
            company_command_list = [
                available_command["friendly_name"]
                for available_command in self.company_agent.available_commands
                if available_command["enabled"] == True
            ]
            for company_command in company_command_list:
                if company_command not in command_list:
                    command_list.append(company_command)

        if len(command_list) == 0:
            return "", []

        try:
            agent_extensions = self.get_company_agent_extensions()
            if agent_extensions == "":
                agent_extensions = self.get_agent_extensions()
        except Exception as e:
            logging.error(f"Error getting agent extensions: {str(e)}")
            agent_extensions = self.get_agent_extensions()

        # Collect client-defined tools
        client_commands = [
            cmd
            for cmd in self.available_commands
            if cmd.get("extension_name") == "__client__" and cmd.get("enabled", False)
        ]

        all_command_names = []
        selection_prompt = "## Available Commands for Selection\n\n"

        # Add client-defined tools
        if client_commands:
            selection_prompt += "### Client-Defined Tools\n"
            for command in client_commands:
                cmd_name = command["friendly_name"]
                cmd_desc = command.get(
                    "description", f"Client-defined tool: {cmd_name}"
                )
                selection_prompt += f"- **{cmd_name}**: {cmd_desc}\n"
                all_command_names.append(cmd_name)

        # Add extension commands
        for extension in agent_extensions:
            if extension["commands"] == []:
                continue
            extension_name = extension["extension_name"]
            extension_description = extension["description"]
            enabled_commands = [
                command
                for command in extension["commands"]
                if command["enabled"] == True
            ]
            if enabled_commands == []:
                continue

            selection_prompt += f"\n### {extension_name}\n{extension_description}\n"
            for command in enabled_commands:
                cmd_name = command["friendly_name"]
                cmd_desc = command["description"]
                selection_prompt += f"- **{cmd_name}**: {cmd_desc}\n"
                all_command_names.append(cmd_name)

        return selection_prompt, all_command_names

    def get_agent_wallet(self):
        """
        Retrieves the private key and passphrase for the agent's Solana wallet.
        If wallet doesn't exist or is empty, creates a new one.
        Strictly enforces one wallet per agent.
        Authenticates using the provided API key.
        """
        session = get_session()
        try:
            # Find the agent first to ensure it belongs to the user
            if (
                hasattr(self, "agent_id")
                and self.agent_id is not None
                and str(self.agent_id) != "None"
            ):
                agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.id == self.agent_id,
                        AgentModel.user_id == self.user_id,
                    )
                    .first()
                )
                if not agent:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Agent with ID '{self.agent_id}' not found for this user.",
                    )
            else:
                agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.name == self.agent_name,
                        AgentModel.user_id == self.user_id,
                    )
                    .first()
                )
                if not agent:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Agent '{self.agent_name}' not found for this user.",
                    )

            # Get ALL wallet settings for this agent (to handle duplicates)
            all_private_keys = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "SOLANA_WALLET_API_KEY",
                )
                .all()
            )

            all_passphrases = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "SOLANA_WALLET_PASSPHRASE_API_KEY",
                )
                .all()
            )

            all_addresses = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "SOLANA_WALLET_ADDRESS",
                )
                .all()
            )

            # Clean up duplicates - keep only the first one with a value, or first one if none have values
            def cleanup_duplicates(settings_list):
                if len(settings_list) <= 1:
                    return settings_list[0] if settings_list else None

                # Find the first setting with a non-empty value
                keeper = None
                for setting in settings_list:
                    if setting.value:
                        keeper = setting
                        break

                # If no setting has a value, keep the first one
                if keeper is None:
                    keeper = settings_list[0]

                # Delete all duplicates except the keeper
                for setting in settings_list:
                    if setting.id != keeper.id:
                        session.delete(setting)

                return keeper

            private_key_setting = cleanup_duplicates(all_private_keys)
            passphrase_setting = cleanup_duplicates(all_passphrases)
            address_setting = cleanup_duplicates(all_addresses)

            # Commit duplicate cleanup
            try:
                session.commit()
            except Exception as e:
                logging.warning(f"Error cleaning up duplicate wallet settings: {e}")
                session.rollback()

            # Check if wallet settings are missing or empty
            wallet_incomplete = (
                not private_key_setting
                or not passphrase_setting
                or not address_setting
                or not (private_key_setting and private_key_setting.value)
                or not (passphrase_setting and passphrase_setting.value)
                or not (address_setting and address_setting.value)
            )

            if wallet_incomplete:
                # Create a new wallet
                try:
                    private_key, passphrase, address = create_solana_wallet()

                    # Update or create the settings
                    if private_key_setting:
                        private_key_setting.value = private_key
                    else:
                        private_key_setting = AgentSettingModel(
                            agent_id=agent.id,
                            name="SOLANA_WALLET_API_KEY",
                            value=private_key,
                        )
                        session.add(private_key_setting)

                    if passphrase_setting:
                        passphrase_setting.value = passphrase
                    else:
                        passphrase_setting = AgentSettingModel(
                            agent_id=agent.id,
                            name="SOLANA_WALLET_PASSPHRASE_API_KEY",
                            value=passphrase,
                        )
                        session.add(passphrase_setting)

                    if address_setting:
                        address_setting.value = address
                    else:
                        address_setting = AgentSettingModel(
                            agent_id=agent.id,
                            name="SOLANA_WALLET_ADDRESS",
                            value=address,
                        )
                        session.add(address_setting)

                    session.commit()

                    # Refresh the variables after successful creation
                    private_key_value = private_key_setting.value
                    passphrase_value = passphrase_setting.value

                except Exception as wallet_creation_error:
                    session.rollback()
                    logging.error(
                        f"Error creating wallet for agent {self.agent_name}: {wallet_creation_error}"
                    )
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to create wallet for agent.",
                    )
            else:
                # Wallet exists and is complete
                private_key_value = private_key_setting.value
                passphrase_value = passphrase_setting.value

            return {
                "private_key": private_key_value,
                "passphrase": passphrase_value,
            }
        except HTTPException as e:
            session.rollback()
            logging.error(f"HTTPException: {e.detail}")
            raise e  # Re-raise HTTPException
        except Exception as e:
            session.rollback()
            logging.error(f"Error retrieving wallet for agent {self.agent_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error retrieving wallet details.",
            )
        finally:
            session.close()
