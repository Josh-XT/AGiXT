import json
import os
import subprocess
import asyncio
import logging
import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from MagicalAuth import (
    convert_time,
    get_user_timezone,
    convert_user_time_to_utc,
    get_current_user_time,
)
from Extensions import Extensions
from safeexecute import execute_python_code
from agixtsdk import AGiXTSDK
from Globals import getenv
from Task import Task
from DB import (
    get_session,
    Base,
    DATABASE_TYPE,
    UUID,
    get_new_id,
    ExtensionDatabaseMixin,
)
import uuid


# Database Model for Todos
class EssentialTodo(Base):
    """Database model for storing todo items in essential abilities"""

    __tablename__ = "essential_todos"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        nullable=False,
        index=True,
    )
    parent_id = Column(
        Integer, ForeignKey("essential_todos.id"), nullable=True, default=None
    )
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(
        String(20), nullable=False, default="not-started"
    )  # not-started, in-progress, completed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    # Self-referential relationship for parent-child todos
    children = relationship(
        "EssentialTodo",
        backref="parent",
        remote_side=[id],
        cascade="all, delete-orphan",
        single_parent=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": str(self.conversation_id),
            "parent_id": self.parent_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "has_children": (
                len(self.children) > 0 if hasattr(self, "children") else False
            ),
        }


class essential_abilities(Extensions, ExtensionDatabaseMixin):
    """
    The Essential Abilities extension provides core functionality for agents,
    including file system operations within the agent's workspace, data analysis, Python code execution,
    scheduling follow-up messages, todo list management, and other fundamental capabilities.

    The agent's workspace is a safe sandboxed environment where the agent has access to uploaded files, files it downloads,
    and files it creates. This allows the agent to perform tasks such as reading and writing files, searching file contents,
    executing Python scripts, and running shell commands in its own environment.

    The scheduling capabilities enable the AI to proactively schedule follow-up messages and interactions with users at specific times.
    When scheduled times arrive, the AI can execute commands and notify users of task completion, enabling time-based automation
    and proactive engagement such as reminders, progress checks, automated reports, and recurring check-ins.

    The todo list management capabilities allow the AI to create, track, and manage structured todo lists with database persistence.
    Each todo is linked to the current conversation and supports status tracking (not-started, in-progress, completed).
    This ensures proper task visibility, planning, and completion tracking for complex workflows across conversation sessions.
    """

    CATEGORY = "Core Abilities"

    # Register extension models for automatic table creation
    extension_models = [EssentialTodo]

    def __init__(self, **kwargs):
        self.commands = {
            "Write to File": self.write_to_file,
            "Read File": self.read_file,
            "Search Files": self.search_files,
            "Search File Content": self.search_file_content,
            "Modify File": self.modify_file,
            "Execute Python File": self.execute_python_file,
            "Delete File": self.delete_file,
            "Execute Shell": self.execute_shell,
            "Run Data Analysis": self.run_data_analysis,
            "Execute Python Code": self.execute_python_code_internal,
            "Explain Chain": self.chain_to_mermaid,
            "Get Datetime": self.get_datetime,
            "Get Chain Details": self.get_chain_details,
            "Get Chain List": self.get_chain_list,
            "Create Automation Chain": self.create_agixt_chain,
            "Modify Automation Chain": self.modify_chain,
            "Custom API Endpoint": self.custom_api,
            "Get Mindmap for task to break it down": self.get_mindmap,
            "Convert Markdown to PDF": self.convert_to_pdf,
            "Convert Markdown to DOCX": self.convert_to_docx,
            "Convert Markdown to XLSX": self.convert_to_xlsx,
            "Convert Markdown to PPTX": self.convert_to_pptx,
            "Schedule Follow-Up Message": self.schedule_task,
            "Schedule Recurring Follow-Up": self.schedule_reoccurring_task,
            "Get Scheduled Follow-Ups": self.get_scheduled_tasks,
            "Modify Scheduled Follow-Up": self.modify_task,
            "Generate Image": self.generate_image,
            "Convert Text to Speech": self.text_to_speech,
            "Create Todo Item": self.create_todo_item,
            "Create Sub-Todo Item": self.create_sub_todo_item,
            "Create Todo Items in Bulk": self.create_todo_items_bulk,
            "List Current Todos": self.list_current_todos,
            "List Sub-Todos": self.list_sub_todos,
            "Mark Todo Item Completed": self.mark_todo_completed,
            "Mark Todo Item Incomplete": self.mark_todo_incomplete,
            "Update Todo Item": self.update_todo_item,
            "Delete Todo Item": self.delete_todo_item,
        }
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.WORKING_DIRECTORY_RESTRICTED = True
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)
        self.user_id = kwargs.get("user_id", None)
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
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
        self.output_url = kwargs.get("output_url", "")
        self.api_key = kwargs.get("api_key", "")

        # Register models with ExtensionDatabaseMixin
        self.register_models()

    def safe_join(self, paths) -> str:
        """
        Safely join paths together

        Args:
        paths (str): The paths to join

        Returns:
        str: The joined path
        """
        if "/path/to/" in paths:
            paths = paths.replace("/path/to/", "")
        new_path = os.path.normpath(
            os.path.join(self.WORKING_DIRECTORY, *paths.split("/"))
        )
        path_dir = os.path.dirname(new_path)
        os.makedirs(path_dir, exist_ok=True)
        return new_path

    @staticmethod
    def we_are_running_in_a_docker_container() -> bool:
        return os.path.exists("/.dockerenv")

    async def read_file(
        self,
        filename: str,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
    ) -> str:
        """
        Read a file in the workspace, optionally reading only specific line ranges

        Args:
        filename (str): The name of the file to read
        line_start (Optional[int]): The starting line number (1-indexed). If None, starts from beginning
        line_end (Optional[int]): The ending line number (1-indexed, inclusive). If None, reads to end

        Returns:
        str: The content of the file or specified line range
        """
        try:
            filepath = self.safe_join(filename)

            # Read the entire file or specific lines
            with open(filepath, "r", encoding="utf-8") as f:
                if line_start is None and line_end is None:
                    # Read entire file
                    content = f.read()
                else:
                    # Read specific line range
                    lines = f.readlines()
                    total_lines = len(lines)

                    # Convert to 0-indexed and handle bounds
                    start_idx = 0 if line_start is None else max(0, line_start - 1)
                    end_idx = (
                        total_lines if line_end is None else min(total_lines, line_end)
                    )

                    # Extract the requested lines
                    selected_lines = lines[start_idx:end_idx]
                    content = "".join(selected_lines)

                    # Add line number information if reading a range
                    if line_start is not None or line_end is not None:
                        actual_start = start_idx + 1
                        actual_end = min(end_idx, total_lines)
                        header = f"Lines {actual_start}-{actual_end} of {total_lines} total lines:\\n"
                        content = header + "=" * 40 + "\\n" + content

            return content
        except Exception as e:
            return f"Error: {str(e)}"

    async def write_to_file(self, filename: str, text: str) -> str:
        """
        Write text to a file in the workspace

        Args:
        filename (str): The name of the file to write to
        text (str): The text to write to the file

        Returns:
        str: Success message with download link

        Note: This command will only work in the agent's designated workspace.
        """
        try:
            filepath = self.safe_join(filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            return f"File {filename} written successfully. The user can access it at {self.output_url}{filename}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    async def search_files(self, query: str) -> str:
        """
        Search for files in the workspace that match a pattern

        Args:
        query (str): The search pattern or filename

        Returns:
        str: List of matching files

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
        """
        import fnmatch

        matches = []
        try:
            for root, dirnames, filenames in os.walk(self.WORKING_DIRECTORY):
                for filename in fnmatch.filter(filenames, f"*{query}*"):
                    relative_path = os.path.relpath(
                        os.path.join(root, filename), self.WORKING_DIRECTORY
                    )
                    matches.append(relative_path)

            if matches:
                return f"Found {len(matches)} matching files:\\n" + "\\n".join(matches)
            else:
                return f"No files found matching pattern: {query}"
        except Exception as e:
            return f"Error searching files: {str(e)}"

    async def search_file_content(self, query: str, filename: str = "") -> str:
        """
        Search for content within files in the workspace

        Args:
        query (str): The text to search for
        filename (str): Optional specific file to search in

        Returns:
        str: Search results showing matching lines

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
        """
        import re

        matches = []
        try:
            if filename:
                # Search in specific file
                files_to_search = [filename]
            else:
                # Search in all text files
                files_to_search = []
                for root, dirs, files in os.walk(self.WORKING_DIRECTORY):
                    for file in files:
                        if file.endswith(
                            (
                                ".txt",
                                ".py",
                                ".md",
                                ".json",
                                ".yaml",
                                ".yml",
                                ".ini",
                                ".cfg",
                            )
                        ):
                            relative_path = os.path.relpath(
                                os.path.join(root, file), self.WORKING_DIRECTORY
                            )
                            files_to_search.append(relative_path)

            for file_path in files_to_search:
                try:
                    full_path = self.safe_join(file_path)
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()

                    for line_num, line in enumerate(lines, 1):
                        if query.lower() in line.lower():
                            matches.append(f"{file_path}:{line_num}: {line.strip()}")
                except:
                    continue

            if matches:
                return f"Found {len(matches)} matches:\\n" + "\\n".join(
                    matches[:20]
                )  # Limit to first 20 matches
            else:
                return f"No matches found for: {query}"
        except Exception as e:
            return f"Error searching file content: {str(e)}"

    async def modify_file(self, filename: str, old_text: str, new_text: str) -> str:
        """
        Modify a file by replacing old text with new text

        Args:
        filename (str): The name of the file to modify
        old_text (str): The text to replace
        new_text (str): The replacement text

        Returns:
        str: Success message with download link or error message

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
        """
        try:
            filepath = self.safe_join(filename)

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            if old_text not in content:
                return f"Error: Text '{old_text}' not found in file {filename}"

            modified_content = content.replace(old_text, new_text)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(modified_content)

            return f"File {filename} modified successfully. The user can access it at {self.output_url}{filename}"
        except Exception as e:
            return f"Error modifying file: {str(e)}"

    async def delete_file(self, filename: str) -> str:
        """
        Delete a file from the workspace

        Args:
        filename (str): The name of the file to delete

        Returns:
        str: Success message

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
        """
        try:
            filepath = self.safe_join(filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                return f"File {filename} deleted successfully."
            else:
                return f"Error: File {filename} does not exist."
        except Exception as e:
            return f"Error deleting file: {str(e)}"

    async def execute_python_file(self, file: str):
        """
        Execute a Python file in the workspace

        Args:
        file (str): The name of the Python file to execute

        Returns:
        str: The output of the Python file

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
        """
        logging.info(f"Executing file '{file}' in workspace '{self.WORKING_DIRECTORY}'")

        if not file.endswith(".py"):
            return "Error: Invalid file type. Only .py files are allowed."

        file_path = os.path.join(self.WORKING_DIRECTORY, file)

        if not os.path.isfile(file_path):
            return f"Error: File '{file}' does not exist."

        if self.we_are_running_in_a_docker_container():
            result = subprocess.run(
                f"python {file_path}", capture_output=True, encoding="utf8", shell=True
            )
            if result.returncode == 0:
                return result.stdout
            else:
                return f"Error: {result.stderr}"

        with open(file_path, "r") as f:
            code = f.read()
        return execute_python_code(code=code, working_directory=self.WORKING_DIRECTORY)

    async def execute_shell(self, command_line: str) -> str:
        """
        Execute a shell command in a sandboxed environment

        Args:
        command_line (str): The shell command to execute

        Returns:
        str: The output of the shell command

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
        """
        try:
            # Try to use the new shell execution capability from safeexecute
            from safeexecute import execute_shell_command

            # Execute the shell command with proper sandboxing
            result = execute_shell_command(
                command=command_line,
                working_directory=self.WORKING_DIRECTORY,
                agent_id=self.agent_name,
                conversation_id=self.conversation_id,
            )

            return result
        except ImportError:
            # Fallback to the old method if execute_shell_command is not available
            # Create Python code that will execute the shell command in a sandboxed environment
            sandboxed_code = f"""
import subprocess
import os

# Execute the command
result = subprocess.run(
    {repr(command_line)}, 
    capture_output=True, 
    shell=True,
    text=True,
    timeout=30  # Add timeout for safety
)

# Format output
output = "STDOUT:\\n"
if result.stdout:
    output += result.stdout
else:
    output += "(no output)"
    
output += "\\nSTDERR:\\n"
if result.stderr:
    output += result.stderr
else:
    output += "(no errors)"

output += f"\\nReturn Code: {{result.returncode}}"

print(output)
"""

            # Execute the code in a sandboxed environment
            try:
                result = execute_python_code(
                    code=sandboxed_code, working_directory=self.WORKING_DIRECTORY
                )
                return result
            except Exception as e:
                return f"Error executing shell command in sandbox: {str(e)}"

    async def run_data_analysis(self, data: str, query: str):
        """
        Run data analysis on a dataset of any format, including analyzing and solving math problems, and more.
        This should be used if the user's input contains a math problem that the assistant must solve, this includes counting, arithmetic, algebra, geometry, calculus, statistics, and other math-related problems.
        If the assistant mentions a file name that was uploaded in the conversation under `data`, it will reference that file automatically to be injected into the data analysis process.

        With this command, the assistant has the capability to directly manipulate files, convert images, and perform a variety of other tasks. Here are some examples:

        - Image Description and Manipulation: the assistant can directly manipulate images, including zooming, cropping, color grading, and resolution enhancement. It can also convert images from one format to another.
        - QR Code Generation: the assistant can create QR codes for various purposes.
        - Project Management: the assistant can assist in creating Gantt charts and mapping out project steps.
        - Study Scheduling: the assistant can design optimized study schedules for exam preparation.
        - File Conversion: the assistant can directly convert files from one format to another, such as PDF to text or video to audio.
        - Mathematical Computation: the assistant can solve complex math equations and produce graphs.
        - Document Analysis: the assistant can analyze, summarize, or extract information from large documents.
        - Data Visualization: the assistant can analyze datasets, identify trends, and create various types of graphs.
        - Geolocation Visualization: the assistant can provide geolocation maps to showcase specific trends or occurrences.
        - Code Analysis and Creation: the assistant can analyze and critique code, and even create code from scratch.
        - Many other things that can be accomplished running python code in a jupyter environment.
        - Multiple visualizations are allowed as long as the return is a markdown string with the url of the image.

        Args:
        data (str): The dataset
        query (str): The query

        Returns:
        str: The result of the data analysis
        """
        return self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "context": f"## Reference Data\\n{data}",
                "user_input": query,
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": True,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

    async def ask_for_help(self, query: str):
        """
        Ask for help from a helper agent

        Args:
        query (str): The task to ask for help with

        Returns:
        str: The response from the helper agent
        """
        return self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"Please help me with the following task:\\n{query}",
                "websearch": False,
                "websearch_depth": 0,
                "analyze_user_input": False,
                "disable_commands": True,
                "log_user_input": False,
                "log_output": False,
                "browse_links": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

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
            csv_content_header = text.split("\\n")[0]
            # Remove any trailing spaces from any headers
            csv_headers = [header.strip() for header in csv_content_header.split(",")]
            # Replace the first line with the comma separated headers
            text = ",".join(csv_headers) + "\\n" + "\\n".join(text.split("\\n")[1:])
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

    async def chain_to_mermaid(self, chain_name: str):
        """
        Convert a chain to a Mermaid diagram format for visualization

        Args:
        chain_name (str): The name of the chain to explain

        Returns:
        str: A Mermaid diagram representation of the chain
        """
        chain_data = self.ApiClient.get_chain(chain_name=chain_name)
        mermaid_diagram = ["graph TD"]
        steps = chain_data.get("steps", [])

        for i, step in enumerate(steps):
            step_number = step.get("step", i + 1)
            agent_name = step.get("agent_name", "Unknown")
            prompt_type = step.get("prompt_type", "Unknown")
            prompt = step.get("prompt", {})

            # Create node for current step
            node_id = f"S{step_number}"
            node_label = f"{step_number}. {agent_name}"
            mermaid_diagram.append(f'    {node_id}["{node_label}"]')

            # Add details about the prompt or command
            if prompt_type.lower() == "prompt":
                prompt_name = prompt.get("prompt_name", "Unknown")
                mermaid_diagram.append(
                    f'    {node_id}AI["AI Prompt:<br>{prompt_name}"]'
                )
                mermaid_diagram.append(f"    {node_id} --> {node_id}AI")
            else:  # Command or Chain
                command_name = prompt.get("command_name") or prompt.get(
                    "chain_name", "Unknown"
                )
                mermaid_diagram.append(
                    f'    {node_id}Cmd["Command:<br>{command_name}"]'
                )
                mermaid_diagram.append(f"    {node_id} --> {node_id}Cmd")

            # Connect to next step
            if i < len(steps) - 1:
                next_step = steps[i + 1].get("step", i + 2)
                mermaid_diagram.append(f"    {node_id} --> S{next_step}")

            # Add connections for step dependencies
            for key, value in prompt.items():
                if isinstance(value, str) and "{STEP" in value:
                    dep_step = value.split("{STEP")[1].split("}")[0]
                    mermaid_diagram.append(f"    S{dep_step} -.-> {node_id}")

        mermaid = "\\n".join(mermaid_diagram)
        return f"```mermaid\\n{mermaid}\\n```"

    async def get_chain_details(self, chain_name: str):
        """
        Get details of a chain

        Args:
        chain_name (str): The name of the chain

        Returns:
        str: The details of the chain
        """
        chain_data = self.ApiClient.get_chain(chain_name=chain_name)
        return json.dumps(chain_data, indent=4)

    async def get_chain_list(self):
        """
        Get a list of all chains

        Returns:
        str: The list of chains
        """
        chains = self.ApiClient.get_chains()
        chain_names = [chain["name"] for chain in chains]
        return "Available Chains:\\n" + "\\n".join(chain_names)

    async def get_datetime(self) -> str:
        """
        Get the current date and time

        Returns:
        str: The current date and time in the format "YYYY-MM-DD HH:MM:SS"
        """
        return "Current date and time: " + convert_time(
            datetime.datetime.now(), user_id=self.user_id
        ).strftime("%Y-%m-%d %H:%M:%S")

    async def create_agixt_chain(self, natural_language_request: str):
        """
        Create an automation chain from a natural language request

        Args:
        natural_language_request (str): Description of what the chain should do

        Returns:
        str: The name of the created chain
        """
        response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Create Chain",
            prompt_args={
                "user_input": natural_language_request,
                "conversation_name": self.conversation_name,
            },
        )
        return response

    async def modify_chain(self, chain_name: str, description_of_modifications: str):
        """
        Modify an existing automation chain

        Args:
        chain_name (str): The name of the chain to modify
        description_of_modifications (str): Description of the modifications to make

        Returns:
        str: Confirmation of the modifications
        """
        response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Modify Chain",
            prompt_args={
                "chain_name": chain_name,
                "user_input": description_of_modifications,
                "conversation_name": self.conversation_name,
            },
        )
        return response

    async def custom_api(
        self,
        method: str,
        url: str,
        headers: str = "",
        body: str = "",
    ):
        """
        Make a custom API call

        Args:
        method (str): HTTP method (GET, POST, PUT, DELETE, etc.)
        url (str): The URL to call
        headers (str): JSON string of headers to include
        body (str): Request body (for POST, PUT, etc.)

        Returns:
        str: The API response
        """
        import requests

        try:
            # Parse headers if provided
            if headers:
                headers_dict = (
                    json.loads(headers) if isinstance(headers, str) else headers
                )
            else:
                headers_dict = {}

            # Make the API call
            if method.upper() in ["POST", "PUT", "PATCH"] and body:
                response = requests.request(
                    method=method.upper(),
                    url=url,
                    headers=headers_dict,
                    json=json.loads(body) if isinstance(body, str) else body,
                    timeout=30,
                )
            else:
                response = requests.request(
                    method=method.upper(), url=url, headers=headers_dict, timeout=30
                )

            return f"Status: {response.status_code}\\nResponse: {response.text}"
        except Exception as e:
            return f"Error making API call: {str(e)}"

    async def get_mindmap(self, task: str, additional_context: str = ""):
        """
        Get a mindmap for a task

        Args:
        task (str): The task
        additional_context (str): Additional context for the task

        Returns:
        dict: The mindmap
        """
        mindmap = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"Create a mindmap using a mermaid diagram for the users input:\\n{task}",
                "context": f"Additional context for creating the mindmap:\\n{additional_context}",
                "websearch": False,
                "websearch_depth": 0,
                "analyze_user_input": False,
                "disable_commands": True,
                "log_user_input": False,
                "log_output": False,
                "browse_links": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )
        return mindmap

    async def convert_to_pdf(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to PDF.

        Args:
            markdown_content: The markdown content to convert
            output_file: File name for the output PDF file

        Returns:
            str: Success message with download link or error message

        Note: Do not include a path in the output_file, just the file name. The file will be saved in the agent's workspace and a link to download returned.
        """
        try:
            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )

            # Write the markdown content to the temp file
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Execute the conversion with pandoc
            process = await asyncio.create_subprocess_exec(
                "pandoc",
                temp_md,
                "-o",
                output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return f"Error: {stderr.decode()}"

            return f"Successfully converted to {self.output_url}{output_file}"

        except Exception as e:
            logging.error(f"Error converting to PDF: {str(e)}")
            return f"Error: {str(e)}"

    async def convert_to_docx(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to DOCX.

        Args:
            markdown_content: The markdown content to convert
            output_file: File name for the output DOCX file

        Returns:
            str: Success message with download link or error message

        Note: Do not include a path in the output_file, just the file name. The file will be saved in the agent's workspace and a link to download returned.
        """
        try:
            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )

            # Write the markdown content to the temp file
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Execute the conversion with pandoc
            process = await asyncio.create_subprocess_exec(
                "pandoc",
                temp_md,
                "-o",
                output_path,
                "-t",
                "docx",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return f"Error: {stderr.decode()}"

            return f"Successfully converted to {self.output_url}{output_file}"

        except Exception as e:
            logging.error(f"Error converting to DOCX: {str(e)}")
            return f"Error: {str(e)}"

    async def convert_to_xlsx(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to XLSX.

        Args:
            markdown_content: The markdown content to convert
            output_file: File name for the output XLSX file

        Returns:
            str: Success message with download link or error message

        Note: Do not include a path in the output_file, just the file name. The file will be saved in the agent's workspace and a link to download returned.
        """
        try:
            import pandas as pd

            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file for reference
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Process markdown content to extract tables
            lines = markdown_content.split("\n")

            # Find table sections (marked by | character)
            tables = []
            current_table = []

            for line in lines:
                if "|" in line:
                    cells = [cell.strip() for cell in line.split("|")]
                    # Remove empty cells from start/end that result from splitting
                    cells = [c for c in cells if c]
                    if cells:  # Only add non-empty rows
                        current_table.append(cells)
                elif current_table:
                    # We've reached the end of a table
                    if (
                        len(current_table) > 1
                    ):  # Only keep tables with at least header and one row
                        # First row is header, second is separator, rest is data
                        df = pd.DataFrame(current_table[2:], columns=current_table[0])
                        tables.append(df)
                    current_table = []

            # Check if we ended with a table
            if current_table and len(current_table) > 1:
                df = pd.DataFrame(current_table[2:], columns=current_table[0])
                tables.append(df)

            # If no tables found, create a simple one-column dataframe with content
            if not tables:
                df = pd.DataFrame({"Content": [line for line in lines if line.strip()]})
                tables = [df]

            # Create Excel writer with multiple sheets if needed
            with pd.ExcelWriter(output_path) as writer:
                if len(tables) == 1:
                    # Single table - use main sheet
                    tables[0].to_excel(writer, sheet_name="Sheet1", index=False)
                else:
                    # Multiple tables - use multiple sheets
                    for i, table in enumerate(tables):
                        table.to_excel(writer, sheet_name=f"Table {i+1}", index=False)

            return f"Successfully converted to {self.output_url}{output_file}"

        except Exception as e:
            logging.error(f"Error converting to XLSX: {str(e)}")
            return f"Error: {str(e)}"

    async def convert_to_pptx(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to PPTX.

        Args:
            markdown_content: The markdown content to convert
            output_file: File name for the output PPTX file

        Returns:
            str: Success message with download link or error message

        Note: Do not include a path in the output_file, just the file name. The file will be saved in the agent's workspace and a link to download returned.
        """
        try:
            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )

            # Write the markdown content to the temp file
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Execute the conversion with pandoc
            process = await asyncio.create_subprocess_exec(
                "pandoc",
                temp_md,
                "-o",
                output_path,
                "-t",
                "pptx",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return f"Error: {stderr.decode()}"

            return f"Successfully converted to {self.output_url}{output_file}"

        except Exception as e:
            logging.error(f"Error converting to PPTX: {str(e)}")
            return f"Error: {str(e)}"

    async def schedule_task(
        self,
        title: str,
        task_description: str,
        days: str = 0,
        hours: str = 0,
        minutes: str = 0,
    ) -> str:
        """
        Schedule a follow-up message to the user at a specific time in the future.
        Use this to proactively remind users, check on progress, or execute commands at scheduled times.
        Examples: reminding about deadlines, following up on tasks, scheduling automated reports, or checking in after a delay.
        At the scheduled time, the AI will message the user and can execute any available commands to complete the task.

        Args:
            title (str): Brief title describing the follow-up purpose (e.g., "Check project progress", "Send daily report")
            task_description (str): Detailed instructions for what the AI should do when following up, including specific commands to run and information to provide
            days (int): Number of days from now to schedule the follow-up
            hours (int): Number of hours from now to schedule the follow-up
            minutes (int): Number of minutes from now to schedule the follow-up

        Returns:
            str: Confirmation of the scheduled follow-up with the exact date/time
        """
        try:
            days = int(days)
        except:
            days = 0
        try:
            hours = int(hours)
        except:
            hours = 0
        try:
            minutes = int(minutes)
        except:
            minutes = 0
        # Calculate the due date from user's current time
        user_now = get_current_user_time(self.user_id)
        user_due_time = user_now + datetime.timedelta(
            days=days, hours=hours, minutes=minutes
        )

        # Convert to UTC for database storage
        due_date = convert_user_time_to_utc(user_due_time, self.user_id)

        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        # Create a descriptive title from the purpose of the follow-up
        title_preview = title.split("\n")[0][:50] + ("..." if len(title) > 50 else "")

        # Create the follow-up task
        task_id = await task_manager.create_task(
            title=title_preview,
            description=task_description,
            category_name="Follow-ups",
            agent_name=self.agent_name,
            due_date=due_date,
            priority=1,  # High priority for follow-ups
            memory_collection=self.conversation_id,  # This ensures context preservation
        )

        return f"Scheduled follow-up message (ID: {task_id}) for {due_date.strftime('%Y-%m-%d %H:%M:%S')}. I'll message you then to {title}."

    async def schedule_reoccurring_task(
        self,
        title: str,
        task_description: str,
        start_date: str,
        end_date: str,
        frequency: str = "daily",
    ) -> str:
        """
        Schedule recurring follow-up messages to the user on a regular basis.
        Use this for periodic check-ins, regular reports, repeated reminders, or any task that needs consistent follow-up.
        The AI will message the user at each scheduled interval and can execute commands to provide updates or perform actions.
        Perfect for daily summaries, weekly progress checks, or monthly reports.

        Args:
            title (str): Brief title for the recurring follow-up (e.g., "Daily standup check-in", "Weekly metrics report")
            task_description (str): What the AI should do at each follow-up, including commands to run and information to gather
            start_date (datetime.datetime): When to begin the recurring follow-ups
            end_date (datetime.datetime): When to stop the recurring follow-ups
            frequency (str): How often to follow up - "daily", "weekly", or "monthly"

        Returns:
            str: Confirmation of the recurring follow-up schedule
        """
        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        # Create a descriptive title from the purpose of the follow-up
        title_preview = title.split("\n")[0][:50] + ("..." if len(title) > 50 else "")

        # Create the follow-up task
        task_ids = await task_manager.create_reoccurring_task(
            title=title_preview,
            description=task_description,
            category_name="Follow-ups",
            agent_name=self.agent_name,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            priority=1,  # High priority for follow-ups
            memory_collection=self.conversation_id,  # This ensures context preservation
        )
        return f"Scheduled {frequency} follow-up messages from {start_date} to {end_date}. I'll check in regularly to {title}."

    async def modify_task(
        self,
        task_id: str,
        title: str = None,
        description: str = None,
        due_date: str = None,
        estimated_hours: str = None,
        priority: str = None,
        cancel_task: str = "false",
    ):
        """
        Modify or cancel a scheduled follow-up message.
        Use this to adjust timing, change what the AI should do at follow-up, update priorities, or cancel if no longer needed.
        This helps maintain relevant and timely follow-ups based on changing circumstances.

        Args:
            task_id (str): The ID of the scheduled follow-up to modify (obtained from Get Scheduled Follow-Ups)
            title (str): New title for the follow-up (optional)
            description (str): Updated instructions for what to do at follow-up (optional)
            due_date (datetime.datetime): New scheduled time for the follow-up (optional)
            estimated_hours (int): Updated time estimate (optional)
            priority (int): New priority level 1-5, where 1 is highest (optional)
            cancel_task (bool): Set to "true" to cancel the follow-up entirely

        Returns:
            str: Confirmation of the changes made
        """
        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        if str(cancel_task).lower() == "true":
            return await task_manager.delete_task(task_id)
        # Update the task
        return await task_manager.update_task(
            task_id=task_id,
            title=title,
            description=description,
            due_date=due_date,
            estimated_hours=estimated_hours,
            priority=priority,
        )

    async def get_scheduled_tasks(self):
        """
        Retrieve all scheduled follow-up messages for the current conversation.
        Use this to review upcoming follow-ups, check their timing, or find task IDs for modification.
        This helps ensure follow-ups are still relevant and properly scheduled.

        Returns:
            list: List of all scheduled follow-ups with their details, timing, and task IDs
        """
        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        # Get all tasks for the current agent
        tasks = await task_manager.get_pending_tasks()
        return tasks

    async def generate_image(self, prompt):
        """
        Generate an image from a prompt.

        Args:
            prompt (str): The prompt to generate the image from.

        Returns:
            str: The URL of the generated image.
        Note:
            The assistant should send the image URL to the user so they can listen to it, it will embed the image in the chat when the assistant sends the URL.
        """
        return self.ApiClient.generate_image(
            prompt=prompt,
            model=self.agent_name,
        )

    async def text_to_speech(self, text):
        """
        Convert text to speech. The assistant can use its voice to read the text aloud to the user.

        Args:
            text (str): The text to convert to speech.

        Returns:
            str: The URL of the generated audio.

        Note:
            The assistant should send the audio URL to the user so they can listen to it, it will embed the audio in the chat when the assistant sends the URL.
        """
        return self.ApiClient.text_to_speech(
            text=text,
            agent_name=self.agent_name,
        )

    async def create_todo_item(
        self, title: str, description: str, parent_id: int = None
    ) -> str:
        """
        Create a new todo item in the current conversation.

        Use this to break down complex tasks into manageable steps and track progress.
        Each todo item is linked to the current conversation for context.

        Args:
            title (str): A concise, action-oriented title for the todo item (3-7 words)
            description (str): Detailed description including context, requirements, file paths,
                             specific methods, or acceptance criteria
            parent_id (int, optional): ID of parent todo to create this as a sub-todo        Returns:
            str: JSON response with success status and created todo item details

        Usage Guidelines:
        - Create todos for multi-step work requiring planning and tracking
        - Use descriptive titles that clearly indicate the action needed
        - Include comprehensive descriptions with all necessary context
        - Break down larger tasks into smaller, actionable steps
        - Create todos BEFORE starting work to ensure proper tracking

        When to use:
        - User provides multiple tasks or complex requests
        - Breaking down large projects into manageable pieces
        - Planning multi-step workflows or processes
        - Tracking progress on ongoing work
        """
        session = get_session()
        try:
            if not title.strip():
                return json.dumps({"success": False, "error": "Title cannot be empty"})

            if not description.strip():
                return json.dumps(
                    {"success": False, "error": "Description cannot be empty"}
                )

            # Validate parent_id if provided
            if parent_id is not None:
                parent_todo = (
                    session.query(EssentialTodo)
                    .filter(
                        EssentialTodo.id == parent_id,
                        EssentialTodo.conversation_id == self.conversation_id,
                    )
                    .first()
                )
                if not parent_todo:
                    return json.dumps(
                        {"success": False, "error": "Parent todo not found"}
                    )

            # Create new todo item
            todo = EssentialTodo(
                conversation_id=self.conversation_id,
                parent_id=parent_id,
                title=title.strip(),
                description=description.strip(),
                status="not-started",
            )

            session.add(todo)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": "Todo item created successfully",
                    "todo": todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def create_sub_todo_item(
        self, parent_todo_id: int, title: str, description: str
    ) -> str:
        """
        Create a new sub-todo item under an existing parent todo.

        Sub-todos are useful for breaking down complex tasks into smaller, more manageable steps.
        They are linked to a parent todo and can be managed independently while maintaining hierarchy.

        Args:
            parent_todo_id (int): The ID of the parent todo to attach this sub-todo to
            title (str): A concise, action-oriented title for the sub-todo item
            description (str): Detailed description of the sub-task

        Returns:
            str: JSON response with success status and created sub-todo details

        Usage Guidelines:
        - Use when a main todo has multiple distinct sub-tasks
        - Sub-todos can have their own status independent of parent
        - Helps organize complex workflows hierarchically
        - Parent todo remains visible even when sub-todos are completed

        When to use:
        - Breaking down large tasks into specific steps
        - When a todo has multiple components that can be tracked separately
        - Creating detailed checklists for complex processes
        - Organizing multi-phase work within a larger task
        """
        session = get_session()
        try:
            if not title.strip():
                return json.dumps({"success": False, "error": "Title cannot be empty"})

            if not description.strip():
                return json.dumps(
                    {"success": False, "error": "Description cannot be empty"}
                )

            # Validate parent todo exists
            parent_todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == parent_todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not parent_todo:
                return json.dumps({"success": False, "error": "Parent todo not found"})

            # Create new sub-todo item
            sub_todo = EssentialTodo(
                conversation_id=self.conversation_id,
                parent_id=parent_todo_id,
                title=title.strip(),
                description=description.strip(),
                status="not-started",
            )

            session.add(sub_todo)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Sub-todo item created successfully under '{parent_todo.title}'",
                    "sub_todo": sub_todo.to_dict(),
                    "parent_todo": parent_todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def create_todo_items_bulk(
        self,
        todo_1_title: str = "",
        todo_1_description: str = "",
        todo_2_title: str = "",
        todo_2_description: str = "",
        todo_3_title: str = "",
        todo_3_description: str = "",
        todo_4_title: str = "",
        todo_4_description: str = "",
        todo_5_title: str = "",
        todo_5_description: str = "",
        todo_6_title: str = "",
        todo_6_description: str = "",
        todo_7_title: str = "",
        todo_7_description: str = "",
        todo_8_title: str = "",
        todo_8_description: str = "",
        todo_9_title: str = "",
        todo_9_description: str = "",
        todo_10_title: str = "",
        todo_10_description: str = "",
    ) -> str:
        """
        Create multiple todo items in bulk (up to 10 at once).

        Use this when breaking down complex tasks into multiple actionable steps.
        Only fill in as many todo items as needed - empty title/description pairs will be ignored.
        This is much more efficient than creating todos individually when you have multiple tasks.

        Args:
            todo_1_title to todo_10_title (str): Titles for up to 10 todo items
            todo_1_description to todo_10_description (str): Descriptions for up to 10 todo items

        Returns:
            str: JSON response with success status and created todo items details

        Usage Guidelines:
        - Use when you have 2-10 related tasks to create at once
        - Only fill in the todo pairs you need (1-10)
        - Leave unused title/description parameters empty
        - Perfect for breaking down user requests into actionable steps
        - More efficient than multiple individual create_todo_item calls

        When to use:
        - User provides a complex multi-step request
        - Breaking down projects into manageable tasks
        - Planning workflows that require multiple steps
        - Initial task planning for new projects

        Example:
        - todo_1_title="Read requirements", todo_1_description="Review user specifications..."
        - todo_2_title="Design architecture", todo_2_description="Create system design..."
        - Leave todo_3_title="" and beyond if only 2 tasks needed
        """
        session = get_session()
        try:
            # Collect all the todo pairs into a list
            todo_pairs = [
                (todo_1_title, todo_1_description),
                (todo_2_title, todo_2_description),
                (todo_3_title, todo_3_description),
                (todo_4_title, todo_4_description),
                (todo_5_title, todo_5_description),
                (todo_6_title, todo_6_description),
                (todo_7_title, todo_7_description),
                (todo_8_title, todo_8_description),
                (todo_9_title, todo_9_description),
                (todo_10_title, todo_10_description),
            ]

            # Filter out empty pairs and validate
            valid_todos = []
            for i, (title, description) in enumerate(todo_pairs, 1):
                if title.strip() and description.strip():
                    valid_todos.append((title.strip(), description.strip()))
                elif title.strip() or description.strip():
                    # One is filled but not the other
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Todo {i}: Both title and description must be provided or both must be empty",
                        }
                    )

            if not valid_todos:
                return json.dumps(
                    {
                        "success": False,
                        "error": "At least one todo item (title and description) must be provided",
                    }
                )

            # Create all the todo items
            created_todos = []
            for title, description in valid_todos:
                todo = EssentialTodo(
                    conversation_id=self.conversation_id,
                    title=title,
                    description=description,
                    status="not-started",
                )
                session.add(todo)
                created_todos.append(todo)

            session.commit()

            # Convert to dict format for response
            created_todos_dict = [todo.to_dict() for todo in created_todos]

            return json.dumps(
                {
                    "success": True,
                    "message": f"Successfully created {len(created_todos)} todo items",
                    "todos": created_todos_dict,
                    "count": len(created_todos),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_current_todos(self, include_completed: bool = False) -> str:
        """
        List all todo items for the current conversation.

        Use this to get an overview of all tasks and their current status.
        Helps track progress and identify what work remains.

        Args:
            include_completed (bool): Whether to include completed todos in the list

        Returns:
            str: JSON response with list of todos and summary statistics

        Usage Guidelines:
        - Use this frequently to stay aware of current tasks
        - Check before starting work to prioritize properly
        - Review regularly to track overall progress
        - Use to identify bottlenecks or stalled tasks
        """
        session = get_session()
        try:
            # Build query based on completion filter
            query = session.query(EssentialTodo).filter(
                EssentialTodo.conversation_id == self.conversation_id
            )

            if not include_completed:
                query = query.filter(EssentialTodo.status != "completed")

            todos = query.order_by(EssentialTodo.created_at).all()

            # Generate summary statistics
            total_count = len(todos)
            completed_count = sum(1 for todo in todos if todo.status == "completed")
            in_progress_count = sum(1 for todo in todos if todo.status == "in-progress")
            not_started_count = sum(1 for todo in todos if todo.status == "not-started")

            # Convert todos to dict format with hierarchy
            parent_todos = [todo for todo in todos if todo.parent_id is None]
            child_todos = [todo for todo in todos if todo.parent_id is not None]

            # Build hierarchical structure
            todo_list = []
            for parent in parent_todos:
                parent_dict = parent.to_dict()
                # Find children for this parent
                children = [
                    child.to_dict()
                    for child in child_todos
                    if child.parent_id == parent.id
                ]
                parent_dict["sub_todos"] = children
                parent_dict["sub_todo_count"] = len(children)
                todo_list.append(parent_dict)

            # Add any orphaned children (shouldn't happen but just in case)
            for child in child_todos:
                if not any(p.id == child.parent_id for p in parent_todos):
                    child_dict = child.to_dict()
                    child_dict["sub_todos"] = []
                    child_dict["sub_todo_count"] = 0
                    todo_list.append(child_dict)

            summary = {
                "total": total_count,
                "completed": completed_count,
                "in_progress": in_progress_count,
                "not_started": not_started_count,
                "parent_todos": len(parent_todos),
                "sub_todos": len(child_todos),
            }

            # Find currently active todo
            active_todo = None
            for todo in todos:
                if todo.status == "in-progress":
                    active_todo = todo.to_dict()
                    break

            return json.dumps(
                {
                    "success": True,
                    "todos": todo_list,
                    "summary": summary,
                    "active_todo": active_todo,
                }
            )

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_sub_todos(self, parent_todo_id: int) -> str:
        """
        List all sub-todo items for a specific parent todo.

        Use this to focus on the sub-tasks of a particular todo item.
        Helpful when working through the details of a complex task.

        Args:
            parent_todo_id (int): The ID of the parent todo to list sub-todos for

        Returns:
            str: JSON response with sub-todos list and parent todo details

        Usage Guidelines:
        - Use when you need to see all sub-tasks for a specific parent
        - Helpful for planning work on a complex todo
        - Shows the breakdown of a larger task
        - Provides focused view of related sub-tasks
        """
        session = get_session()
        try:
            # Verify parent todo exists and belongs to this conversation
            parent_todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == parent_todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not parent_todo:
                return json.dumps({"success": False, "error": "Parent todo not found"})

            # Get all sub-todos for this parent
            sub_todos = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.parent_id == parent_todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .order_by(EssentialTodo.created_at)
                .all()
            )

            # Generate statistics for sub-todos
            total_count = len(sub_todos)
            completed_count = sum(1 for todo in sub_todos if todo.status == "completed")
            in_progress_count = sum(
                1 for todo in sub_todos if todo.status == "in-progress"
            )
            not_started_count = sum(
                1 for todo in sub_todos if todo.status == "not-started"
            )

            # Convert to dict format
            sub_todo_list = [todo.to_dict() for todo in sub_todos]

            # Find active sub-todo
            active_sub_todo = None
            for todo in sub_todos:
                if todo.status == "in-progress":
                    active_sub_todo = todo.to_dict()
                    break

            return json.dumps(
                {
                    "success": True,
                    "parent_todo": parent_todo.to_dict(),
                    "sub_todos": sub_todo_list,
                    "summary": {
                        "total": total_count,
                        "completed": completed_count,
                        "in_progress": in_progress_count,
                        "not_started": not_started_count,
                    },
                    "active_sub_todo": active_sub_todo,
                }
            )

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def mark_todo_completed(self, todo_id: int) -> str:
        """
        Mark a todo item as completed.

        Use this immediately after finishing work on a todo item.
        This helps track progress and keeps the todo list current.

        Args:
            todo_id (int): The unique ID of the todo item to mark as completed

        Returns:
            str: JSON response with success status and updated todo details

        Usage Guidelines:
        - Mark todos as completed IMMEDIATELY when finished
        - Don't batch completions - update as you go
        - This helps maintain accurate progress tracking
        - Completed todos provide a record of work done
        """
        session = get_session()
        try:
            todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not todo:
                return json.dumps({"success": False, "error": "Todo item not found"})

            todo.status = "completed"
            todo.updated_at = datetime.datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Todo '{todo.title}' marked as completed",
                    "todo": todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def mark_todo_incomplete(
        self, todo_id: int, status: str = "not-started"
    ) -> str:
        """
        Mark a todo item as incomplete (either not-started or in-progress).

        Use this to revert completed todos or update status when starting work.
        Only one todo can be in-progress at a time.

        Args:
            todo_id (int): The unique ID of the todo item to update
            status (str): The new status - either "not-started" or "in-progress"

        Returns:
            str: JSON response with success status and updated todo details

        Usage Guidelines:
        - Mark as "in-progress" when starting work on a todo
        - Only one todo should be "in-progress" at a time
        - Use "not-started" to reset a todo back to initial state
        - Change status before beginning work for proper tracking
        """
        session = get_session()
        try:
            if status not in ["not-started", "in-progress"]:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Status must be either 'not-started' or 'in-progress'",
                    }
                )

            # If setting to in-progress, ensure no other todo is in-progress
            if status == "in-progress":
                existing_in_progress = (
                    session.query(EssentialTodo)
                    .filter(
                        EssentialTodo.conversation_id == self.conversation_id,
                        EssentialTodo.status == "in-progress",
                        EssentialTodo.id != todo_id,
                    )
                    .first()
                )

                if existing_in_progress:
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Another todo is already in-progress: '{existing_in_progress.title}'",
                        }
                    )

            todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not todo:
                return json.dumps({"success": False, "error": "Todo item not found"})

            old_status = todo.status
            todo.status = status
            todo.updated_at = datetime.datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Todo '{todo.title}' status changed from '{old_status}' to '{status}'",
                    "todo": todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def update_todo_item(
        self, todo_id: int, title: str = None, description: str = None
    ) -> str:
        """
        Update the title or description of an existing todo item.

        Use this when requirements change or you need to clarify a todo item.
        Helps keep todos accurate and up-to-date.

        Args:
            todo_id (int): The unique ID of the todo item to update
            title (str, optional): New title for the todo item
            description (str, optional): New description for the todo item

        Returns:
            str: JSON response with success status and updated todo details

        Usage Guidelines:
        - Update todos when requirements become clearer
        - Refine descriptions as you learn more about the task
        - Keep titles concise and action-oriented
        - Update when scope or approach changes
        """
        session = get_session()
        try:
            todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not todo:
                return json.dumps({"success": False, "error": "Todo item not found"})

            updates = []
            if title is not None and title.strip():
                todo.title = title.strip()
                updates.append("title")

            if description is not None and description.strip():
                todo.description = description.strip()
                updates.append("description")

            if not updates:
                return json.dumps(
                    {"success": False, "error": "No valid updates provided"}
                )

            todo.updated_at = datetime.datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Todo '{todo.title}' updated successfully ({', '.join(updates)} changed)",
                    "todo": todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def delete_todo_item(self, todo_id: int) -> str:
        """
        Delete a todo item permanently.

        Use this to remove todos that are no longer relevant or were created in error.
        This action cannot be undone.

        Args:
            todo_id (int): The unique ID of the todo item to delete

        Returns:
            str: JSON response with success status and confirmation

        Usage Guidelines:
        - Only delete todos that are completely irrelevant
        - Consider marking as completed instead of deleting
        - Use when requirements change and the todo is no longer needed
        - Be cautious - this action cannot be undone
        """
        session = get_session()
        try:
            todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not todo:
                return json.dumps({"success": False, "error": "Todo item not found"})

            title = todo.title  # Store for confirmation message
            session.delete(todo)
            session.commit()

            return json.dumps(
                {"success": True, "message": f"Todo '{title}' deleted successfully"}
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()
