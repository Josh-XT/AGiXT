from Chain import Chain
from Extensions import Extensions
from Interactions import Interactions
from Prompts import Prompts
import datetime
import json
import requests


class agixt_chain(Extensions):
    def __init__(self, **kwargs):
        self.chains = Chain().get_chains()
        self.commands = {
            "Create Task Chain": self.create_task_chain,
            "Create Smart Task Chain": self.create_smart_task_chain,
            "Generate Extension from OpenAPI": self.generate_openapi_chain,
        }
        if self.chains != None:
            for chain in self.chains:
                if "name" in chain:
                    self.commands.update(
                        {f"Run Chain: {chain['name']}": self.run_chain}
                    )

    async def create_task_chain(
        self,
        agent: str,
        primary_objective: str,
        numbered_list_of_tasks: str,
        short_chain_description: str,
    ):
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        task_list = numbered_list_of_tasks.split("\n")
        task_list = [
            task.lstrip("0123456789.")  # Strip leading digits and periods
            for task in task_list
            if task
            and task[0]
            in [str(i) for i in range(10)]  # Check for task starting with a digit (0-9)
        ]
        chain_name = f"AI Generated Task - {short_chain_description} - {timestamp}"
        chain = Chain()
        chain.add_chain(chain_name=chain_name)
        i = 1
        for task in task_list:
            chain.add_chain_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Prompt",
                prompt={
                    "prompt_name": "Task Execution",
                    "primary_objective": primary_objective,
                    "task": task,
                    "websearch": True,
                    "websearch_depth": 3,
                    "context_results": 5,
                },
            )
            i += 1
        return chain_name

    async def create_smart_task_chain(
        self,
        agent: str,
        primary_objective: str,
        numbered_list_of_tasks: str,
        short_chain_description: str,
    ):
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        task_list = numbered_list_of_tasks.split("\n")
        task_list = [
            task.lstrip("0123456789.")  # Strip leading digits and periods
            for task in task_list
            if task
            and task[0]
            in [str(i) for i in range(10)]  # Check for task starting with a digit (0-9)
        ]
        chain_name = (
            f"AI Generated Smart Task - {short_chain_description} - {timestamp}"
        )
        chain = Chain()
        chain.add_chain(chain_name=chain_name)
        i = 1
        for task in task_list:
            chain.add_chain_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Chain",
                prompt={
                    "chain": "Smart Instruct",
                    "input": f"Primary Objective: {primary_objective}\nYour Task: {task}",
                },
            )
            i += 1
        return chain_name

    async def run_chain(self, chain: str = "", input: str = ""):
        await Interactions(agent_name="").run_chain(chain_name=chain, user_input=input)
        return "Chain started successfully."

    def parse_openapi(self, data):
        endpoints = []
        if "paths" in data:
            for path, path_info in data["paths"].items():
                for method, method_info in path_info.items():
                    endpoint_info = {
                        "endpoint": path,
                        "method": method.upper(),
                        "summary": method_info.get("summary", ""),
                        "parameters": [],
                        "responses": [],
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
        chain = Chain()
        chain.add_chain(chain_name=chain_name)
        i = 1
        for endpoint in endpoints:
            i += 1
            chain.add_chain_step(
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
            chain.add_chain_step(
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
            chain.add_chain_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Command",
                prompt={
                    "command_name": "Indent String for Python Code",
                    "string": "{STEP" + str(i - 1) + "}",
                },
            )
            i += 1
            chain.add_chain_step(
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
        chain.add_chain_step(
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
        chain.add_chain_step(
            chain_name=chain_name,
            agent_name=agent,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Generate Commands Dictionary",
                "python_file_content": "{STEP" + str(i - 1) + "}",
            },
        )
        new_extension = Prompts().get_prompt(prompt_name="New Extension Format")
        new_extension.format(
            extension_name=extension_name,
            extension_commands="{STEP" + str(i) + "}",
            extension_functions="{STEP" + str(i - 1) + "}",
            auth_type=auth_type,
        )
        i += 1
        chain.add_chain_step(
            chain_name=chain_name,
            agent_name=agent,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Write to File",
                "filename": f"{extension_name}.py",
                "content": new_extension,
            },
        )
        return chain_name
