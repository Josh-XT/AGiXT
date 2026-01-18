import os
import sys
import json
import subprocess
import importlib.util
import tiktoken
from dotenv import load_dotenv
from multiprocessing import Manager

load_dotenv()

# Cache for installed packages to avoid repeated checks
_installed_packages_cache = set()


def install_package_if_missing(package_name: str, import_name: str = None) -> bool:
    """
    Install a package only if it's not already installed.

    Args:
        package_name: The pip package name to install (e.g., "PyGithub")
        import_name: The import name if different from package name (e.g., "github")

    Returns:
        True if package was installed, False if already present
    """
    global _installed_packages_cache

    # Use import_name for checking if provided, otherwise use package_name
    check_name = import_name or package_name

    # Check cache first
    if check_name in _installed_packages_cache:
        return False

    # Check if module can be imported
    spec = importlib.util.find_spec(check_name)
    if spec is not None:
        _installed_packages_cache.add(check_name)
        return False

    # Package not found, install it
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", package_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _installed_packages_cache.add(check_name)
    return True


# Global state for Machine Control Extension WebSocket connections
# Use multiprocessing.Manager to create a truly shared dict across ALL Python contexts
_manager = Manager()
MACHINE_ACTIVE_TERMINALS = _manager.dict()

# Server config cache to avoid repeated database queries
# Uses SharedCache for cross-worker consistency
_SERVER_CONFIG_CACHE_KEY = "server_config_cache"
_SERVER_CONFIG_CACHE_TTL = 3600  # 1 hour TTL - longer for stability without Redis
_server_config_cache_loaded = False

# Settings that should NEVER be loaded from database (infrastructure settings)
# These must be set via environment variables as they're needed before DB is available
_ENV_ONLY_SETTINGS = {
    "DATABASE_TYPE",
    "DATABASE_NAME",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_SSL",
    "UVICORN_WORKERS",
    "WORKING_DIRECTORY",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "AGIXT_HEALTH_URL",
    "HEALTH_CHECK_INTERVAL",
    "HEALTH_CHECK_TIMEOUT",
    "HEALTH_CHECK_MAX_FAILURES",
    "RESTART_COOLDOWN",
    "INITIAL_STARTUP_DELAY",
    "SEED_DATA",
    "AGIXT_API_KEY",
    "DEFAULT_USER",
    "USING_JWT",
    "ALLOWED_DOMAINS",
    "CHROMA_PORT",
    "CHROMA_SSL",
    "CREATE_AGENT_ON_REGISTER",
    "CREATE_AGIXT_AGENT",
    "DISABLED_EXTENSIONS",
    "DISABLED_PROVIDERS",
    "SUPERADMIN_EMAIL",
}


def load_server_config_cache():
    """
    Load all server config values from the database into shared cache.
    This is called once during startup after the database is initialized.
    Uses SharedCache for cross-worker consistency.

    Note: We cache ALL values including empty strings, so we can distinguish
    between "key not set" and "key explicitly set to empty" (which is used
    to disable providers at the server level).
    """
    global _server_config_cache_loaded

    if _server_config_cache_loaded:
        return

    try:
        # Import here to avoid circular imports
        from DB import ServerConfig, get_session, decrypt_config_value
        from SharedCache import shared_cache

        # Check if already in shared cache
        cached = shared_cache.get(_SERVER_CONFIG_CACHE_KEY)
        if cached is not None:
            _server_config_cache_loaded = True
            return

        # Load from database
        config_dict = {}
        with get_session() as db:
            configs = db.query(ServerConfig).all()
            for config in configs:
                # Cache all values including empty strings
                # Empty string means "explicitly cleared at server level"
                if config.value is not None:
                    if config.is_sensitive and config.value:
                        config_dict[config.name] = decrypt_config_value(config.value)
                    else:
                        config_dict[config.name] = config.value

        # Store in shared cache
        shared_cache.set(
            _SERVER_CONFIG_CACHE_KEY, config_dict, ttl=_SERVER_CONFIG_CACHE_TTL
        )
        _server_config_cache_loaded = True
    except Exception:
        # Database not initialized yet or other error - this is expected during startup
        pass


def invalidate_server_config_cache():
    """Invalidate the server config cache to force a reload across all workers."""
    global _server_config_cache_loaded
    try:
        from SharedCache import shared_cache

        shared_cache.delete(_SERVER_CONFIG_CACHE_KEY)
    except Exception:
        pass
    _server_config_cache_loaded = False


def server_config_has_key(var_name: str) -> bool:
    """
    Check if a key exists in server config cache (regardless of its value).
    This is used to determine if server admin explicitly set a value (even empty).
    """
    global _server_config_cache_loaded
    if not _server_config_cache_loaded:
        load_server_config_cache()
    try:
        from SharedCache import shared_cache

        cached = shared_cache.get(_SERVER_CONFIG_CACHE_KEY)
        if cached is not None:
            return var_name in cached
    except Exception:
        pass
    return False


def getenv(var_name: str, default_value: str = "") -> str:
    global _server_config_cache_loaded
    default_values = {
        "AGIXT_URI": "http://localhost:7437",
        "APP_URI": "http://localhost:3437",
        "AGIXT_API_KEY": "",
        "EZLOCALAI_URI": "http://localhost:8091/v1/",
        "EZLOCALAI_API_KEY": "",
        "AGENT_NAME": "AGiXT",
        "ALLOWED_DOMAINS": "*",
        "WORKING_DIRECTORY": os.path.join(os.getcwd(), "WORKSPACE"),
        "APP_NAME": "AGiXT",
        "EMAIL_SERVER": "",
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "%(asctime)s | %(levelname)s | %(message)s",
        "UVICORN_WORKERS": 10,
        "DATABASE_TYPE": "sqlite",
        "DATABASE_NAME": "models/agixt",
        "DATABASE_USER": "postgres",
        "DATABASE_PASSWORD": "postgres",
        "DATABASE_HOST": "localhost",
        "DATABASE_PORT": "5432",
        "DEFAULT_USER": "user",
        "DISABLED_EXTENSIONS": "",
        "DISABLED_PROVIDERS": "",
        "REGISTRATION_DISABLED": "false",
        "CREATE_AGENT_ON_REGISTER": "true",
        "CREATE_AGIXT_AGENT": "true",
        "SEED_DATA": "true",
        "TRAINING_URLS": "",
        "ENABLED_COMMANDS": "",
        "AGIXT_HEALTH_URL": "http://localhost:7437/health",
        "HEALTH_CHECK_INTERVAL": "15",
        "HEALTH_CHECK_TIMEOUT": "10",
        "HEALTH_CHECK_MAX_FAILURES": "3",
        "RESTART_COOLDOWN": "60",
        "INITIAL_STARTUP_DELAY": "180",
        "EXTENSIONS_HUB": "",
        "EXTENSIONS_HUB_TOKEN": "",
        "PAYMENT_WALLET_ADDRESS": "BavSLrHbzcq5QdY491Fo6uC9rqvfKgszVcj661zqJogS",
        "PAYMENT_SOLANA_RPC_URL": "https://api.mainnet-beta.solana.com",
        # Token-based billing configuration
        "TOKEN_PRICE_PER_MILLION_USD": "0.00",
        "MIN_TOKEN_TOPUP_USD": "10.00",
        "LOW_BALANCE_WARNING_THRESHOLD": "10000000",  # 10M tokens
        "TOKEN_WARNING_INCREMENT": "1000000",  # 1M tokens
        "TZ": "UTC",
        "SUPERADMIN_EMAIL": "josh@devxt.com",
    }
    if var_name == "MAGIC_LINK_URL":
        var_name = "APP_URI"
    if default_value != "":
        default_values[var_name] = default_value
    default_value = default_values[var_name] if var_name in default_values else ""

    # For infrastructure settings, always use environment variables only
    if var_name in _ENV_ONLY_SETTINGS:
        return os.getenv(var_name, default_value)

    # First check environment variable (highest priority - allows overrides)
    env_value = os.getenv(var_name)
    if env_value is not None and env_value != "":
        return env_value

    # Then check server config cache (database values from shared cache)
    # Try to load cache if not already loaded (handles multi-worker scenarios)
    if not _server_config_cache_loaded:
        load_server_config_cache()

    if _server_config_cache_loaded:
        try:
            from SharedCache import shared_cache

            cached = shared_cache.get(_SERVER_CONFIG_CACHE_KEY)

            # If cache expired (returned None), try to reload it
            if cached is None:
                _server_config_cache_loaded = False
                load_server_config_cache()
                cached = shared_cache.get(_SERVER_CONFIG_CACHE_KEY)

            if cached is not None and var_name in cached:
                cached_value = cached.get(var_name)
                if cached_value is not None and cached_value != "":
                    return cached_value
        except Exception:
            pass

    # Fall back to default value
    return default_value


def get_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(text))
    return num_tokens


def get_data_size_kb(data) -> int:
    """
    Calculate the size of any data in kilobytes.

    Args:
        data: Any data type (dict, list, str, int, json, etc.)

    Returns:
        int: Size in KB, rounded to the nearest whole number
    """
    if isinstance(data, (dict, list)):
        data_str = json.dumps(data)
    else:
        data_str = str(data)

    size_bytes = len(data_str.encode("utf-8"))
    size_kb = round(size_bytes / 1024)
    return size_kb


def get_default_agent_settings():
    """
    Get default agent settings.

    NOTE: Provider API keys and provider-specific settings are intentionally NOT included here.
    Provider settings should be resolved at inference time from the hierarchy:
    1. Server extension settings (admin configured)
    2. Company agent settings (company admin configured)
    3. User preferences (if applicable)

    This ensures that when server admins change API keys, all agents automatically use
    the new keys without needing to update each agent's settings individually.
    """
    agent_settings = {
        # Non-provider settings that should be stored at agent level
        "SMARTEST_PROVIDER": "anthropic",
        "mode": "prompt",
        "prompt_name": "Think About It",
        "prompt_category": "Default",
        "analyze_user_input": False,
        "websearch": False,
        "websearch_depth": 2,
        "WEBSEARCH_TIMEOUT": 0,
        "persona": getenv("AGENT_PERSONA"),
        "tts": False,
        # Complexity scaling settings for inference-time compute
        "complexity_scaling_enabled": True,
        "thinking_budget_enabled": True,
        "thinking_budget_override": None,  # Optional int to bypass auto-calculation
        "answer_review_enabled": True,  # Two-phase answer for high complexity
        "planning_phase_enabled": True,  # Mandatory to-do list for multi-step tasks
    }
    for key in list(agent_settings.keys()):
        if agent_settings[key] == "":
            del agent_settings[key]
    return agent_settings


def get_default_agent_enabled_commands():
    enabled_commands = getenv("ENABLED_COMMANDS")
    if enabled_commands == "":
        return {}
    commands = {}
    if "," in enabled_commands:
        enabled_commands = enabled_commands.split(",")
    else:
        enabled_commands = [enabled_commands]
    for command in enabled_commands:
        commands[command] = True
    return commands


def get_default_training_urls():
    training_urls = getenv("TRAINING_URLS")
    if training_urls == "":
        return []
    if "," in training_urls:
        training_urls = training_urls.split(",")
    else:
        training_urls = [training_urls]
    return training_urls


def get_default_agent():
    return {
        "settings": get_default_agent_settings(),
        "commands": get_default_agent_enabled_commands(),
        "training_urls": get_default_training_urls(),
    }


def get_agixt_training_urls():
    return [
        "https://josh-xt.github.io/AGiXT/",
        "https://josh-xt.github.io/AGiXT/1-Getting%20started/3-Examples.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/0-Core%20Concepts.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/01-Processes%20and%20Frameworks.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/02-Providers.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/03-Agents.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/04-Chat%20Completions.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/05-Extension%20Commands.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/06-Prompts.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/07-Chains.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/07-Conversations.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/09-Agent%20Training.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/10-Agent%20Interactions.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/0-ezLocalai.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/1-Anthropic%20Claude.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/2-Azure%20OpenAI.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/3-Google.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/4-GPT4Free.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/5-Hugging%20Face.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/6-OpenAI.html",
        "https://josh-xt.github.io/AGiXT/4-Authentication/microsoft.html",
        "https://josh-xt.github.io/AGiXT/4-Authentication/google.html",
    ]


def get_output_url(path: str):
    agixt_uri = getenv("AGIXT_URI")
    new_path = path.split("/WORKSPACE/")[-1]
    return f"{agixt_uri}/{new_path}"


DEFAULT_USER = str(getenv("DEFAULT_USER")).lower()
DEFAULT_SETTINGS = get_default_agent_settings()
