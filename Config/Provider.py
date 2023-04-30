import os
import glob
from Config import Config


class Provider(Config):
    def get_providers(self):
        providers = []
        for provider in glob.glob("provider/*.py"):
            if "__init__.py" not in provider:
                providers.append(os.path.splitext(os.path.basename(provider))[0])
        return providers
