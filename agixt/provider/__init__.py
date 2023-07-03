import importlib
import subprocess
import pkg_resources
import glob
import os
import inspect
from DBConnection import (
    session,
    Provider as ProviderModel,
    ProviderSetting,
)


def import_providers():
    providers = get_providers()
    existing_providers = session.query(ProviderModel).all()
    existing_provider_names = [provider.name for provider in existing_providers]

    for provider in existing_providers:
        if provider.name not in providers:
            session.delete(provider)

    for provider_name in providers:
        provider_options = get_provider_options(provider_name)

        provider = (
            session.query(ProviderModel).filter_by(name=provider_name).one_or_none()
        )

        if provider:
            print(f"Updating provider: {provider_name}")
        else:
            provider = ProviderModel(name=provider_name)
            session.add(provider)
            existing_provider_names.append(provider_name)
            print(f"Adding provider: {provider_name}")

        for option_name, option_value in provider_options.items():
            provider_setting = (
                session.query(ProviderSetting)
                .filter_by(provider_id=provider.id, name=option_name)
                .one_or_none()
            )
            if provider_setting:
                provider_setting.value = option_value
                print(
                    f"Updating provider setting: {option_name} for provider: {provider_name}"
                )
            else:
                provider_setting = ProviderSetting(
                    provider_id=provider.id,
                    name=option_name,
                    value=option_value,
                )
                session.add(provider_setting)
                print(
                    f"Adding provider setting: {option_name} for provider: {provider_name}"
                )

    session.commit()


def get_providers():
    providers = []
    for provider in glob.glob("provider/*.py"):
        if "__init__.py" not in provider:
            providers.append(os.path.splitext(os.path.basename(provider))[0])
    return providers


def get_provider_options(provider_name):
    provider_name = provider_name.lower()
    module = importlib.import_module(f"provider.{provider_name}")
    provider_class = getattr(module, f"{provider_name.capitalize()}Provider")
    signature = inspect.signature(provider_class.__init__)
    options = {
        name: param.default if param.default is not inspect.Parameter.empty else None
        for name, param in signature.parameters.items()
        if name != "self" and name != "kwargs"
    }
    options["provider"] = provider_name
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
