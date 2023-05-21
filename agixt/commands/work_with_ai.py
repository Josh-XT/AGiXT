from Commands import Commands
from Config import Config
from AGiXT import AGiXT


class work_with_ai(Commands):
    def __init__(self):
        agents = Config().get_agents()
        self.commands = {}
        if agents != None:
            for agent in agents:
                if "name" in agent:
                    name = f" AI Agent {agent['name']}"
                    self.commands.update(
                        {f"Ask{name}": self.ask, f"Instruct{name}": self.instruct}
                    )

    def ask(self, prompt: str, agent_name: str = "AGiXT") -> str:
        response = AGiXT(agent_name).run(
            prompt, prompt="chat", websearch=True, websearch_depth=4
        )
        return response

    def instruct(self, prompt: str, agent_name: str = "AGiXT") -> str:
        response = AGiXT(agent_name).run(
            task=prompt, prompt="instruct", websearch=True, websearch_depth=8
        )
        return response
