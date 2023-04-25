from Commands import Commands
from Config import Config
from AgentLLM import AgentLLM

CFG = Config()

class work_with_ai(Commands):
    def __init__(self):
        agents = CFG.get_agents()
        self.commands = {}
        for agent in agents:
            name = f" AI Agent {agent.name}"
            self.commands.update({f"Ask{name}": self.ask, f"Instruct{name}": self.instruct})

    def ask(self, prompt: str) -> str:
        response = AgentLLM().run(prompt, commands_enabled=False)
        return response
    
    def instruct(self, prompt: str) -> str:
        response = AgentLLM().run(prompt, commands_enabled=True)
        return response