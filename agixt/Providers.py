import importlib
import subprocess
import pkg_resources
import glob
import os
import inspect
from dotenv import load_dotenv

DEFAULT_SETTINGS = {
    "embedder": "default",
    "AI_MODEL": "gpt-3.5-turbo",
    "AI_TEMPERATURE": "0.7",
    "AI_TOP_P": "1",
    "MAX_TOKENS": "4096",
    "helper_agent_name": "gpt4free",
    "WEBSEARCH_TIMEOUT": 0,
    "WAIT_BETWEEN_REQUESTS": 1,
    "WAIT_AFTER_FAILURE": 3,
    "stream": False,
    "WORKING_DIRECTORY": "./WORKSPACE",
    "WORKING_DIRECTORY_RESTRICTED": True,
    "AUTONOMOUS_EXECUTION": True,
}

load_dotenv()

DISABLED_PROVIDERS = os.getenv("DISABLED_PROVIDERS", "").replace(" ", "").split(",")


def get_providers():
    providers = []
    for provider in glob.glob("providers/*.py"):
        if provider in DISABLED_PROVIDERS:
            continue
        if "__init__.py" not in provider:
            providers.append(os.path.splitext(os.path.basename(provider))[0])
    return providers


def get_provider_options(provider_name):
    provider_name = provider_name.lower()
    if provider_name in DISABLED_PROVIDERS:
        return {}
    options = {
        "provider": provider_name,
        **DEFAULT_SETTINGS,
    }
    # This will keep the heavy requirements of these providers not installed unless needed.
    if provider_name == "llamacpp":
        options["MODEL_PATH"] = ""
        options["STOP_SEQUENCE"] = "</s>"
        options["GPU_LAYERS"] = 0
        options["BATCH_SIZE"] = 2048
        options["THREADS"] = 0
    elif provider_name == "pipeline":
        options["HUGGINGFACE_API_KEY"] = ""
        options["MODEL_PATH"] = ""
    elif provider_name == "palm":
        options["PALM_API_KEY"] = ""
    else:
        try:
            module = importlib.import_module(f"providers.{provider_name}")
            provider_class = getattr(module, f"{provider_name.capitalize()}Provider")
            signature = inspect.signature(provider_class.__init__)
            options = {
                name: param.default
                if param.default is not inspect.Parameter.empty
                else None
                for name, param in signature.parameters.items()
                if name != "self" and name != "kwargs"
            }
        except:
            pass
    if "prodiver" not in options:
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


class Providers:
    def __init__(self, name, **kwargs):
        if name in DISABLED_PROVIDERS:
            raise AttributeError(f"module {__name__} has no attribute {name}")
        try:
            module = importlib.import_module(f"providers.{name}")
            provider_class = getattr(module, f"{name.capitalize()}Provider")
            self.instance = provider_class(**kwargs)

            # Install the requirements if any
            self.install_requirements()

        except (ModuleNotFoundError, AttributeError) as e:
            raise AttributeError(f"module {__name__} has no attribute {name}") from e

    def __getattr__(self, attr):
        return getattr(self.instance, attr)

    def install_requirements(self):
        requirements = getattr(self.instance, "requirements", [])
        installed_packages = {pkg.key: pkg.version for pkg in pkg_resources.working_set}
        for requirement in requirements:
            if requirement.lower() not in installed_packages:
                subprocess.run(["pip", "install", requirement], check=True)


def __getattr__(name):
    return Providers(name)
