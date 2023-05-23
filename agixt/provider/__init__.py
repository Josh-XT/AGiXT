import importlib
import subprocess
import pkg_resources
import glob
import os
import inspect


def get_provider_options(provider_name):
    module = importlib.import_module(f"provider.{provider_name}")
    provider_class = getattr(module, f"{provider_name.capitalize()}Provider")
    signature = inspect.signature(provider_class.__init__)
    options = [
        param for param in signature.parameters if param != "self" and param != "kwargs"
    ]
    return options


class Provider:
    def __init__(self, name, **kwargs):
        try:
            module = importlib.import_module(f"provider.{name}")
            provider_class = getattr(module, f"{name.capitalize()}Provider")
            self.instance = provider_class(**kwargs)

            # Install the requirements if any
            self.install_requirements()

        except (ModuleNotFoundError, AttributeError) as e:
            raise AttributeError(f"module {__name__} has no attribute {name}") from e

    def __getattr__(self, attr):
        return getattr(self.instance, attr)

    def get_providers(self):
        providers = []
        for provider in glob.glob("provider/*.py"):
            if "__init__.py" not in provider:
                providers.append(os.path.splitext(os.path.basename(provider))[0])
        return providers

    def install_requirements(self):
        requirements = getattr(self.instance, "requirements", [])
        installed_packages = {pkg.key: pkg.version for pkg in pkg_resources.working_set}
        for requirement in requirements:
            if requirement.lower() not in installed_packages:
                subprocess.run(["pip", "install", requirement], check=True)


def __getattr__(name):
    return Provider(name)


def max_tokens_ceiling(ai_model: str):
    """Generates the max token limit for a given model"""

    # https://huggingface.co/OpenAssistant/oasst-sft-6-llama-30b-xor
    if ai_model == "openassistant":
        return 2000
    # https://huggingface.co/bigcode/starcoderbase
    elif ai_model == "starcoderbase":
        return 8192
    elif ai_model == "default":
        return 2000
    else:
        return 999999999
