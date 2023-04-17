import json
from typing import List
from Commands import Commands
from Config import Config
from AgentLLM import AgentLLM

CFG = Config()

class code_evaluation(Commands):
    def __init__(self):
        self.commands = {
            "Evaluate Code": self.evaluate_code,
            "Improve Code": self.improve_code,
            "Write Tests": self.write_tests
        }

    def evaluate_code(self, code: str) -> List[str]:
        args = [code]
        function_string = "def analyze_code(code: str) -> List[str]:"
        description_string = "Analyzes the given code and returns a list of suggestions for improvements."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AgentLLM().run(prompt, commands_enabled=False)
    
    def improve_code(self, suggestions: List[str], code: str) -> str:
        args = [json.dumps(suggestions), code]
        function_string = "def generate_improved_code(suggestions: List[str], code: str) -> str:"
        description_string = "Improves the provided code based on the suggestions provided, making no other changes."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AgentLLM().run(prompt, commands_enabled=False)
    
    def write_tests(code: str, focus: List[str]) -> str:
        args = [code, json.dumps(focus)]
        function_string = "def create_test_cases(code: str, focus: Optional[str] = None) -> str:"
        description_string = "Generates test cases for the existing code, focusing on specific areas if required."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AgentLLM().run(prompt, commands_enabled=False)