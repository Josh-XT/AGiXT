import datetime
import json
import uuid
import requests
import os
import re
from typing import List, Type
from pydantic import BaseModel
from Extensions import Extensions
from ApiClient import Chain
import logging
import docker
import asyncio
from agixtsdk import AGiXTSDK
from Globals import getenv


def install_docker_image():
    docker_image = "joshxt/safeexecute:main"
    client = docker.from_env()
    try:
        client.images.get(docker_image)
        logging.info(f"Image '{docker_image}' found locally")
    except:
        logging.info(f"Installing docker image '{docker_image}' from Docker Hub")
        client.images.pull(docker_image)
        logging.info(f"Image '{docker_image}' installed")
    return client


def execute_python_code(
    code: str, agent_id: str = "", conversation_id: str = ""
) -> str:
    docker_image = "joshxt/safeexecute:main"
    docker_working_dir = f"/agixt/WORKSPACE/{agent_id}/{conversation_id}"
    os.makedirs(docker_working_dir, exist_ok=True)
    host_working_dir = os.getenv("WORKING_DIRECTORY", "/agixt/WORKSPACE")
    host_working_dir = os.path.join(host_working_dir, agent_id, conversation_id)
    # Check if there are any package requirements in the code to install
    package_requirements = re.findall(r"pip install (.*)", code)
    # Strip out python code blocks if they exist in the code
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    # check if ``` is on the first or last line and remove it
    if code.startswith("```"):
        code = code.split("\n", 1)[1]
    if code.endswith("\n```python"):
        code = code.rsplit("\n", 1)[0]
    if code.endswith("```"):
        code = code.rsplit("\n", 1)[0]
    temp_file_name = f"{str(uuid.uuid4())}.py"
    temp_file = os.path.join(docker_working_dir, temp_file_name)
    logging.info(f"Writing Python code to temporary file: {temp_file}")
    with open(temp_file, "w") as f:
        f.write(code)
    logging.info(
        f"Temporary file written. Checking if the file exists: {os.path.exists(temp_file)}"
    )
    try:
        client = install_docker_image()
        # Install the required packages in the container
        for package in package_requirements:
            try:
                logging.info(f"Installing package '{package}' in container")
                client.containers.run(
                    docker_image,
                    f"pip install {package}",
                    volumes={
                        host_working_dir: {"bind": docker_working_dir, "mode": "rw"}
                    },
                    working_dir=docker_working_dir,
                    stderr=True,
                    stdout=True,
                    remove=True,
                )
            except Exception as e:
                logging.error(f"Error installing package '{package}': {str(e)}")
                return f"Error: {str(e)}"
        # Run the Python code in the container
        container = client.containers.run(
            docker_image,
            f"python {os.path.join(docker_working_dir, temp_file_name)}",
            volumes={host_working_dir: {"bind": docker_working_dir, "mode": "rw"}},
            working_dir=docker_working_dir,
            stderr=True,
            stdout=True,
            detach=True,
        )
        # Wait for the container to finish and capture the logs
        result = container.wait()
        logs = container.logs().decode("utf-8")
        container.remove()
        if result["StatusCode"] != 0:
            logging.error(f"Error executing Python code: {logs}")
            return f"Error: {logs}"
        logging.info(f"Python code executed successfully. Logs: {logs}")
        logs = str(logs)
        if logs.endswith("\n"):
            logs = logs[:-1]
        return logs
    except Exception as e:
        logging.error(f"Error executing Python code: {str(e)}")
        return f"Error: {str(e)}"


def extract_markdown_from_message(message):
    match = re.search(r"```(.*)```", message, re.DOTALL)
    return match.group(1).strip() if match else ""


def parse_mindmap(mindmap):
    markdown_text = extract_markdown_from_message(mindmap)
    if not markdown_text:
        markdown_text = mindmap
    markdown_text = markdown_text.strip()
    lines = markdown_text.split("\n")

    root = {}
    current_path = [root]

    for line in lines:
        node = line.strip().lstrip("- ").replace("**", "")
        indent_level = (len(line) - len(line.lstrip())) // 4

        if indent_level < len(current_path) - 1:
            current_path = current_path[: indent_level + 1]

        current_dict = current_path[-1]
        if isinstance(current_dict, list):
            current_dict = current_path[-2][
                current_dict[0]
            ]  # go one level up if current dict is a list

        if node not in current_dict:
            current_dict[node] = {}

        current_path.append(current_dict[node])

    # Function to convert dictionary leaf nodes into lists
    def convert_to_lists(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, dict):
                    if all(isinstance(val, dict) and not val for val in value.values()):
                        # filter out any empty keys
                        node[key] = [k for k in value.keys() if k]
                    else:
                        convert_to_lists(value)

    convert_to_lists(root)
    return root


class agixt_actions(Extensions):
    """
    The AGiXT Actions extension contains commands that allow the AGiXT Agents to work with other agents and use pre-built chains to complete tasks.
    """

    def __init__(self, **kwargs):
        self.commands = {
            "Create Task Chain": self.create_task_chain,
            "Generate Extension from OpenAPI": self.generate_openapi_chain,
            "Generate Agent Helper Chain": self.generate_helper_chain,
            "Ask for Help or Further Clarification to Complete Task": self.ask_for_help,
            "Execute Python Code": self.execute_python_code_internal,
            "Get Python Code from Response": self.get_python_code_from_response,
            "Get Mindmap for task to break it down": self.get_mindmap,
            "Store information in my long term memory": self.store_long_term_memory,
            "Research on arXiv": self.search_arxiv,
            "Read GitHub Repository into long term memory": self.read_github_repository,
            "Read Website Content into long term memory": self.write_website_to_memory,
            "Read non-image file content into long term memory": self.read_file_content,
            "Make CSV Code Block": self.make_csv_code_block,
            "Get CSV Preview": self.get_csv_preview,
            "Get CSV Preview Text": self.get_csv_preview_text,
            "Strip CSV Data from Code Block": self.get_csv_from_response,
            "Convert a string to a Pydantic model": self.convert_string_to_pydantic_model,
            "Disable Command": self.disable_command,
            "Plan Multistep Task": self.plan_multistep_task,
            "Replace init in File": self.replace_init_in_file,
        }
        user = kwargs["user"] if "user" in kwargs else "user"
        for chain in Chain(user=user).get_chains():
            self.commands[chain] = self.run_chain
        self.command_name = (
            kwargs["command_name"] if "command_name" in kwargs else "Smart Prompt"
        )
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        os.makedirs(self.WORKING_DIRECTORY, exist_ok=True)
        self.conversation_id = (
            kwargs["conversation_id"] if "conversation_id" in kwargs else ""
        )

        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else AGiXTSDK(
                base_uri=getenv("AGIXT_URI"),
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
            )
        )
        self.failures = 0

    async def read_file_content(self, file_path: str):
        """
        Read the content of a file and store it in long term memory

        Args:
        file_path (str): The path to the file

        Returns:
        str: Success message
        """
        with open(file_path, "r") as f:
            file_content = f.read()
        filename = os.path.basename(file_path)
        return self.ApiClient.learn_file(
            agent_name=self.agent_name,
            file_name=filename,
            file_content=file_content,
            collection_number="0",
        )

    async def write_website_to_memory(self, url: str):
        """
        Read the content of a website and store it in long term memory

        Args:
        url (str): The URL of the website

        Returns:
        str: Success message
        """
        return self.ApiClient.learn_url(
            agent_name=self.agent_name,
            url=url,
            collection_number="0",
        )

    async def store_long_term_memory(
        self, input: str, data_to_correlate_with_input: str
    ):
        """
        Store information in long term memory

        Args:
        input (str): The user input
        data_to_correlate_with_input (str): The data to correlate with the user input in long term memory, useful for feedback or remembering important information for later

        Returns:
        str: Success message
        """
        return self.ApiClient.learn_text(
            agent_name=self.agent_name,
            user_input=input,
            text=data_to_correlate_with_input,
        )

    async def search_arxiv(self, query: str, max_articles: int = 5):
        """
        Search for articles on arXiv, read into long term memory

        Args:
        query (str): The search query
        max_articles (int): The maximum number of articles to read

        Returns:
        str: Success message
        """
        return self.ApiClient.learn_arxiv(
            query=query,
            article_ids=None,
            max_articles=max_articles,
            collection_number="0",
        )

    async def read_github_repository(self, repository_url: str):
        """
        Read the content of a GitHub repository and store it in long term memory

        Args:
        repository_url (str): The URL of the GitHub repository

        Returns:
        str: Success message
        """
        return self.ApiClient.learn_github_repo(
            agent_name=self.agent_name,
            github_repo=repository_url,
            use_agent_settings=True,
            collection_number="0",
        )

    async def disable_command(self, command_name: str):
        """
        Disable a command

        Args:
        command_name (str): The name of the command to disable

        Returns:
        str: Success message
        """
        return self.ApiClient.update_agent_commands(
            agent_name=self.agent_name, commands={command_name: False}
        )

    async def plan_multistep_task(self, assumed_scope_of_work: str):
        """
        Plan a multi-step task

        Args:
        assumed_scope_of_work (str): The assumed scope of work

        Returns:
        str: The name of the new chain
        """
        user_input = assumed_scope_of_work
        new_chain = self.ApiClient.plan_task(
            agent_name=self.agent_name,
            user_input=user_input,
            websearch=True,
            websearch_depth=3,
            conversation_name=self.conversation_name,
            log_user_input=False,
            log_output=False,
            enable_new_command=True,
        )
        return new_chain["message"]

    async def create_task_chain(
        self,
        primary_objective: str,
        numbered_list_of_tasks: str,
        short_chain_description: str,
        smart_chain: bool = False,
        researching: bool = False,
    ):
        """
        Create a task chain from a numbered list of tasks

        Args:
        primary_objective (str): The primary objective to keep in mind while working on the task
        numbered_list_of_tasks (str): The numbered list of tasks to complete
        short_chain_description (str): A short description of the chain
        smart_chain (bool): Whether to create a smart chain
        researching (bool): Whether to include web research in the chain

        Returns:
        str: The name of the created chain
        """
        logging.info(f"[TASK CHAIN GENERATOR] Primary Objective: {primary_objective}")
        logging.info(
            f"[TASK CHAIN GENERATOR] Numbered List of Tasks: {numbered_list_of_tasks}"
        )
        logging.info(
            f"[TASK CHAIN GENERATOR] Short Chain Description: {short_chain_description}"
        )
        logging.info(f"[TASK CHAIN GENERATOR] Smart Chain: {smart_chain}")
        logging.info(f"[TASK CHAIN GENERATOR] Researching: {researching}")
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        task_list = numbered_list_of_tasks.split("\n")
        new_task_list = []
        current_task = ""
        for task in task_list:
            if task and task[0].isdigit():
                if current_task:
                    new_task_list.append(current_task.lstrip("0123456789."))
                current_task = task
            else:
                current_task += "\n" + task
        logging.info(f"[TASK CHAIN GENERATOR] Task List: {new_task_list}")

        if current_task:
            new_task_list.append(current_task.lstrip("0123456789."))

        task_list = new_task_list
        string_task_list = "\n".join(task_list)
        chain_name = f"AI Generated Task - {short_chain_description} - {timestamp}"
        logging.info(f"[TASK CHAIN GENERATOR] New Chain Name: {chain_name}")
        self.ApiClient.add_chain(chain_name=chain_name)
        # RUN Smart Prompt chain on the task list
        i = 1
        for task in task_list:
            response = self.ApiClient.run_chain(
                chain_name="Smart Prompt",
                agent_name=self.agent_name,
                user_input=f"Task List:\n{string_task_list}\nPrimary Objective to keep in mind while working on the task: {primary_objective} \nAll tasks on the list are being planned and completed separately. Assume all steps prior have been completed. The only task to complete to move towards the objective: {task}",
            )
            logging.info(
                f"[TASK CHAIN GENERATOR] Smart Prompt for Step {i}: {response}"
            )
            i += 1
            if smart_chain:
                if researching:
                    step_chain = "Smart Instruct"
                else:
                    step_chain = "Smart Instruct - No Research"
                self.ApiClient.add_step(
                    chain_name=chain_name,
                    agent_name=self.agent_name,
                    step_number=i,
                    prompt_type="Chain",
                    prompt={
                        "chain": step_chain,
                        "input": response,
                    },
                )
                logging.info(f"[TASK CHAIN GENERATOR] Added step {i} to SMART chain")
            else:
                self.ApiClient.add_step(
                    chain_name=chain_name,
                    agent_name=self.agent_name,
                    step_number=i,
                    prompt_type="Prompt",
                    prompt={
                        "prompt_name": "Think About It",
                        "user_input": response,
                        "websearch": researching,
                        "websearch_depth": 3,
                    },
                )
                logging.info(f"[TASK CHAIN GENERATOR] Added step {i} to NORMAL chain")
            i += 1
        return chain_name

    async def run_chain(
        self, input_for_task: str = "", start_from_step_number: int = 1
    ):
        """
        Run a chain

        Args:
        input_for_task (str): The input for the task

        Returns:
        str: The response from the chain
        """
        try:
            step_number = int(start_from_step_number)
        except:
            step_number = 1
        response = await self.ApiClient.run_chain(
            chain_name=self.command_name,
            user_input=input_for_task,
            agent_name=self.agent_name,
            all_responses=False,
            from_step=step_number,
            chain_args={
                "conversation_name": self.conversation_name,
            },
        )
        return response

    def parse_openapi(self, data):
        """
        Parse OpenAPI data to extract endpoints

        Args:
        data (dict): The OpenAPI data

        Returns:
        list: The list of endpoints
        """
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
                                "type": (
                                    param.get("schema", {}).get("type", "")
                                    if "schema" in param
                                    else ""
                                ),
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
        """
        Get the authentication type from the OpenAPI data

        Args:
        openapi_data (dict): The OpenAPI data

        Returns:
        str: The authentication type
        """
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
        return "Not provided from OpenAPI spec"

    async def replace_init_in_file(self, filename: str, new_init: str):
        """
        Replace the __init__ method in a file

        Args:
        filename (str): The filename
        new_init (str): The new __init__ method

        Returns:
        str: The new file content
        """
        with open(filename, "r") as f:
            file_content = f.read()
        new_init = new_init.replace("    def __init__", "def __init__")
        new_file_content = re.sub(
            r"def __init__\((.*?)\):.*?async def",
            new_init,
            file_content,
        )
        with open(filename, "w") as f:
            f.write(new_file_content)
        new_path = os.path.join(os.getcwd(), "WORKSPACE", "extensions", filename)
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        with open(new_path, "w") as f:
            f.write(new_file_content)
        agixt_uri = getenv("AGIXT_URI")
        return f"{agixt_uri}/outputs/extensions/{filename}"

    async def generate_openapi_chain(
        self,
        extension_name: str,
        openapi_json_url: str,
        api_base_uri: str = "",
    ):
        """
        Generate an AGiXT extension from an OpenAPI JSON URL

        Args:
        extension_name (str): The name of the extension
        openapi_json_url (str): The URL of the OpenAPI JSON file
        api_base_uri (str): The base URI of the API

        Returns:
        str: The name of the created chain
        """
        # Experimental currently.
        openapi_str = requests.get(openapi_json_url).text
        openapi_data = json.loads(openapi_str)
        endpoints = self.parse_openapi(data=openapi_data)
        auth_type = self.get_auth_type(openapi_data=openapi_data)
        if api_base_uri == "":
            rules = """## Guidelines
- Respond in JSON in a markdown codeblock with the only key being `base_uri`, for example:
```json
{
    "base_uri": "https://api.example.com/v1"
}
```
"""
            response = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Chat",
                prompt_args={
                    "user_input": f"{rules}\nUsing context from the web search, please provide the base URI of the API for: {extension_name}.",
                    "websearch": True,
                    "websearch_depth": 2,
                    "analyze_user_input": False,
                    "conversation_name": self.conversation_name,
                    "log_user_input": False,
                    "log_output": False,
                    "tts": False,
                },
            )
            # Stripe the base_uri from the response
            response = response.split("```json")[1].split("```")[0].strip()
            response = response.split("```")[1].strip()
            api_base_uri = json.loads(response).get("base_uri", "")
        extension_name = extension_name.lower().replace(" ", "_")
        chain_name = f"OpenAPI to Python Chain - {extension_name}"
        chains = self.ApiClient.get_chains()
        # Check if any chain with the same name already exists, if so, delete it
        for chain in chains:
            if chain == chain_name:
                self.ApiClient.delete_chain(chain_name=chain_name)
        self.ApiClient.add_chain(chain_name=chain_name)
        i = 0
        for endpoint in endpoints:
            i += 1
            self.ApiClient.add_step(
                chain_name=chain_name,
                agent_name=self.agent_name,
                step_number=i,
                prompt_type="Prompt",
                prompt={
                    "prompt_name": "Convert OpenAPI Endpoint",
                    "api_endpoint_info": f"{endpoint}",
                },
            )
            i += 1
            self.ApiClient.add_step(
                chain_name=chain_name,
                agent_name=self.agent_name,
                step_number=i,
                prompt_type="Command",
                prompt={
                    "command_name": "Get Python Code from Response",
                    "response": "{STEP" + str(i - 1) + "}",
                },
            )
            i += 1
            self.ApiClient.add_step(
                chain_name=chain_name,
                agent_name=self.agent_name,
                step_number=i,
                prompt_type="Command",
                prompt={
                    "command_name": "Indent String for Python Code",
                    "string": "{STEP" + str(i - 1) + "}",
                    "indents": 1,
                },
            )
            i += 1
            self.ApiClient.add_step(
                chain_name=chain_name,
                agent_name=self.agent_name,
                step_number=i,
                prompt_type="Command",
                prompt={
                    "command_name": "Append to File",
                    "filename": f"{extension_name}_functions.py",
                    "text": "\n\n{STEP" + str(i - 1) + "}",
                },
            )
        i += 1
        self.ApiClient.add_step(
            chain_name=chain_name,
            agent_name=self.agent_name,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Read File",
                "filename": f"{extension_name}_functions.py",
            },
        )
        i += 1
        self.ApiClient.add_step(
            chain_name=chain_name,
            agent_name=self.agent_name,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Generate Commands Dictionary",
                "python_file_content": "{STEP" + str(i - 1) + "}",
            },
        )
        new_extension = self.ApiClient.get_prompt(prompt_name="New Extension Format")
        new_extension = new_extension.replace("{extension_name}", extension_name)
        new_extension = new_extension.replace("extension_commands", "STEP" + str(i))
        new_extension = new_extension.replace(
            "extension_functions", "STEP" + str(i - 1)
        )
        new_extension = new_extension.replace("{base_uri}", api_base_uri)
        new_extension = new_extension.replace(
            "{upper_extension_name}", extension_name.upper()
        )
        i += 1
        self.ApiClient.add_step(
            chain_name=chain_name,
            agent_name=self.agent_name,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Write to File",
                "filename": f"{extension_name}.py",
                "text": new_extension,
            },
        )
        i += 1
        self.ApiClient.add_step(
            chain_name=chain_name,
            agent_name=self.agent_name,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Read File",
                "filename": f"{extension_name}.py",
            },
        )
        i += 1
        self.ApiClient.add_step(
            chain_name=chain_name,
            agent_name=self.agent_name,
            step_number=i,
            prompt_type="Prompt",
            prompt={
                "prompt_name": "Get Auth Headers",
                "prompt_args": {
                    "extension_content": "{STEP" + str(i - 1) + "}",
                    "extension_name": extension_name,
                    "auth_type": auth_type,
                    "user_input": f"{extension_name} API authentication headers",
                    "websearch": True,
                    "websearch_depth": 2,
                    "analyze_user_input": False,
                },
            },
        )
        i += 1
        self.ApiClient.add_step(
            chain_name=chain_name,
            agent_name=self.agent_name,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Indent String for Python Code",
                "string": "{STEP" + str(i - 1) + "}",
                "indents": 1,
            },
        )
        i += 1
        self.ApiClient.add_step(
            chain_name=chain_name,
            agent_name=self.agent_name,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Replace init in File",
                "filename": f"{extension_name}.py",
                "new_init": "{STEP" + str(i - 1) + "}",
            },
        )
        return chain_name

    async def generate_helper_chain(self, user_agent, helper_agent, task_in_question):
        """
        Generate a helper chain for an agent

        Args:
        user_agent (str): The user agent
        helper_agent (str): The helper agent
        task_in_question (str): The task in question

        Returns:
        str: The name of the created chain
        """
        chain_name = f"Help Chain - {user_agent} to {helper_agent}"
        self.ApiClient.add_chain(chain_name=chain_name)
        i = 1
        self.ApiClient.add_step(
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
        self.ApiClient.add_step(
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
        """
        Ask for help from a helper agent

        Args:
        your_agent_name (str): Your agent name
        your_task (str): Your task

        Returns:
        str: The response from the helper agent
        """
        return self.ApiClient.run_chain(
            chain_name="Ask Helper Agent for Help",
            user_input=your_task,
            agent_name=your_agent_name,
            all_responses=False,
            from_step=1,
            chain_args={
                "conversation_name": self.conversation_name,
            },
        )

    async def ask(self, user_input: str) -> str:
        """
        Ask a question

        Args:
        user_input (str): The user input

        Returns:
        str: The response to the question
        """
        response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Chat",
            prompt_args={
                "user_input": user_input,
                "websearch": True,
                "websearch_depth": 3,
                "conversation_name": self.conversation_name,
            },
        )
        return response

    async def instruct(self, user_input: str) -> str:
        """
        Instruct the agent

        Args:
        user_input (str): The user input

        Returns:
        str: The response to the instruction
        """
        response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="instruct",
            prompt_args={
                "user_input": user_input,
                "websearch": True,
                "websearch_depth": 3,
                "conversation_name": self.conversation_name,
            },
        )
        return response

    async def get_python_code_from_response(self, response: str):
        """
        Get the Python code from the response

        Args:
        response (str): The response

        Returns:
        str: The Python code
        """
        if "```python" in response:
            response = response.split("```python")[1].split("```")[0]
        return response

    async def execute_python_code_internal(self, code: str, text: str = "") -> str:
        """
        Execute Python code

        Args:
        code (str): The Python code
        text (str): The text

        Returns:
        str: The result of the Python code
        """
        if text:
            csv_content_header = text.split("\n")[0]
            # Remove any trailing spaces from any headers
            csv_headers = [header.strip() for header in csv_content_header.split(",")]
            # Replace the first line with the comma separated headers
            text = ",".join(csv_headers) + "\n" + "\n".join(text.split("\n")[1:])
            filename = "data.csv"
            filepath = os.path.join(self.WORKING_DIRECTORY, filename)
            with open(filepath, "w") as f:
                f.write(text)
        agents = self.ApiClient.get_agents()
        agent_id = ""
        for agent in agents:
            if agent["name"] == self.agent_name:
                agent_id = str(agent["id"])
        execution_response = execute_python_code(
            code=code, agent_id=agent_id, conversation_id=self.conversation_id
        )
        return execution_response

    async def get_mindmap(self, task: str):
        """
        Get a mindmap for a task

        Args:
        task (str): The task

        Returns:
        dict: The mindmap
        """
        mindmap = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Mindmap",
            prompt_args={
                "user_input": task,
                "conversation_name": self.conversation_name,
            },
        )
        return parse_mindmap(mindmap=mindmap)

    async def make_csv_code_block(self, data: str) -> str:
        """
        Make a CSV code block

        Args:
        data (str): The data

        Returns:
        str: The CSV code block
        """
        if "," in data or "\n" in data:
            return f"```csv\n{data}\n```"
        return data

    async def get_csv_preview(self, filename: str):
        """
        Get a preview of a CSV file

        Args:
        filename (str): The filename

        Returns:
        str: The preview of the CSV file consisting of the first 2-5 lines
        """
        filepath = self.safe_join(base=self.WORKING_DIRECTORY, paths=filename)
        with open(filepath, "r") as f:
            lines = f.readlines()
        if len(lines) > 5:
            lines = lines[:5]
        else:
            lines = lines[:2]
        lines_string = "\n".join(lines)
        return lines_string

    async def get_csv_preview_text(self, text: str):
        """
        Get a preview of a CSV text

        Args:
        text (str): The text

        Returns:
        str: The preview of the CSV text consisting of the first 2-5 lines
        """
        lines = text.split("\n")
        if len(lines) > 5:
            lines = lines[:5]
        else:
            lines = lines[:2]
        lines_string = "\n".join(lines)
        return lines_string

    async def get_csv_from_response(self, response: str) -> str:
        """
        Get the CSV data from the response

        Args:
        response (str): The response

        Returns:
        str: The CSV data
        """
        return response.split("```csv")[1].split("```")[0]

    async def convert_llm_response_to_list(self, response):
        """
        Convert an LLM response to a list

        Args:
        response (str): The response

        Returns:
        list: The list
        """
        response = response.split("\n")
        response = [item.lstrip("0123456789.*- ") for item in response if item.lstrip()]
        response = [item for item in response if item]
        response = [item.lstrip("0123456789.*- ") for item in response]
        return response

    async def convert_questions_to_dataset(self, response):
        """
        Convert questions to a dataset

        Args:
        response (str): The response

        Returns:
        str: The dataset
        """
        questions = await self.convert_llm_response_to_list(response)
        tasks = []
        i = 0
        for question in questions:
            i += 1
            if i % 10 == 0:
                await asyncio.gather(*tasks)
                tasks = []
            task = asyncio.create_task(
                self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Basic With Memory",
                    prompt_args={
                        "user_input": question,
                        "context_results": 10,
                        "conversation_name": self.conversation_name,
                    },
                )
            )
            tasks.append(task)

    async def convert_string_to_pydantic_model(
        self, input_string: str, output_model: Type[BaseModel]
    ):
        """
        Convert a string to a Pydantic model

        Args:
        input_string (str): The input string
        output_model (Type[BaseModel]): The output model

        Returns:
        Type[BaseModel]: The Pydantic model
        """
        fields = output_model.model_fields
        field_descriptions = [f"{field}: {fields[field]}" for field in fields]
        schema = "\n".join(field_descriptions)
        response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Convert to JSON",
            prompt_args={
                "user_input": input_string,
                "schema": schema,
                "conversation_name": "AGiXT Terminal",
            },
        )
        response = str(response).split("```json")[1].split("```")[0].strip()
        try:
            response = json.loads(response)
            return output_model(**response)
        except:
            self.failures += 1
            logging.warning(f"Failed to convert response, the response was: {response}")
            logging.info(f"[{self.failures}/3] Retrying conversion")
            if self.failures < 3:
                return await self.convert_string_to_pydantic_model(
                    input_string=input_string, output_model=output_model
                )
            else:
                logging.error(
                    "Failed to convert response after 3 attempts, returning empty string."
                )
                return ""
