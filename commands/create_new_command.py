import os
import subprocess
from git import Repo
from typing import List
from Commands import Commands
from Config import Config
from AgentLLM import AgentLLM

CFG = Config()

class create_new_command(Commands):
    def __init__(self):
        self.commands = {
            "Create a new command": self.create_command
        }

    def git_pull(self) -> None:
        repo = Repo('.')
        origin = repo.remote(name='origin')
        origin.pull()

    def command_exists(self, file_name: str) -> bool:
        return os.path.exists(f"commands/{file_name}.py")

    def create_pull_request(self, file_name: str) -> None:
        repo = Repo('.')
        repo.git.add(f"commands/{file_name}.py")
        repo.git.commit('-m', f"Add {file_name} command")
        origin = repo.remote(name='origin')
        origin.push()
        # You need to set up GitHub CLI and authentication to create a pull request
        subprocess.run(["gh", "pr", "create", "--title", f"Add {file_name} command", "--body", "Automatically created by Agent LLM."])

    def create_command(self, function_description: str) -> List[str]:
        args = [function_description]
        function_string = """
from typing import List
from Commands import Commands
from AgentLLM import AgentLLM

class code_evaluation(Commands):
    def __init__(self):
        self.commands = {
            "Evaluate Code": self.evaluate_code
        }

    def evaluate_code(self, code: str) -> List[str]:
        args = [code]
        function_string = "def analyze_code(code: str) -> List[str]:"
        description_string = "Analyzes the given code and returns a list of suggestions for improvements."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AgentLLM().run(prompt, commands_enabled=False)
        """
        description_string = "You write new commands for this framework. Ensure commands summaries are short and concice in self.commands. Do not explain, only provide code."
        prompt = f"{description_string}\n{function_string}```\n\nOnly respond with your `return` values. Args: {args}"
        response = AgentLLM().run(prompt, commands_enabled=False)
        
        # Git pull to update the local repository
        self.git_pull()

        file_name = response.split("class ")[1].split("(")[0]
        code = code.replace("```", "")

        if not self.command_exists(file_name):
            with open(f"commands/{file_name}.py", "w") as f:
                f.write(code)
            self.create_pull_request(file_name)
            return f"Created new command: {file_name} and submitted a pull request."
        else:
            return f"Command {file_name} already exists. No changes were made."