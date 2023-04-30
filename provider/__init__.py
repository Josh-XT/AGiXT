import importlib
import subprocess
import pkg_resources
import glob
import os


class Provider:
    def __init__(self, name, **kwargs):
        try:
            module = importlib.import_module(f".{name}", package=__name__)
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
