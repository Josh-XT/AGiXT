from Extensions import Extensions
from Config import Config
from Chain import Chain
from AGiXT import AGiXT
import json
import os
from typing import List, Optional


class agixt_agent(Extensions):
    def __init__(self, **kwargs):
        agents = Config().get_agents()
        self.chains = Chain().get_chains()
        self.commands = {
            "Evaluate Code": self.evaluate_code,
            "Analyze Pull Request": self.analyze_pull_request,
            "Perform Automated Testing": self.perform_automated_testing,
            "Run CI-CD Pipeline": self.run_ci_cd_pipeline,
            "Improve Code": self.improve_code,
            "Write Tests": self.write_tests,
            "Create a new command": self.create_command,
        }
        if agents != None:
            for agent in agents:
                if "name" in agent:
                    name = f" AI Agent {agent['name']}"
                    self.commands.update(
                        {f"Ask{name}": self.ask, f"Instruct{name}": self.instruct}
                    )
        if self.chains != None:
            for chain in self.chains:
                if "name" in chain:
                    self.commands.update(
                        {f"Run Chain: {chain['name']}": self.run_chain}
                    )

    def command_exists(self, file_name: str) -> bool:
        return os.path.exists(f"commands/{file_name}.py")

    def create_command(
        self, function_description: str, agent_name: str = "AGiXT"
    ) -> List[str]:
        with open(f"prompts/Create New Command.txt", "r") as f:
            prompt = f.read()
        prompt = prompt.replace("{{NEW_FUNCTION_DESCRIPTION}}", function_description)
        response = AGiXT(agent_name).run(prompt)
        file_name = response.split("class ")[1].split("(")[0]
        code = code.replace("```", "")

        if not self.command_exists(file_name):
            with open(f"commands/{file_name}.py", "w") as f:
                f.write(code)
            return f"Created new command: {file_name}."
        else:
            return f"Command {file_name} already exists. No changes were made."

    def evaluate_code(self, code: str, agent_name: str = "AGiXT") -> List[str]:
        args = [code]
        function_string = "def analyze_code(code: str) -> List[str]:"
        description_string = "Analyzes the given code and returns a list of suggestions for improvements."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AGiXT(agent_name).run(prompt)

    def analyze_pull_request(self, pr_url: str, agent_name: str = "AGiXT") -> List[str]:
        args = [pr_url]
        function_string = "def analyze_pr(pr_url: str) -> List[str]:"
        description_string = "Analyzes the given pull request and returns a list of suggestions for improvements."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AGiXT(agent_name).run(prompt)

    def perform_automated_testing(
        self, test_url: str, agent_name: str = "AGiXT"
    ) -> List[str]:
        args = [test_url]
        function_string = "def perform_testing(test_url: str) -> List[str]:"
        description_string = "Performs automated testing using AI-driven tools and returns a list of test results."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AGiXT(agent_name).run(prompt)

    def improve_code(
        self, suggestions: List[str], code: str, agent_name: str = "AGiXT"
    ) -> str:
        args = [json.dumps(suggestions), code]
        function_string = (
            "def generate_improved_code(suggestions: List[str], code: str) -> str:"
        )
        description_string = "Improves the provided code based on the suggestions provided, making no other changes."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AGiXT(agent_name).run(prompt)

    def write_tests(
        self,
        code: str,
        focus: Optional[List[str]] = None,
        agent_name: str = "AGiXT",
    ) -> str:
        args = [code, json.dumps(focus) if focus else "None"]
        function_string = "def create_test_cases(code: str, focus: Optional[List[str]] = None) -> str:"
        description_string = "Generates test cases for the existing code, focusing on specific areas if required."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AGiXT(agent_name).run(prompt)

    def run_ci_cd_pipeline(self, repo_url: str, agent_name: str = "AGiXT") -> str:
        args = [repo_url]
        function_string = "def run_pipeline(repo_url: str) -> str:"
        description_string = (
            "Runs the entire CI/CD pipeline for the given repository URL."
        )
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AGiXT(agent_name).run(prompt)

    def run_chain(self, chain_name):
        Chain().run_chain(chain_name)
        return "Chain started successfully."

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
