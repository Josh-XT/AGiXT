import os
import glob
import logging

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
        agents_dir = "agents"
        if not os.path.exists(agents_dir):
            os.makedirs(agents_dir)
        agents = [
            dir_name
            for dir_name in os.listdir(agents_dir)
            if os.path.isdir(os.path.join(agents_dir, dir_name))
        ]
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
