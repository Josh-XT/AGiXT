import importlib
import subprocess
import importlib.metadata
import glob
import os
import inspect
import logging
import time
from Globals import getenv

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
DISABLED_PROVIDERS = getenv("DISABLED_PROVIDERS").replace(" ", "").split(",")

# Cache for AI provider extensions to avoid expensive file system scanning
_ai_provider_cache = None
_ai_provider_cache_time = 0
_AI_PROVIDER_CACHE_TTL = 300  # 5 minutes cache TTL


def _get_ai_provider_extensions(use_cache=True):
    """Get all extension files with CATEGORY = 'AI Provider'

    Args:
        use_cache: If True, use cached results when available (default: True)
    """
    global _ai_provider_cache, _ai_provider_cache_time

    # Return cached result if valid
    if use_cache and _ai_provider_cache is not None:
        if (time.time() - _ai_provider_cache_time) < _AI_PROVIDER_CACHE_TTL:
            return _ai_provider_cache

    from ExtensionsHub import (
        find_extension_files,
        import_extension_module,
        get_extension_class_name,
    )

    ai_providers = {}
    extension_files = find_extension_files()

    for ext_file in extension_files:
        filename = os.path.basename(ext_file)
        module = import_extension_module(ext_file)
        if module is None:
            continue

        class_name = get_extension_class_name(filename)
        if not hasattr(module, class_name):
            continue

        try:
            provider_class = getattr(module, class_name)
            if (
                hasattr(provider_class, "CATEGORY")
                and provider_class.CATEGORY == "AI Provider"
            ):
                provider_name = class_name.lower()
                if provider_name not in DISABLED_PROVIDERS:
                    ai_providers[provider_name] = {
                        "module": module,
                        "class": provider_class,
                        "file": ext_file,
                    }
        except Exception as e:
            logging.debug(f"Could not inspect extension {filename}: {e}")

    # Update cache
    _ai_provider_cache = ai_providers
    _ai_provider_cache_time = time.time()

    return ai_providers


def invalidate_provider_cache():
    """Invalidate the provider cache, forcing a refresh on next access"""
    global _ai_provider_cache, _ai_provider_cache_time
    _ai_provider_cache = None
    _ai_provider_cache_time = 0


def get_providers():
    """Get list of all available AI provider names"""
    return list(_get_ai_provider_extensions().keys())


def get_provider_options(provider_name):
    """Get the configuration options/settings for a provider"""
    provider_name = provider_name.lower()
    options = {}
    if provider_name in DISABLED_PROVIDERS:
        return {}

    try:
        providers = _get_ai_provider_extensions()
        if provider_name not in providers:
            return {"provider": provider_name}

        provider_class = providers[provider_name]["class"]
        signature = inspect.signature(provider_class.__init__)
        options = {
            name: (
                param.default if param.default is not inspect.Parameter.empty else None
            )
            for name, param in signature.parameters.items()
            if name != "self" and name != "kwargs"
        }
    except Exception as e:
        logging.debug(f"Could not get options for provider {provider_name}: {e}")

    if "provider" not in options:
        options["provider"] = provider_name
    return options


def get_providers_with_settings():
    """Get all providers with their settings"""
    providers = []
    for provider in get_providers():
        providers.append(
            {
                provider: get_provider_options(provider_name=provider),
            }
        )
    return providers


def get_providers_with_details():
    """Get detailed information about all providers"""
    providers = {}
    ai_providers = _get_ai_provider_extensions()

    for provider_name, provider_info in ai_providers.items():
        if provider_name == "rotation":
            continue
        if provider_name == "gpt4free":
            continue
        if provider_name == "default":
            continue

        try:
            provider_class = provider_info["class"]
            provider_settings = get_provider_options(provider_name=provider_name)
            if "provider" in provider_settings:
                del provider_settings["provider"]

            documentation = provider_class.__doc__ if provider_class.__doc__ else ""
            documentation = documentation.strip()
            if documentation.startswith("\n"):
                documentation = documentation[1:]
            if documentation.endswith("\n"):
                documentation = documentation[:-1]
            documentation = documentation.strip()

            providers.update(
                {
                    provider_name: {
                        "name": (
                            provider_class.friendly_name
                            if hasattr(provider_class, "friendly_name")
                            else provider_name.capitalize()
                        ),
                        "description": documentation,
                        "services": (
                            provider_class.services()
                            if hasattr(provider_class, "services")
                            else (
                                provider_class.SERVICES
                                if hasattr(provider_class, "SERVICES")
                                else []
                            )
                        ),
                        "settings": provider_settings,
                    }
                }
            )
        except Exception as e:
            logging.debug(f"Could not get details for provider {provider_name}: {e}")

    return providers


def get_provider_services(provider_name="openai"):
    """Get the services supported by a provider"""
    try:
        providers = _get_ai_provider_extensions()
        if provider_name not in providers:
            return []

        provider_class = providers[provider_name]["class"]
        if hasattr(provider_class, "services"):
            return provider_class.services()
        elif hasattr(provider_class, "SERVICES"):
            return provider_class.SERVICES
        return []
    except Exception as e:
        logging.debug(f"Could not get services for provider {provider_name}: {e}")
        return []


def get_providers_by_service(service="llm"):
    """Get all providers that support a given service"""
    providers = []
    if service in [
        "llm",
        "tts",
        "image",
        "embeddings",
        "transcription",
        "translation",
        "vision",
    ]:
        try:
            for provider in get_providers():
                if provider in DISABLED_PROVIDERS:
                    continue
                if service in get_provider_services(provider):
                    providers.append(provider)
            return providers
        except:
            return []
    return []
