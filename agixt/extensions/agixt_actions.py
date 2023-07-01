import datetime
import json
import requests
import os
import torch
import subprocess
from typing import List
from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image
from Extensions import Extensions
from agixtsdk import AGiXTSDK
from Chain import Chain

ApiClient = AGiXTSDK(base_uri="http://localhost:7437")


class agixt_actions(Extensions):
    def __init__(self, **kwargs):
        self.chains = Chain().get_chains()
        # agents = ApiClient.get_agents()
        self.commands = {
            "Create Task Chain": self.create_task_chain,
            "Generate Extension from OpenAPI": self.generate_openapi_chain,
            "Generate Agent Helper Chain": self.generate_helper_chain,
            "Ask for Help or Further Clarification to Complete Task": self.ask_for_help,
            "Create a new command": self.create_command,
            "Describe Image": self.describe_image,
            "Execute Python Code": self.execute_python_code,
            "Get Python Code from Response": self.get_python_code_from_response,
        }
        if self.chains != None:
            for chain in self.chains:
                if "name" in chain:
                    self.commands.update(
                        {f"Run Chain: {chain['name']}": self.run_chain}
                    )
        """
        if agents != None:
            for agent in agents:
                if "name" in agent:
                    name = f" AI Agent {agent['name']}"
                    self.commands.update(
                        {
                            f"Ask{name}": self.ask,
                            f"Instruct{name}": self.instruct,
                        }
                    )"""

    async def create_task_chain(
        self,
        agent: str,
        primary_objective: str,
        numbered_list_of_tasks: str,
        short_chain_description: str,
        smart_chain: bool = False,
        researching: bool = False,
    ):
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        task_list = numbered_list_of_tasks.split("\n")
        new_task_list = []
        current_task = ""
        for task in task_list:
            if task and task[0] in [
                str(i) for i in range(10)
            ]:  # Check for task starting with a digit (0-9)
                if current_task:  # If there's a current task, add it to the list
                    new_task_list.append(
                        current_task.lstrip("0123456789.")
                    )  # Strip leading digits and periods
                current_task = task  # Start a new current task
            else:
                current_task += (
                    "\n" + task
                )  # If the line doesn't start with a number, it's a subtask - add it to the current task

        if current_task:  # Add the last task if it exists
            if "\n\n" in current_task:
                current_task = current_task.split("\n\n")[0]
            new_task_list.append(
                current_task.lstrip("0123456789.")
            )  # Strip leading digits and periods

        task_list = new_task_list

        chain_name = f"AI Generated Task - {short_chain_description} - {timestamp}"
        ApiClient.add_chain(chain_name=chain_name)
        i = 1
        for task in task_list:
            ApiClient.add_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Chain",
                prompt={
                    "chain": "Smart Prompt",
                    "input": f"Primary Objective to keep in mind while working on the task: {primary_objective} \nThe only task to complete to move towards the objective: {task}",
                },
            )
            i += 1
            if smart_chain:
                if researching:
                    step_chain = "Smart Instruct"
                else:
                    step_chain = "Smart Instruct - No Research"
                ApiClient.add_step(
                    chain_name=chain_name,
                    agent_name=agent,
                    step_number=i,
                    prompt_type="Chain",
                    prompt={
                        "chain": step_chain,
                        "input": "{STEP" + str(i - 1) + "}",
                    },
                )
            else:
                ApiClient.add_step(
                    chain_name=chain_name,
                    agent_name=agent,
                    step_number=i,
                    prompt_type="Prompt",
                    prompt={
                        "prompt_name": "Task Execution",
                        "introduction": "{STEP" + str(i - 1) + "}",
                        "websearch": researching,
                        "websearch_depth": 3,
                        "context_results": 5,
                    },
                )
            i += 1
        return chain_name

    async def run_chain(self, chain: str = "", input: str = ""):
        await ApiClient.run_chain(chain_name=chain, user_input=input)
        return "Chain started successfully."

    def parse_openapi(self, data):
        endpoints = []
        schemas = data.get("components", {}).get(
            "schemas", {}
        )  # get the global schemas

        def resolve_schema(ref):
            # remove the '#/components/schemas/' part
            schema_name = ref.replace("#/components/schemas/", "")
            return schemas.get(schema_name, {})

        if "paths" in data:
            for path, path_info in data["paths"].items():
                for method, method_info in path_info.items():
                    endpoint_info = {
                        "endpoint": path,
                        "method": method.upper(),
                        "summary": method_info.get("summary", ""),
                        "parameters": [],
                        "responses": [],
                        "requestBody": {},
                    }
                    if "parameters" in method_info:
                        for param in method_info["parameters"]:
                            param_info = {
                                "name": param.get("name", ""),
                                "in": param.get("in", ""),
                                "description": param.get("description", ""),
                                "required": param.get("required", False),
                                "type": param.get("schema", {}).get("type", "")
                                if "schema" in param
                                else "",
                            }
                            endpoint_info["parameters"].append(param_info)
                    if "requestBody" in method_info:
                        request_body = method_info["requestBody"]
                        content = request_body.get("content", {})
                        for content_type, content_info in content.items():
                            if "$ref" in content_info.get("schema", {}):
                                # resolve the reference into the actual schema
                                content_info["schema"] = resolve_schema(
                                    content_info["schema"]["$ref"]
                                )
                        endpoint_info["requestBody"] = {
                            "description": request_body.get("description", ""),
                            "required": request_body.get("required", False),
                            "content": content,
                        }
                    if "responses" in method_info:
                        for response, response_info in method_info["responses"].items():
                            response_info = {
                                "code": response,
                                "description": response_info.get("description", ""),
                            }
                            endpoint_info["responses"].append(response_info)
                    endpoints.append(endpoint_info)
        return endpoints

    def get_auth_type(self, openapi_data):
        # The "components" section contains the security schemes
        if (
            "components" in openapi_data
            and "securitySchemes" in openapi_data["components"]
        ):
            security_schemes = openapi_data["components"]["securitySchemes"]

            # Iterate over all security schemes
            for scheme_name, scheme_details in security_schemes.items():
                # The "type" field specifies the type of the scheme
                if "type" in scheme_details and scheme_details["type"] == "http":
                    # The "scheme" field provides more specific information
                    if "scheme" in scheme_details:
                        return scheme_details["scheme"]
        return "basic"

    async def generate_openapi_chain(
        self, agent: str, extension_name: str, openapi_json_url: str
    ):
        # Experimental currently.
        openapi_str = requests.get(openapi_json_url).text
        openapi_data = json.loads(openapi_str)
        endpoints = self.parse_openapi(data=openapi_data)
        auth_type = self.get_auth_type(openapi_data=openapi_data)
        extension_name = extension_name.lower().replace(" ", "_")
        chain_name = f"OpenAPI to Python Chain - {extension_name}"
        ApiClient.add_chain(chain_name=chain_name)
        i = 0
        for endpoint in endpoints:
            i += 1
            ApiClient.add_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Prompt",
                prompt={
                    "prompt_name": "Convert OpenAPI Endpoint",
                    "api_endpoint_info": f"{endpoint}",
                },
            )
            i += 1
            ApiClient.add_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Command",
                prompt={
                    "command_name": "Get Python Code from Response",
                    "response": "{STEP" + str(i - 1) + "}",
                },
            )
            i += 1
            ApiClient.add_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Command",
                prompt={
                    "command_name": "Indent String for Python Code",
                    "string": "{STEP" + str(i - 1) + "}",
                    "indents": 1,
                },
            )
            i += 1
            ApiClient.add_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Command",
                prompt={
                    "command_name": "Append to File",
                    "filename": f"{extension_name}_functions.py",
                    "text": "\n\n{STEP" + str(i - 1) + "}",
                },
            )
        i += 1
        ApiClient.add_step(
            chain_name=chain_name,
            agent_name=agent,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Read File",
                "filename": f"{extension_name}_functions.py",
            },
        )
        i += 1
        ApiClient.add_step(
            chain_name=chain_name,
            agent_name=agent,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Generate Commands Dictionary",
                "python_file_content": "{STEP" + str(i - 1) + "}",
            },
        )
        new_extension = ApiClient.get_prompt(prompt_name="New Extension Format")
        new_extension = new_extension.replace("{extension_name}", extension_name)
        new_extension = new_extension.replace("extension_commands", "STEP" + str(i))
        new_extension = new_extension.replace(
            "extension_functions", "STEP" + str(i - 1)
        )
        new_extension = new_extension.replace("{auth_type}", auth_type)
        i += 1
        ApiClient.add_step(
            chain_name=chain_name,
            agent_name=agent,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Write to File",
                "filename": f"{extension_name}.py",
                "text": new_extension,
            },
        )
        return chain_name

    async def generate_helper_chain(self, user_agent, helper_agent, task_in_question):
        chain_name = f"Help Chain - {user_agent} to {helper_agent}"
        ApiClient.add_chain(chain_name=chain_name)
        i = 1
        ApiClient.add_step(
            chain_name=chain_name,
            agent_name=user_agent,
            step_number=i,
            prompt_type="Prompt",
            prompt={
                "prompt_name": "Get Clarification",
                "task_in_question": task_in_question,
            },
        )
        i += 1
        ApiClient.add_step(
            chain_name=chain_name,
            agent_name=helper_agent,
            step_number=i,
            prompt_type="Prompt",
            prompt={
                "prompt_name": "Ask for Help",
                "task_in_question": task_in_question,
                "question": "{STEP" + str(i - 1) + "}",
            },
        )
        # run the chain and return the result
        return chain_name

    async def ask_for_help(self, your_agent_name, your_task):
        return ApiClient.run_chain(
            chain_name="Ask Helper Agent for Help",
            user_input=your_task,
            agent_name=your_agent_name,
            all_responses=False,
            from_step=1,
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
