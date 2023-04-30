import importlib
import subprocess
import pkg_resources


class Provider:
    def __init__(self, name):
        try:
            module = importlib.import_module(f".{name}", package=__name__)
            provider_class = getattr(module, f"{name.capitalize()}Provider")
            self.instance = provider_class()

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
    return Provider(name)
