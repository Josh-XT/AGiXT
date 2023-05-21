import json
from typing import List, Optional
from Commands import Commands
from AGiXT import AGiXT


class cicd(Commands):
    def __init__(self, **kwargs):
        self.commands = {
            "Evaluate Code": self.evaluate_code,
            "Analyze Pull Request": self.analyze_pull_request,
            "Perform Automated Testing": self.perform_automated_testing,
            "Run CI-CD Pipeline": self.run_ci_cd_pipeline,
            "Improve Code": self.improve_code,
            "Write Tests": self.write_tests,
        }

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
