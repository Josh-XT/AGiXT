import os
import glob
import logging

from Agent import get_agents_basefolder

logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)


class Config:
    def get_providers(self):
        providers = []
        for provider in glob.glob("provider/*.py"):
            if "__init__.py" not in provider:
                providers.append(os.path.splitext(os.path.basename(provider))[0])
        return providers

    def get_agents(self):
        agents_dir = get_agents_basefolder()
        if not os.path.exists(agents_dir):
            os.makedirs(agents_dir)

        agents = []
        for item in os.listdir(agents_dir):
            if os.path.isdir(os.path.join(agents_dir, item)):
              agents.append(item)
              
        output = []
        if agents:
            for agent in agents:
                try:
                    agent_instance = self.agent_instances[agent]
                    status = agent_instance.get_status()
                except:
                    status = False
                output.append({"name": agent, "status": status})
        return output
