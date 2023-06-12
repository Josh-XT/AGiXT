from Extensions import Extensions
from Agent import get_agents
from Chain import Chain
from Interactions import Interactions
import json
import os
from typing import List, Optional
from transformers import BlipProcessor, BlipForConditionalGeneration
import torch
from PIL import Image
import requests


class agixt_agent(Extensions):
    def __init__(self, **kwargs):
        agents = get_agents()
        self.chains = Chain().get_chains()
        self.commands = {
            "Evaluate Code": self.evaluate_code,
            "Analyze Pull Request": self.analyze_pull_request,
            "Perform Automated Testing": self.perform_automated_testing,
            "Run CI-CD Pipeline": self.run_ci_cd_pipeline,
            "Improve Code": self.improve_code,
            "Write Tests": self.write_tests,
            "Create a new command": self.create_command,
            "Create Task Chain": self.create_task_chain,
            "Create Smart Task Chain": self.create_smart_task_chain,
            "Prompt AI Agent": self.prompt_agent,
            "Describe Image": self.describe_image,
        }
        if agents != None:
            for agent in agents:
                if "name" in agent:
                    name = f" AI Agent {agent['name']}"
                    self.commands.update(
                        {
                            f"Ask{name}": self.ask,
                            f"Instruct{name}": self.instruct,
                            f"Prompt{name}": self.prompt_agent,
                        }
                    )
        if self.chains != None:
            for chain in self.chains:
                if "name" in chain:
                    self.commands.update(
                        {f"Run Chain: {chain['name']}": self.run_chain}
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

    async def run_chain(self, chain_name: str = "", user_input: str = ""):
        await Chain().run_chain(chain_name=chain_name, user_input=user_input)
        return "Chain started successfully."

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

    async def prompt_agent(
        self,
        agent: str = "gpt4free",
        user_input: str = "",
        prompt_name: str = "",
        prompt_args: dict = {},
        websearch: bool = False,
        websearch_depth: int = 3,
        context_results: int = 5,
        shots: int = 1,
    ) -> str:
        ai = Interactions(agent_name=agent)
        response = await ai.run(
            user_input=user_input,
            prompt=prompt_name,
            websearch=websearch,
            websearch_depth=websearch_depth,
            context_results=context_results,
            **prompt_args,
        )
        if shots > 1:
            responses = [response]
            for shot in range(shots - 1):
                response = await ai.run(
                    user_input=user_input,
                    prompt=prompt_name,
                    context_results=context_results,
                    **prompt_args,
                )
                responses.append(response)
            # Join responses by "Response # <shot number>:" and return
            return "\n".join(
                [
                    f"Response {shot + 1}:\n{response}"
                    for shot, response in enumerate(responses)
                ]
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

    async def create_task_chain(
        self,
        agent: str,
        primary_objective: str,
        numbered_list_of_tasks: str,
        short_task_description: str,
    ):
        task_list = numbered_list_of_tasks.split("\n")
        task_list = [
            task
            for task in task_list
            if task and task[0] in [str(i) for i in range(10)]
        ]
        chain_name = f"AI Generated Task - {short_task_description}"
        chain = Chain()
        chain.add_chain(chain_name=chain_name)
        for task in task_list:
            if "task_name" in task:
                chain.add_chain_step(
                    chain_name=chain_name,
                    agent_name=agent,
                    step_number=1,
                    prompt_type="Prompt",
                    prompt={
                        "prompt_name": "Task Execution",
                        "user_input": primary_objective,
                        "task": task["task_name"],
                        "websearch": True,
                        "websearch_depth": 3,
                        "context_results": 5,
                    },
                )
        return chain_name

    async def create_smart_task_chain(
        self,
        agent: str,
        primary_objective: str,
        numbered_list_of_tasks: str,
        short_task_description: str,
    ):
        task_list = numbered_list_of_tasks.split("\n")
        task_list = [
            task
            for task in task_list
            if task and task[0] in [str(i) for i in range(10)]
        ]
        chain_name = f"AI Generated Smart Task - {short_task_description}"
        chain = Chain()
        chain.add_chain(chain_name=chain_name)
        for task in task_list:
            if "task_name" in task:
                chain.add_chain_step(
                    chain_name=chain_name,
                    agent_name=agent,
                    step_number=1,
                    prompt_type="Chain",
                    prompt={
                        "chain_name": "Smart Instruct",
                        "user_input": f"Primary Objective: {primary_objective}\nYour Task: {task['task_name']}",
                    },
                )
        return chain_name
