import yaml
from pathlib import Path

class YamlMemory:
    def __init__(self, agent_name: str, memory_folder: str = "agents"):
        self.memory_folder = memory_folder
        self.memory_file = Path(memory_folder) / f"{agent_name}.yaml"
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.memory = self.load_memory()

    def load_memory(self):
        if self.memory_file.is_file():
            with open(self.memory_file, "r") as file:
                memory = yaml.safe_load(file)
                if memory is None:
                    memory = {"interactions": []}
        else:
            memory = {"interactions": []}
        return memory

    def save_memory(self):
        with open(self.memory_file, "w") as file:
            yaml.safe_dump(self.memory, file)

    def log_interaction(self, role: str, message: str):
        self.memory["interactions"].append({"role": role, "message": message})
        self.save_memory()