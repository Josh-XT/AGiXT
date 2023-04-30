import importlib
import subprocess


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
        for requirement in requirements:
            subprocess.run(["pip", "install", requirement], check=True)


def __getattr__(name):
    return Provider(name)
