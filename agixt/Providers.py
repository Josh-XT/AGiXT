import importlib
import subprocess
import pkg_resources
import glob
import os
import inspect
from dotenv import load_dotenv

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
        options["provider"] = provider_name
    except:
        options = {
            "provider": provider_name,
            "MAX_TOKENS": 4096,
            "AI_MODEL": "gpt-3.5-turbo",
            "AI_TOP_P": 0.7,
            "AI_TEMPERATURE": 0.7,
            "WAIT_BETWEEN_REQUESTS": 1,
            "WAIT_AFTER_FAILURE": 3,
        }
        if provider_name == "petal" or provider_name == "pipeline":
            options["HUGGINGFACE_API_KEY"] = ""
    return options


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
