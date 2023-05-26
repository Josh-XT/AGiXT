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
        memories_dir = "agents"
        if not os.path.exists(memories_dir):
            os.makedirs(memories_dir)
        agents = []
        for file in os.listdir(memories_dir):
            if file.endswith(".yaml"):
                agents.append(file.replace(".yaml", ""))
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
