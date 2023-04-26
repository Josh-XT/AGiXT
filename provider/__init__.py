import importlib


class Provider:
    def __init__(self, name):
        try:
            module = importlib.import_module(f".{name}", package=__name__)
            provider_class = getattr(module, f"{name.capitalize()}Provider")
            self.instance = provider_class()
        except (ModuleNotFoundError, AttributeError) as e:
            raise AttributeError(f"module {__name__} has no attribute {name}") from e

    def __getattr__(self, attr):
        return getattr(self.instance, attr)


def __getattr__(name):
    return Provider(name)
