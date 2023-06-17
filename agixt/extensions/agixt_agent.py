from Extensions import Extensions
from Agent import get_agents
from Interactions import Interactions
import json
import os
from typing import List, Optional
from transformers import BlipProcessor, BlipForConditionalGeneration
import torch
from PIL import Image
import requests
import subprocess


class agixt_agent(Extensions):
    def __init__(self, **kwargs):
        agents = get_agents()
        self.commands = {
            "Evaluate Code": self.evaluate_code,
            "Analyze Pull Request": self.analyze_pull_request,
            "Perform Automated Testing": self.perform_automated_testing,
            "Run CI-CD Pipeline": self.run_ci_cd_pipeline,
            "Improve Code": self.improve_code,
            "Write Tests": self.write_tests,
            "Create a new command": self.create_command,
            "Describe Image": self.describe_image,
            "Execute Python Code": self.execute_python_code,
            "Get Python Code from Response": self.get_python_code_from_response,
        }
        if agents != None:
            for agent in agents:
                if "name" in agent:
                    name = f" AI Agent {agent['name']}"
                    self.commands.update(
                        {
                            f"Ask{name}": self.ask,
                            f"Instruct{name}": self.instruct,
                        }
                    )

    def command_exists(self, file_name: str) -> bool:
        return os.path.exists(f"commands/{file_name}.py")

    async def create_command(
        self, function_description: str, agent: str = "AGiXT"
    ) -> List[str]:
        with open(f"prompts/Create New Command.txt", "r") as f:
            prompt = f.read()
        prompt = prompt.replace("{{NEW_FUNCTION_DESCRIPTION}}", function_description)
        response = await Interactions(agent_name=agent).run(user_input=prompt)
        file_name = response.split("class ")[1].split("(")[0]
        code = code.replace("```", "")

        if not self.command_exists(file_name):
            with open(f"commands/{file_name}.py", "w") as f:
                f.write(code)
            return f"Created new command: {file_name}."
        else:
            return f"Command {file_name} already exists. No changes were made."

    async def evaluate_code(self, code: str, agent: str = "AGiXT") -> List[str]:
        args = [code]
        function_string = "def analyze_code(code: str) -> List[str]:"
        description_string = "Analyzes the given code and returns a list of suggestions for improvements."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return await Interactions(agent_name=agent).run(user_input=prompt)

    async def analyze_pull_request(
        self, pr_url: str, agent: str = "AGiXT"
    ) -> List[str]:
        args = [pr_url]
        function_string = "def analyze_pr(pr_url: str) -> List[str]:"
        description_string = "Analyzes the given pull request and returns a list of suggestions for improvements."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return await Interactions(agent_name=agent).run(user_input=prompt)

    async def perform_automated_testing(
        self, test_url: str, agent: str = "AGiXT"
    ) -> List[str]:
        args = [test_url]
        function_string = "def perform_testing(test_url: str) -> List[str]:"
        description_string = "Performs automated testing using AI-driven tools and returns a list of test results."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return await Interactions(agent_name=agent).run(user_input=prompt)

    async def improve_code(
        self, suggestions: List[str], code: str, agent: str = "AGiXT"
    ) -> str:
        args = [json.dumps(suggestions), code]
        function_string = (
            "def generate_improved_code(suggestions: List[str], code: str) -> str:"
        )
        description_string = "Improves the provided code based on the suggestions provided, making no other changes."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return await Interactions(agent_name=agent).run(user_input=prompt)

    async def write_tests(
        self,
        code: str,
        focus: Optional[List[str]] = None,
        agent: str = "AGiXT",
    ) -> str:
        args = [code, json.dumps(focus) if focus else "None"]
        function_string = "def create_test_cases(code: str, focus: Optional[List[str]] = None) -> str:"
        description_string = "Generates test cases for the existing code, focusing on specific areas if required."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return await Interactions(agent_name=agent).run(user_input=prompt)

    async def run_ci_cd_pipeline(self, repo_url: str, agent: str = "AGiXT") -> str:
        args = [repo_url]
        function_string = "def run_pipeline(repo_url: str) -> str:"
        description_string = (
            "Runs the entire CI/CD pipeline for the given repository URL."
        )
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return await Interactions(agent_name=agent).run(user_input=prompt)

    async def ask(self, user_input: str, agent: str = "AGiXT") -> str:
        response = await Interactions(agent_name=agent).run(
            user_input=user_input, prompt="chat", websearch=True, websearch_depth=4
        )
        return response

    async def instruct(self, user_input: str, agent: str = "AGiXT") -> str:
        response = await Interactions(agent_name=agent).run(
            user_input=user_input, prompt="instruct", websearch=True, websearch_depth=8
        )
        return response

    async def describe_image(self, image_url):
        """
        Describe an image using FuseCap.
        """
        if image_url:
            processor = BlipProcessor.from_pretrained("noamrot/FuseCap")
            model = BlipForConditionalGeneration.from_pretrained("noamrot/FuseCap")

            # Define the device to run the model on (CPU or GPU)

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model.to(device)
            raw_image = Image.open(requests.get(image_url, stream=True).raw).convert(
                "RGB"
            )

            # Generate a caption for the image using FuseCap
            text = "a picture of "
            inputs = processor(raw_image, text, return_tensors="pt").to(device)
            out = model.generate(max_length=20, temperature=0.7, **inputs, num_beams=3)
            caption = processor.decode(out[0], skip_special_tokens=True)

            # Return the caption
            return caption

    async def get_python_code_from_response(self, response: str):
        if "```python" in response:
            response = response.split("```python")[1].split("```")[0]
        return response

    async def execute_python_code(self, code: str) -> str:
        code = await self.get_python_code_from_response(code)
        # Create the WORKSPACE directory if it doesn't exist
        workspace_dir = os.path.join(os.getcwd(), "WORKSPACE")
        os.makedirs(workspace_dir, exist_ok=True)

        # Create a temporary Python file in the WORKSPACE directory
        temp_file = os.path.join(workspace_dir, "temp.py")
        with open(temp_file, "w") as f:
            f.write(code)

        try:
            # Execute the Python script and capture its output
            response = subprocess.check_output(
                ["python", temp_file], stderr=subprocess.STDOUT
            )
        except subprocess.CalledProcessError as e:
            # If the script raises an exception, return the error message
            response = e.output

        # Delete the temporary Python file
        os.remove(temp_file)

        # Decode the output from bytes to string and return it
        return response.decode("utf-8")
