import importlib
import subprocess
import importlib.metadata
import glob
import os
import inspect
import logging
from Globals import getenv

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
DISABLED_PROVIDERS = getenv("DISABLED_PROVIDERS").replace(" ", "").split(",")


def _get_ai_provider_extensions():
    """Get all extension files with CATEGORY = 'AI Provider'"""
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

    return ai_providers


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


class Providers:
    """Load and instantiate an AI Provider extension by name"""

    def __init__(self, name, ApiClient=None, **kwargs):
        self.provider_name = name
        self.instance = None

        if name in DISABLED_PROVIDERS:
            raise AttributeError(f"module {__name__} has no attribute {name}")

        try:
            kwargs["ApiClient"] = ApiClient
            providers = _get_ai_provider_extensions()

            if name not in providers:
                raise ModuleNotFoundError(f"No AI Provider extension named '{name}'")

            provider_class = providers[name]["class"]
            self.instance = provider_class(**kwargs)

        except (ModuleNotFoundError, AttributeError) as e:
            if name is not None and str(name).lower() not in ["none", ""]:
                logging.error(
                    f"Error loading provider '{name}': {str(e)}",
                    exc_info=True,
                )
            raise AttributeError(f"module {__name__} has no provider '{name}'") from e
        except Exception as e:
            logging.error(
                f"Unexpected error initializing provider '{name}': {str(e)}",
                exc_info=True,
            )
            raise AttributeError(
                f"module {__name__} could not initialize provider '{name}'"
            ) from e

    def __getattr__(self, attr):
        if self.instance is None:
            raise AttributeError(
                f"Provider '{self.provider_name}' is not available; failed to initialize."
            )
        return getattr(self.instance, attr)


def __getattr__(name, ApiClient=None):
    if isinstance(name, str) and name.startswith("__"):
        raise AttributeError(f"module {__name__} has no attribute {name}")
    return Providers(name=name, ApiClient=ApiClient)
