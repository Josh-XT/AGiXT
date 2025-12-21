import json
import uuid
import requests
import os
import re
from typing import Type
from pydantic import BaseModel
from Extensions import Extensions
import logging
from InternalClient import InternalClient
from Globals import getenv


class automation_helpers(Extensions):
    """
    The Automation Helpers extension provides utility functions for automation tasks,
    code generation, data processing, and API integration.
    """

    CATEGORY = "Development & Code"

    def __init__(self, **kwargs):
        self.commands = {
            "Generate Extension from OpenAPI": self.generate_openapi_chain,
            "Get Python Code from Response": self.get_python_code_from_response,
            "Make CSV Code Block": self.make_csv_code_block,
            "Get CSV Preview": self.get_csv_preview,
            "Get CSV Preview Text": self.get_csv_preview_text,
            "Strip CSV Data from Code Block": self.get_csv_from_response,
            "Convert a string to a Pydantic model": self.convert_string_to_pydantic_model,
            "Disable Command": self.disable_command,
            "Replace init in File": self.replace_init_in_file,
            "Use MCP Server": self.mcp_client,
            "Indent String for Python Code": self.indent_string,
            "Generate Commands Dictionary": self.generate_commands_dict,
            "Chat Completion": self.chat_completions,
        }
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
        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else InternalClient(
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
                user=kwargs.get("user"),
            )
        )
        self.api_key = kwargs["api_key"] if "api_key" in kwargs else ""
        self.failures = 0

    async def chat_completions(
        self,
        base_url,
        api_key,
        model,
        message_content,
        max_output_tokens=4096,
        temperature=0.7,
        top_p=1.0,
    ):
        """
        Chat completions using a custom API. This command is best used in an automation chain to connect agents to other agents or OpenAI style APIs.

        Args:
            base_url (str): The base URL of the API.
            api_key (str): Your API key for authentication.
            model (str): The model to use for chat completions.
            message_content (str): The content of the message.
            max_output_tokens (int, optional): The maximum number of output tokens. Defaults to 4096.
            temperature (float, optional): The temperature for sampling. Defaults to 0.7.
            top_p (float, optional): The top-p sampling parameter. Defaults to 1.0.

        Returns:
            str: The response from the API.
        """
        try:
            int(max_output_tokens)
        except:
            max_output_tokens = 4096
        try:
            float(temperature)
        except:
            temperature = 0.7
        try:
            float(top_p)
        except:
            top_p = 1.0

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        api_url = base_url.rstrip("/") + "/chat/completions"

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": message_content,
                }
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "top_p": top_p,
        }
        resp = requests.post(api_url, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def indent_string(self, string: str, indents: int = 1):
        """
        Indent a string for Python code

        Args:
        string (str): The string to indent
        indents (int): The number of indents to add

        Returns:
        str: The indented string
        """
        try:
            indents = int(indents)
        except:
            indents = 1
        if indents == 1:
            indent = "    "
        else:
            indent = "    " * indents
        lines = string.split("\n")
        indented_lines = [(indent + line) for line in lines]
        indented_string = "\n".join(indented_lines)
        return indented_string

    async def generate_commands_dict(self, python_file_content):
        """
        Generate a dictionary of commands from a Python file

        Args:
        python_file_content (str): The content of the Python file

        Returns:
        str: The dictionary of commands
        """
        function_names = re.findall(r"async def (.*?)\(", python_file_content)
        commands_dict = {
            f_name.replace("_", " "): f"self.{f_name}" for f_name in function_names
        }
        commands_string = "self.commands = {"
        for key, value in commands_dict.items():
            commands_string += f' "{key.capitalize()}": {value},'
        commands_string = commands_string[:-1]
        commands_string += "}"
        return commands_string

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
            agent_id=self.agent_id,
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

    async def disable_command(self, command_name: str):
        """
        Disable a command

        Args:
        command_name (str): The name of the command to disable

        Returns:
        str: Success message
        """
        disabled = self.ApiClient.update_agent_settings(
            agent_name=self.agent_name,
            settings={
                command_name: False,
            },
        )
        return f"Command '{command_name}' disabled."

    async def replace_init_in_file(self, filename: str, new_init: str):
        """
        Replace the __init__ method in a file

        Args:
        filename (str): The filename
        new_init (str): The new __init__ method

        Returns:
        str: Success message
        """
        filepath = self.safe_join(base=self.WORKING_DIRECTORY, paths=filename)
        with open(filepath, "r") as f:
            content = f.read()

        new_init = new_init.replace("    def __init__", "def __init__")

        # Find the existing __init__ method and replace it
        init_pattern = r"def __init__\(.*?\):\s*.*?(?=\n\s{4}def|\n\s{0}def|\nclass|\Z)"
        if re.search(init_pattern, content, re.DOTALL):
            content = re.sub(init_pattern, new_init, content, flags=re.DOTALL)
        else:
            # If no __init__ method found, add it after class definition
            class_pattern = r"(class\s+\w+.*?:\s*)"
            content = re.sub(class_pattern, rf"\1\n{new_init}\n", content)

        with open(filepath, "w") as f:
            f.write(content)

        return f"Successfully replaced __init__ method in {filename}"

    def parse_openapi(self, data):
        """
        Parse OpenAPI data to extract endpoints

        Args:
        data (dict): The OpenAPI data

        Returns:
        list: List of parsed endpoints
        """
        endpoints = []
        components = data.get("components", {})
        schemas = components.get("schemas", {})
        parameters = components.get("parameters", {})

        def resolve_schema(ref):
            if ref.startswith("#/components/schemas/"):
                schema_name = ref.split("/")[-1]
                return schemas.get(schema_name, {})
            return {}

        def resolve_parameter(ref):
            if ref.startswith("#/components/parameters/"):
                param_name = ref.split("/")[-1]
                return parameters.get(param_name, {})
            return {}

        for path, path_item in data.get("paths", {}).items():
            for method, operation in path_item.items():
                if method.lower() not in ["get", "post", "put", "delete", "patch"]:
                    continue

                endpoint_info = {
                    "path": path,
                    "method": method.upper(),
                    "operationId": operation.get("operationId", ""),
                    "summary": operation.get("summary", ""),
                    "description": operation.get("description", ""),
                    "parameters": [],
                    "requestBody": {},
                    "responses": {},
                }

                # Process parameters
                for param in operation.get("parameters", []):
                    if "$ref" in param:
                        param = resolve_parameter(param["$ref"])

                    param_info = {
                        "name": param.get("name", ""),
                        "in": param.get("in", ""),
                        "required": param.get("required", False),
                        "schema": param.get("schema", {}),
                        "description": param.get("description", ""),
                    }
                    endpoint_info["parameters"].append(param_info)

                # Process request body
                request_body = operation.get("requestBody", {})
                if request_body:
                    content = request_body.get("content", {})
                    for content_type, content_info in content.items():
                        schema = content_info.get("schema", {})
                        if "$ref" in schema:
                            schema = resolve_schema(schema["$ref"])
                        endpoint_info["requestBody"] = {
                            "content_type": content_type,
                            "schema": schema,
                            "required": request_body.get("required", False),
                        }
                        break

                # Process responses
                for status_code, response in operation.get("responses", {}).items():
                    content = response.get("content", {})
                    for content_type, content_info in content.items():
                        schema = content_info.get("schema", {})
                        if "$ref" in schema:
                            schema = resolve_schema(schema["$ref"])
                        endpoint_info["responses"][status_code] = {
                            "description": response.get("description", ""),
                            "content_type": content_type,
                            "schema": schema,
                        }
                        break

                endpoints.append(endpoint_info)

        return endpoints

    def get_auth_type(self, openapi_data):
        """
        Get the authentication type from OpenAPI data

        Args:
        openapi_data (dict): The OpenAPI data

        Returns:
        str: The authentication type
        """
        components = openapi_data.get("components", {})
        security_schemes = components.get("securitySchemes", {})

        if security_schemes:
            for scheme_name, scheme in security_schemes.items():
                auth_type = scheme.get("type", "")
                if auth_type == "http":
                    return f"Bearer {scheme.get('scheme', 'bearer')}"
                elif auth_type == "apiKey":
                    return f"API Key in {scheme.get('in', 'header')}"
                elif auth_type == "oauth2":
                    return "OAuth2"

        return "None"

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
                agent_id=self.agent_id,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": f"{rules}\nUsing context from the web search, please provide the base URI of the API for: {extension_name}.",
                    "disable_commands": True,
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

        return chain_name

    async def mcp_client(
        self,
        mcp_server: str,
        method: str = "tools/list",
        params: dict = {},
    ):
        """
        Use MCP (Model Context Protocol) Server

        Args:
        mcp_server (str): The MCP server name or URI
        method (str): The MCP method to call
        params (dict): Parameters for the MCP method

        Returns:
        str: The response from the MCP server
        """
        try:
            from mcp_client import MCPClient

            client = MCPClient()
            response = await client.call_method(
                server=mcp_server, method=method, params=params
            )
            return str(response)
        except Exception as e:
            logging.error(f"MCP client error: {str(e)}")
            return f"Error using MCP server: {str(e)}"
