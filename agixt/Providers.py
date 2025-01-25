import importlib
import subprocess
import pkg_resources
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


def get_providers():
    providers = []
    for provider in glob.glob("providers/*.py"):
        provider_name = os.path.splitext(os.path.basename(provider))[0]
        if provider_name not in DISABLED_PROVIDERS and "__init__.py" not in provider:
            providers.append(provider_name)
    return providers


def get_provider_options(provider_name):
    provider_name = provider_name.lower()
    options = {}
    if provider_name in DISABLED_PROVIDERS:
        return {}
    logging.info(f"Getting options for provider: {provider_name}")
    # This will keep transformers from being installed unless needed.
    try:
        module = importlib.import_module(f"providers.{provider_name}")
        provider_class = getattr(module, f"{provider_name.capitalize()}Provider")
        signature = inspect.signature(provider_class.__init__)
        options = {
            name: (
                param.default if param.default is not inspect.Parameter.empty else None
            )
            for name, param in signature.parameters.items()
            if name != "self" and name != "kwargs"
        }
    except:
        pass
    if "provider" not in options:
        options["provider"] = provider_name
    return options


def get_providers_with_settings():
    providers = []
    for provider in get_providers():
        providers.append(
            {
                provider: get_provider_options(provider_name=provider),
            }
        )
    return providers


def get_providers_with_details():
    providers = {}
    for provider in get_providers():
        if provider == "rotation":
            continue
        if provider == "gpt4free":
            continue
        if provider == "default":
            continue
        module = importlib.import_module(f"providers.{provider}")
        provider_class = getattr(module, f"{provider.capitalize()}Provider")
        provider_settings = get_provider_options(provider_name=provider)
        if "provider" in provider_settings:
            del provider_settings["provider"]
        documentation = provider_class.__doc__ if provider_class.__doc__ else ""
        # Remove first and last lines if they're \n or whitespce
        documentation = documentation.strip()
        if documentation.startswith("\n"):
            documentation = documentation[1:]
        if documentation.endswith("\n"):
            documentation = documentation[:-1]
        documentation = documentation.strip()
        providers.update(
            {
                provider: {
                    "name": (
                        provider_class.friendly_name
                        if hasattr(provider_class, "friendly_name")
                        else provider.capitalize()
                    ),
                    "description": documentation,
                    "services": (
                        provider_class.services()
                        if hasattr(provider_class, "services")
                        else []
                    ),
                    "settings": provider_settings,
                }
            }
        )
    return providers


def get_provider_services(provider_name="openai"):
    try:
        module = importlib.import_module(f"providers.{provider_name}")
        provider_class = getattr(module, f"{provider_name.capitalize()}Provider")
        return provider_class.services()
    except:
        return []


def get_providers_by_service(service="llm"):
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
    def __init__(self, name, ApiClient=None, **kwargs):
        if name in DISABLED_PROVIDERS:
            raise AttributeError(f"module {__name__} has no attribute {name}")
        try:
            kwargs["ApiClient"] = ApiClient
            module = importlib.import_module(f"providers.{name}")
            provider_class = getattr(module, f"{name.capitalize()}Provider")
            self.instance = provider_class(**kwargs)

            # Install the requirements if any
            # self.install_requirements()

        except (ModuleNotFoundError, AttributeError) as e:
            if name != None and name != "None" and not str(name).startswith("__"):
                logging.info(f"Error loading provider: {name}")

    def __getattr__(self, attr):
        return getattr(self.instance, attr)

    def install_requirements(self):
        requirements = getattr(self.instance, "requirements", [])
        installed_packages = {pkg.key: pkg.version for pkg in pkg_resources.working_set}
        for requirement in requirements:
            if requirement.lower() not in installed_packages:
                subprocess.run(["pip", "install", requirement], check=True)


def __getattr__(name, ApiClient=None):
    return Providers(name=name, ApiClient=ApiClient)
