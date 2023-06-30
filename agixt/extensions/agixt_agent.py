from Extensions import Extensions
from Agent import get_agents
import os
from typing import List
from transformers import BlipProcessor, BlipForConditionalGeneration
import torch
from PIL import Image
import requests
import subprocess
from agixtsdk import AGiXTSDK

base_uri = "http://localhost:7437"
ApiClient = AGiXTSDK(base_uri=base_uri)


class agixt_agent(Extensions):
    def __init__(self, **kwargs):
        agents = get_agents()
        self.commands = {
            "Create a new command": self.create_command,
            "Describe Image": self.describe_image,
            "Execute Python Code": self.execute_python_code,
            "Get Python Code from Response": self.get_python_code_from_response,
            "Ask for Help or Further Clarification to Complete Task": self.ask_for_help,
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

    async def create_command(
        self, function_description: str, agent: str = "AGiXT"
    ) -> List[str]:
        try:
            return ApiClient.run_chain(
                chain_name="Create New Command",
                user_input=function_description,
                agent_name=agent,
                all_responses=False,
                from_step=1,
            )
        except Exception as e:
            return f"Unable to create command: {e}"

    async def ask_for_help(
        self,
        agent: str,
        your_primary_objective: str,
        your_current_task: str,
        your_detailed_question: str,
    ) -> str:
        """
        Ask for Help or Further Clarification to Complete Task
        """
        return await ApiClient.prompt_agent(
            agent_name=agent,
            prompt_name="Ask for Help",
            prompt_args={
                "user_input": your_primary_objective,
                "question": your_detailed_question,
                "task_in_question": your_current_task,
            },
        )

    async def ask(self, user_input: str, agent: str = "AGiXT") -> str:
        response = ApiClient.prompt_agent(
            agent_name=agent,
            prompt_name="Chat",
            prompt_args={
                "user_input": user_input,
                "websearch": True,
                "websearch_depth": 3,
            },
        )
        return response

    async def instruct(self, user_input: str, agent: str = "AGiXT") -> str:
        response = ApiClient.prompt_agent(
            agent_name=agent,
            prompt_name="instruct",
            prompt_args={
                "user_input": user_input,
                "websearch": True,
                "websearch_depth": 3,
            },
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
