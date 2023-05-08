import os
from typing import List
from Commands import Commands
from Config import Config
from AgentLLM import AgentLLM

CFG = Config()


class create_new_command(Commands):
    def __init__(self):
        self.commands = {"Create a new command": self.create_command}

    def command_exists(self, file_name: str) -> bool:
        return os.path.exists(f"commands/{file_name}.py")

    def create_command(
        self, function_description: str, agent_name: str = "Agent-LLM"
    ) -> List[str]:
        args = [function_description]
        # Get prompt from model-prompts/{CFG.AI_MODEL}/script.txt
        with open(f"model-prompts/{CFG.AI_MODEL}/script.txt", "r") as f:
            prompt = f.read()
        prompt = prompt.replace("{{NEW_FUNCTION_DESCRIPTION}}", function_description)
        response = AgentLLM(agent_name).run(prompt)
        file_name = response.split("class ")[1].split("(")[0]
        code = code.replace("```", "")

        if not self.command_exists(file_name):
            with open(f"commands/{file_name}.py", "w") as f:
                f.write(code)
            return f"Created new command: {file_name}."
        else:
            return f"Command {file_name} already exists. No changes were made."
