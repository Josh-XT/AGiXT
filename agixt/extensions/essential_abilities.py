import json
import os
import subprocess
import asyncio
import logging
import datetime
import threading
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
from InternalClient import InternalClient
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
    depends_on = Column(
        Text, nullable=True, default=None
    )  # Comma-separated list of task IDs that must be completed first
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    # Note: Self-referential relationship for parent-child todos
    # Commented out temporarily to resolve SQLAlchemy registry conflicts
    # children = relationship(
    #     "agixt.extensions.essential_abilities.EssentialTodo",
    #     backref="parent",
    #     remote_side=[id],
    #     cascade="all, delete-orphan",
    #     single_parent=True,
    # )

    def _parse_dependencies(self):
        """Parse the comma-separated depends_on field into a list of integers"""
        if not self.depends_on:
            return []
        try:
            return [int(id.strip()) for id in self.depends_on.split(",") if id.strip()]
        except ValueError:
            return []

    def _can_start(self):
        """Check if this task can be started (all dependencies are completed)"""
        dependencies = self._parse_dependencies()
        if not dependencies:
            return True

        # This will be called from to_dict, so we need to import get_session here
        from DB import get_session

        session = get_session()
        try:
            # Check if all dependencies are completed
            completed_deps = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id.in_(dependencies),
                    EssentialTodo.conversation_id == self.conversation_id,
                    EssentialTodo.status == "completed",
                )
                .count()
            )
            return completed_deps == len(dependencies)
        finally:
            session.close()

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": str(self.conversation_id),
            "parent_id": self.parent_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "depends_on": self.depends_on,
            "dependencies": self._parse_dependencies(),
            "can_start": self._can_start(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            # Note: has_children calculation disabled due to relationship temporarily removed
            "has_children": False,
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
            "List Runnable Todos": self.list_runnable_todos,
            "Run Todo List": self.run_todo_list,
            "List Sub-Todos": self.list_sub_todos,
            "Mark Todo Item Completed": self.mark_todo_completed,
            "Mark Todo Item Incomplete": self.mark_todo_incomplete,
            "Update Todo Item": self.update_todo_item,
            "Delete Todo Item": self.delete_todo_item,
            "Gather information from website URLs": self.browse_links,
            "Download File from URL": self.download_file_from_url,
            "View Image": self.view_image,
            "Get Web UI Tips": self.get_webui_tips,
            "Create AGiXT Agent": self.create_new_agixt_agent,
            "Optimize Command Selection": self.optimize_command_selection,
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
        self.agent_id = kwargs.get("agent_id")
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
        self.conversation_id = (
            kwargs["conversation_id"] if "conversation_id" in kwargs else ""
        )
        self.activity_id = kwargs["activity_id"] if "activity_id" in kwargs else None
        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else InternalClient(
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
                user=kwargs.get("user"),
            )
        )
        self.user = kwargs.get("user", None)
        self.output_url = kwargs.get("output_url", "")
        self.api_key = kwargs.get("api_key", "")

        # Register models with ExtensionDatabaseMixin
        self.register_models()

    async def browse_links(self, urls: str, query: str) -> str:
        """
        Browse links to gather information from websites. This will scrape data from the websites provided into the agent's memory.

        Args:
            urls (str): Space-separated list of URLs to browse. Prefix each url with "https://" with the full url. When browsing multiple URLs, separate them with spaces.
            query (str): The query to search for on the pages

        Returns:
            str: The gathered information

        Notes: This ability will browse the provided URLs and extract relevant information based on the query as well as extract learned information from the website into the assistant's memory.
        """
        response = self.ApiClient.prompt_agent(
            agent_id=self.agent_id,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"{urls} \n {query}",
                "websearch": False,
                "analyze_user_input": False,
                "disable_commands": True,
                "log_user_input": False,
                "log_output": False,
                "browse_links": True,
                "tts": False,
                "conversation_name": self.conversation_id,
            },
        )
        return response

    async def download_file_from_url(
        self, url: str, filename: str = "", headers: str = ""
    ) -> str:
        """
        Download a file from a URL to the agent's workspace

        Args:
            url (str): The URL to download the file from (must start with https://)
            filename (str): Optional custom filename to save as. If not provided, uses the filename from the URL
            headers (str): Optional JSON string of HTTP headers for authentication (e.g., '{"Authorization": "Bearer token"}')

        Returns:
            str: Success message with download link or error message

        Notes:
            - Only HTTPS URLs are allowed for security
            - Downloaded files are saved to the agent's workspace
            - Supports authentication via custom headers
            - Automatically detects filename from URL if not provided
            - File is immediately accessible to user via download link

        Example headers for authentication:
            '{"Authorization": "Bearer your_token_here"}'
            '{"X-API-Key": "your_api_key_here"}'
        """
        import requests
        from urllib.parse import urlparse, unquote

        # Security check: only allow HTTPS URLs
        if not url.startswith("https://"):
            return "Error: Only HTTPS URLs are allowed for security reasons. Please provide a URL starting with 'https://'"

        try:
            # Parse headers if provided
            request_headers = {}
            if headers:
                try:
                    request_headers = json.loads(headers)
                except json.JSONDecodeError:
                    return f"Error: Invalid headers format. Headers must be valid JSON string."

            # Make the request
            logging.info(f"Downloading file from URL: {url}")
            response = requests.get(
                url, headers=request_headers, stream=True, timeout=30
            )
            response.raise_for_status()

            # Determine filename
            if not filename:
                # Try to get filename from Content-Disposition header
                content_disposition = response.headers.get("Content-Disposition")
                if content_disposition:
                    import re

                    filename_match = re.findall(
                        'filename="?([^"]+)"?', content_disposition
                    )
                    if filename_match:
                        filename = filename_match[0]

                # If still no filename, extract from URL
                if not filename:
                    parsed_url = urlparse(url)
                    filename = unquote(parsed_url.path.split("/")[-1])

                # If still no filename, generate one
                if not filename or filename == "":
                    filename = f"downloaded_file_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Ensure filename doesn't contain path separators
            filename = os.path.basename(filename)

            # Save the file
            file_path = self.safe_join(filename)
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)

            logging.info(f"Successfully downloaded {filename} ({file_size_mb:.2f} MB)")

            return f"Successfully downloaded file to workspace: {filename} ({file_size_mb:.2f} MB)\n\nDownload link: {self.output_url}/{filename}"

        except requests.exceptions.Timeout:
            return f"Error: Request timed out while trying to download from {url}"
        except requests.exceptions.HTTPError as e:
            return f"Error: HTTP error occurred: {e.response.status_code} - {e.response.reason}"
        except requests.exceptions.RequestException as e:
            return f"Error: Failed to download file: {str(e)}"
        except Exception as e:
            return f"Error downloading file: {str(e)}"

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

    async def view_image(
        self, image_path: str, query: str = "What is in this image?"
    ) -> str:
        """
        View and analyze an image file in the agent's workspace

        Args:
        image_path (str): The path to the image file in the agent's workspace, or a URL to an image to download to the agent's workspace and view.
        query (str): The question or analysis to perform on the image

        Returns:
        str: The analysis or description of the image

        Note: Example, the assistant could ask what is in the image, to OCR the image to pull text from it, ask about specific things in the image or details, etc.
        """
        if image_path.startswith("https://"):
            file_name = f"{uuid.uuid4()}_{image_path.split('/')[-1]}"
            await self.download_file_from_url(url=image_path, filename=file_name)
            image_path = os.path.join(self.WORKING_DIRECTORY, file_name)
        # Ensure the image path is safe
        safe_image_path = self.safe_join(image_path)

        if not os.path.exists(safe_image_path):
            return f"Error: Image file '{image_path}' does not exist in the workspace."
        # Read and encode the image in base64
        import base64
        from Agent import Agent

        with open(safe_image_path, "rb") as img_file:
            image_data = img_file.read()
            base64_image = base64.b64encode(image_data).decode("utf-8")
        base64_image = f"data:image/{image_path.split('.')[-1]};base64,{base64_image}"

        agent = Agent(agent_id=self.agent_id, ApiClient=self.ApiClient, user=self.user)
        response = await agent.inference(prompt=query, images=[base64_image])
        return response

    async def read_file(
        self,
        filename: str,
        line_start: str,
        line_end: str,
    ) -> str:
        """
        Read a file in the workspace, optionally reading only specific line ranges

        Args:
        filename (str): The name of the file to read
        line_start (int): The starting line number (1-indexed). If "None", starts from beginning
        line_end (int): The ending line number (1-indexed, inclusive). If "None", reads to end

        Returns:
        str: The content of the file or specified line range

        Notes: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access. The user can browse the agents workspace by clicking the folder icon in their chat input bar.
        """
        try:
            line_start = int(line_start)
        except:
            line_start = None
        try:
            line_end = int(line_end)
        except:
            line_end = None
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
            parent_activity_id=self.activity_id,
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
        Execute Python code in a powerful sandboxed environment with full workspace access

        Args:
        code (str): The Python code to execute
        text (str): Optional CSV data that will be automatically saved as 'data.csv' in workspace

        Returns:
        str: The result of the Python code execution

        POWERFUL PYTHON CODE EXECUTION CAPABILITIES:

        **Workspace File System Access:**
        - Full read/write access to all files in your dedicated workspace directory
        - Automatically discovers and works with uploaded files, downloaded content, and previously created files
        - Can process multiple files simultaneously (CSV, Excel, images, PDFs, text files, etc.)
        - Files you create are immediately accessible to users via download links
        - Use standard Python file operations: open(), pandas.read_csv(), PIL.Image.open(), etc.

        **Multi-File Operations:**
        - Process entire directories of files at once
        - Combine data from multiple sources automatically
        - Cross-reference and merge datasets from different files
        - Batch process images, documents, or data files
        - Example: `import os; files = [f for f in os.listdir('.') if f.endswith('.csv')]`

        **Mathematical & Analytical Power:**
        - NEVER attempt math problems manually - ALWAYS use Python code for accurate calculations
        - Supports complex mathematics: calculus, statistics, linear algebra, differential equations
        - Includes counting operations (force strings to lowercase for letter counting)
        - Advanced statistical analysis and hypothesis testing
        - Machine learning and data modeling capabilities

        **Data Visualization & Analysis:**
        - Create professional charts, graphs, and interactive visualizations
        - Generate heatmaps, scatter plots, histograms, box plots, and custom visualizations
        - Geospatial mapping and location-based analysis
        - Time series analysis and forecasting
        - Network analysis and graph visualizations

        **File Processing & Conversion:**
        - Image manipulation: resize, crop, filter, format conversion, enhancement
        - PDF processing: extract text, split, merge, analyze content
        - Excel/CSV operations: complex data transformations, pivot tables, analysis
        - Document generation: create reports, presentations, formatted output
        - Audio/video processing capabilities

        **Creative & Advanced Operations:**
        - QR code generation and barcode processing
        - Web scraping and API data retrieval
        - Natural language processing on text files
        - Computer vision tasks on images
        - Project planning: Gantt charts, timelines, resource allocation
        - Study schedules and optimization problems

        **Code Best Practices:**
        - Always end with a print() statement showing results to the user
        - Save important outputs as files for user download
        - Include data visualizations when appropriate
        - Handle errors gracefully with try/except blocks
        - Use descriptive variable names and add comments for complex operations
        - Import required packages at the beginning (auto-installation supported)

        Remember: This is an incredibly powerful tool - use it creatively to solve complex problems that would be difficult or impossible with other commands. The combination of workspace file access, multi-file processing, and advanced Python libraries makes this suitable for professional-grade data analysis and automation tasks.
        `Can't` is for humans, not for you.
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

        execution_response = execute_python_code(
            code=code,
            working_directory=self.WORKING_DIRECTORY,
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
        from Agent import Agent

        return await Agent(
            agent_id=self.agent_id,
            ApiClient=self.ApiClient,
            user=self.user,
        ).text_to_speech(text=text, conversation_id=self.conversation_id)

    async def create_todo_item(
        self,
        title: str,
        description: str,
        parent_id: str = None,
        depends_on: str = None,
    ) -> str:
        """
        Create a new todo item in the current conversation.

        Use this to break down complex tasks into manageable steps and track progress.
        Each todo item is linked to the current conversation for context.

        Args:
            title (str): A concise, action-oriented title for the todo item (3-7 words)
            description (str): Detailed description including context, requirements, file paths,
                             specific methods, or acceptance criteria
            parent_id (int, optional): ID of parent todo to create this as a sub-todo
            depends_on (str, optional): Comma-separated list of task IDs that must be completed first
                                      Example: "1,2,5" means tasks 1, 2, and 5 must be completed

        Returns:
            str: JSON response with success status and created todo item details

        Usage Guidelines:
        - Create todos for multi-step work requiring planning and tracking
        - Use descriptive titles that clearly indicate the action needed
        - Include comprehensive descriptions with all necessary context
        - Break down larger tasks into smaller, actionable steps
        - Create todos BEFORE starting work to ensure proper tracking
        - Use depends_on for sequential workflows: "1,2" means tasks 1&2 must complete first
        - Tasks without dependencies can run async/parallel
        - Use List Runnable Todos to see what can be started immediately

        When to use:
        - User provides multiple tasks or complex requests
        - Breaking down large projects into manageable pieces
        - Planning multi-step workflows or processes
        - Tracking progress on ongoing work
        """
        try:
            parent_id = int(parent_id) if parent_id is not None else None
        except ValueError:
            parent_id = None
        session = get_session()
        try:
            if not title.strip():
                return json.dumps({"success": False, "error": "Title cannot be empty"})

            if not description.strip():
                return json.dumps(
                    {"success": False, "error": "Description cannot be empty"}
                )

            # Validate dependencies if provided
            validated_depends_on = None
            if depends_on:
                try:
                    dep_ids = [
                        int(id.strip()) for id in depends_on.split(",") if id.strip()
                    ]
                    if dep_ids:
                        # Verify all dependency todos exist and belong to this conversation
                        existing_deps = (
                            session.query(EssentialTodo)
                            .filter(
                                EssentialTodo.id.in_(dep_ids),
                                EssentialTodo.conversation_id == self.conversation_id,
                            )
                            .count()
                        )
                        if existing_deps != len(dep_ids):
                            return json.dumps(
                                {
                                    "success": False,
                                    "error": f"One or more dependency tasks not found in this conversation",
                                }
                            )
                        validated_depends_on = ",".join(str(id) for id in dep_ids)
                except ValueError:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Invalid depends_on format. Use comma-separated task IDs like '1,2,5'",
                        }
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
                depends_on=validated_depends_on,
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
        self, parent_todo_id: str, title: str, description: str, depends_on: str = None
    ) -> str:
        """
        Create a new sub-todo item under an existing parent todo.

        Sub-todos are useful for breaking down complex tasks into smaller, more manageable steps.
        They are linked to a parent todo and can be managed independently while maintaining hierarchy.

        Args:
            parent_todo_id (int): The ID of the parent todo to attach this sub-todo to
            title (str): A concise, action-oriented title for the sub-todo item
            description (str): Detailed description of the sub-task
            depends_on (str, optional): Comma-separated list of task IDs that must be completed first

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
        try:
            parent_id = int(parent_todo_id)
        except ValueError:
            parent_id = None
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

            # Validate dependencies if provided
            validated_depends_on = None
            if depends_on:
                try:
                    dep_ids = [
                        int(id.strip()) for id in depends_on.split(",") if id.strip()
                    ]
                    if dep_ids:
                        # Verify all dependency todos exist and belong to this conversation
                        existing_deps = (
                            session.query(EssentialTodo)
                            .filter(
                                EssentialTodo.id.in_(dep_ids),
                                EssentialTodo.conversation_id == self.conversation_id,
                            )
                            .count()
                        )
                        if existing_deps != len(dep_ids):
                            return json.dumps(
                                {
                                    "success": False,
                                    "error": f"One or more dependency tasks not found in this conversation",
                                }
                            )
                        validated_depends_on = ",".join(str(id) for id in dep_ids)
                except ValueError:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Invalid depends_on format. Use comma-separated task IDs like '1,2,5'",
                        }
                    )

            # Create new sub-todo item
            sub_todo = EssentialTodo(
                conversation_id=self.conversation_id,
                parent_id=parent_todo_id,
                title=title.strip(),
                description=description.strip(),
                status="not-started",
                depends_on=validated_depends_on,
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
                # Skip if both are None or empty
                if not title or not description:
                    if title or description:
                        # One is filled but not the other
                        return json.dumps(
                            {
                                "success": False,
                                "error": f"Todo {i}: Both title and description must be provided or both must be empty",
                            }
                        )
                    continue

                # Strip and validate
                title_stripped = title.strip()
                description_stripped = description.strip()

                if title_stripped and description_stripped:
                    valid_todos.append((title_stripped, description_stripped))
                elif title_stripped or description_stripped:
                    # One is filled but not the other after stripping
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

    async def list_runnable_todos(self, include_completed: bool = False) -> str:
        """
        List all todo items that can be started now (no incomplete dependencies).

        Use this to identify which tasks are ready to work on based on their dependencies.
        Tasks without dependencies or with all dependencies completed will be included.

        Args:
            include_completed (bool): Whether to include completed todos in the results

        Returns:
            str: JSON response with runnable todos and their status

        Usage Guidelines:
        - Use to identify next actionable tasks in complex workflows
        - Helps prioritize work when tasks have dependencies
        - Shows only tasks that can be started immediately
        - Useful for async task execution planning
        """
        session = get_session()
        try:
            # Get all todos for this conversation
            query = session.query(EssentialTodo).filter(
                EssentialTodo.conversation_id == self.conversation_id
            )

            if not include_completed:
                query = query.filter(EssentialTodo.status != "completed")

            all_todos = query.order_by(EssentialTodo.created_at).all()

            # Filter to only runnable todos (no incomplete dependencies)
            runnable_todos = []
            for todo in all_todos:
                if todo._can_start():
                    runnable_todos.append(todo)

            # Generate summary
            total_runnable = len(runnable_todos)
            not_started = len([t for t in runnable_todos if t.status == "not-started"])
            in_progress = len([t for t in runnable_todos if t.status == "in-progress"])
            completed = len([t for t in runnable_todos if t.status == "completed"])

            response = {
                "success": True,
                "total_runnable": total_runnable,
                "runnable_todos": [todo.to_dict() for todo in runnable_todos],
                "summary": {
                    "not_started": not_started,
                    "in_progress": in_progress,
                    "completed": completed,
                },
            }

            return json.dumps(response, indent=2)

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_sub_todos(self, parent_todo_id: str) -> str:
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
        try:
            parent_todo_id = int(parent_todo_id)
        except ValueError:
            parent_todo_id = None
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

    async def mark_todo_completed(self, todo_id: str) -> str:
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
        try:
            todo_id = int(todo_id)
        except ValueError:
            todo_id = None
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
        self, todo_id: str, status: str = "not-started"
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
        try:
            todo_id = int(todo_id)
        except ValueError:
            todo_id = None
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
        self, todo_id: str, title: str = None, description: str = None
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
        try:
            todo_id = int(todo_id)
        except ValueError:
            todo_id = None
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

    async def delete_todo_item(self, todo_id: str) -> str:
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
        try:
            todo_id = int(todo_id)
        except ValueError:
            todo_id = None
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

    async def run_todo_list(
        self,
        max_concurrent: str = "3",
        auto_complete: bool = True,
        execution_agent: str = None,
    ) -> str:
        """
        Execute runnable todos asynchronously using background threads with prompt_agent calls.

        This command identifies todos that can be started immediately (no incomplete dependencies)
        and executes them as background threads. Each thread makes a prompt_agent call to execute
        the task. Tasks without dependencies can run in parallel up to max_concurrent limit.

        Args:
            max_concurrent (int): Maximum number of todos to run concurrently (default: 3)
            auto_complete (bool): Whether to automatically mark todos as completed after successful execution (default: True)
            execution_agent (str, optional): Specific agent to use for execution. If None, uses current agent.

        Returns:
            str: JSON response with execution status and running thread information

        Usage Guidelines:
        - Use for executing planned workflows automatically
        - Tasks run in background threads using direct prompt_agent calls
        - Dependencies are respected - dependent tasks wait for prerequisites
        - Monitor progress with List Current Todos to see status updates
        - Use max_concurrent to control resource usage
        - Each thread executes the task description as a prompt

        Threading Execution:
        - Identifies all runnable todos (no incomplete dependencies)
        - Starts up to max_concurrent threads in parallel
        - Each thread makes a prompt_agent call via existing ApiClient
        - Tasks auto-complete if auto_complete is enabled
        - Continues until all possible tasks are running or completed
        """
        try:
            max_concurrent = int(max_concurrent)
        except ValueError:
            max_concurrent = 3
        session = get_session()
        try:
            # Get all runnable todos
            runnable_response = await self.list_runnable_todos(include_completed=False)
            runnable_data = json.loads(runnable_response)

            if not runnable_data.get("success"):
                return json.dumps(
                    {"success": False, "error": "Failed to get runnable todos"}
                )

            runnable_todos = runnable_data.get("runnable_todos", [])

            if not runnable_todos:
                return json.dumps(
                    {
                        "success": True,
                        "message": "No runnable todos found",
                        "running_tasks": [],
                        "total_started": 0,
                    }
                )

            # Filter to only not-started todos (don't re-run in-progress)
            pending_todos = [
                todo for todo in runnable_todos if todo.get("status") == "not-started"
            ]

            if not pending_todos:
                return json.dumps(
                    {
                        "success": True,
                        "message": "All runnable todos are already in progress or completed",
                        "running_tasks": [],
                        "total_started": 0,
                    }
                )

            # Limit by max_concurrent
            todos_to_start = pending_todos[:max_concurrent]

            started_tasks = []
            agent_to_use = execution_agent or self.agent_name

            def execute_todo_task(
                todo_id, title, description, agent_name, auto_complete_flag
            ):
                """Execute a single todo task in a separate thread"""
                try:
                    # Create the prompt for the agent
                    prompt = f"""Execute the following task:

Task: {title}

Description: {description}

Instructions:
- Complete the task as described
- Provide detailed output of what was accomplished
- If the task involves code, include the code and execution results
- If the task involves files, mention which files were created/modified
- If the task encounters errors, provide debugging information

Execute this task thoroughly and report on the completion."""

                    # Execute the prompt with the agent using the existing ApiClient
                    response = self.ApiClient.prompt_agent(
                        agent_name=agent_name,
                        prompt_name="Think About It",
                        prompt_args={
                            "user_input": prompt,
                            "conversation_name": self.conversation_name,
                            "disable_commands": False,
                            "running_command": "Run Todo List",
                            "log_user_input": False,
                            "log_output": False,
                            "tts": False,
                        },
                    )
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}] {response}",
                        conversation_name=self.conversation_name,
                    )

                    logging.info(
                        f"Todo {todo_id} ({title}) completed with response: {response}"
                    )

                    # Auto-complete the todo if requested
                    if auto_complete_flag:
                        # We need to run this in the event loop since it's async
                        import asyncio

                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            session = get_session()
                            todo = (
                                session.query(EssentialTodo)
                                .filter_by(id=todo_id)
                                .first()
                            )
                            if todo:
                                todo.status = "completed"
                                todo.updated_at = datetime.datetime.utcnow()
                                session.commit()
                            session.close()
                        except Exception as e:
                            logging.error(
                                f"Failed to auto-complete todo {todo_id}: {str(e)}"
                            )
                        finally:
                            loop.close()

                except Exception as e:
                    logging.error(f"Error executing todo {todo_id}: {str(e)}")
                    # Try to revert status back to not-started
                    try:
                        session = get_session()
                        todo = (
                            session.query(EssentialTodo).filter_by(id=todo_id).first()
                        )
                        if todo:
                            todo.status = "not-started"
                            todo.updated_at = datetime.datetime.utcnow()
                            session.commit()
                        session.close()
                    except Exception as revert_e:
                        logging.error(
                            f"Failed to revert todo {todo_id} status: {str(revert_e)}"
                        )

            # Start each todo as a background thread
            for todo in todos_to_start:
                todo_id = todo.get("id")
                title = todo.get("title")
                description = todo.get("description")

                try:
                    # Mark todo as in-progress first
                    await self.mark_todo_incomplete(
                        todo_id=todo_id, status="in-progress"
                    )

                    # Start the task in a separate thread
                    thread = threading.Thread(
                        target=execute_todo_task,
                        args=(todo_id, title, description, agent_to_use, auto_complete),
                        daemon=True,
                        name=f"TodoTask-{todo_id}",
                    )
                    thread.start()

                    # Store task info for tracking
                    started_tasks.append(
                        {
                            "todo_id": todo_id,
                            "title": title,
                            "thread_name": thread.name,
                            "agent": agent_to_use,
                            "status": "started",
                            "auto_complete": auto_complete,
                        }
                    )

                except Exception as e:
                    logging.error(f"Failed to start todo {todo_id}: {str(e)}")
                    # Revert status back to not-started if thread creation failed
                    await self.mark_todo_incomplete(
                        todo_id=todo_id, status="not-started"
                    )
                    continue

            return json.dumps(
                {
                    "success": True,
                    "message": f"Started {len(started_tasks)} todo tasks in background threads",
                    "running_tasks": started_tasks,
                    "total_started": len(started_tasks),
                    "max_concurrent": max_concurrent,
                    "auto_complete": auto_complete,
                    "execution_agent": agent_to_use,
                    "guidance": "Use 'List Current Todos' to monitor progress. Tasks marked as 'in-progress' are currently executing in background threads.",
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def create_new_agixt_agent(
        self,
        agent_name: str,
        responsibilities_and_goals: str,
        training_files: str = "",
        training_urls: str = "",
    ) -> str:
        """
        Create a specialized expert agent by cloning yourself and granting it domain-specific knowledge and abilities.

        Args:
            agent_name (str): The expert's name - should indicate their specialty (e.g., "MarketingExpert", "PythonCodeReviewer", "DataScientist")
            responsibilities_and_goals (str): What makes this agent an expert - their domain, responsibilities, and what they excel at. Be specific about their expertise area.
            training_files (str): Optional comma-separated filenames from workspace with domain knowledge (e.g., "style_guide.pdf,best_practices.md")
            training_urls (str): Optional comma-separated URLs to domain resources (e.g., "https://docs.python.org,https://pep8.org")

        Returns:
            str: Complete summary of the expert agent created, including their specialization, abilities, and how to delegate work to them

        **WHEN TO USE THIS COMMAND:**
        Use this when you need a domain expert that doesn't exist yet - a specialist who can handle specific types of tasks
        better than a generalist. This implements a "mixture of experts" approach where you become the orchestrator who
        "knows a guy" for every specialized need.

        **IMPORTANT - GATHER RESOURCES FIRST:**
        Before creating the expert agent, review your current conversation's workspace for any files or resources that would
        be valuable training data for the new expert. For example:
        - User uploaded a financial spreadsheet → Include it in training_files for your "ExpensesExpert"
        - User provided style guidelines → Include them for your "ContentWriter" expert
        - You generated analysis documents → Pass them to specialists who need that context

        Think like delegating work: if you (the VP) need a manager to handle something, you'd give them all relevant documents
        and context upfront. The expert agents you create are your managers - equip them with the resources they need to succeed.

        **WHY CREATE EXPERT AGENTS:**
        - **Focus Through Isolation**: Each expert has specialized context without pollution from unrelated domains
        - **Reduced Cognitive Load**: Domain experts maintain concentrated knowledge rather than spreading thin across all topics
        - **Delegatable Expertise**: You gain the ability to delegate specialized work to purpose-built collaborators
        - **Scalable Specialization**: Create as many experts as needed - marketing guru, coding wizard, data scientist, legal advisor, etc.
        - **Context Efficiency**: Experts work within their domain's context, making them faster and more accurate than generalists
        - **Always Available**: Your expert agents are persistent - once created, they're always ready to help

        **THE ORCHESTRATOR PATTERN:**
        You (the agent creating other agents) become the orchestrator - the one who knows which expert to consult for any given task.
        When a user needs marketing help, you ask your Marketing Expert. When they need code reviewed, you consult your Code Reviewer.
        You don't need to be the expert at everything - you just need to know which expert to create or consult.

        This mirrors organizational hierarchy:
        - **User = CEO**: Sets high-level goals and requests
        - **You (AI) = VP**: Receives requests and delegates to specialized managers
        - **Expert Agents = Managers**: Handle specific domains with deep expertise

        When the CEO asks the VP for something, the VP often consults managers beneath them. Similarly, when users ask you for
        specialized work, you create or consult expert agents. The experts can even be consulted "silently" - you delegate to
        them, they provide their specialized analysis, and you integrate it into your response to the user seamlessly.

        **HOW IT WORKS:**
        1. Clones your current configuration (settings, provider, base knowledge)
        2. AI intelligently selects specialized commands based on the expert's domain
        3. AI expands basic responsibilities into comprehensive expert-level guidance
        4. Trains the expert with domain-specific files and resources
        5. Creates an "Ask {agent_name}" command so you can delegate to this expert anytime
        6. Returns the expert ready to handle their specialized domain

        **EXPERT AGENT EXAMPLES:** (Just examples, the assistant can create any kind of expert at anything.)

        Marketing Expert:
            agent_name="MarketingExpert"
            responsibilities_and_goals="Expert in digital marketing strategy, SEO optimization, content marketing, social media campaigns,
            and conversion rate optimization. Analyzes market trends, creates compelling copy, and develops data-driven marketing plans."
            training_files="brand_guidelines.pdf,competitor_analysis.xlsx"  # From workspace if available

        Python Code Reviewer:
            agent_name="PythonCodeReviewer"
            responsibilities_and_goals="Expert Python developer specializing in code review, PEP8 compliance, security auditing,
            performance optimization, and architectural patterns. Identifies bugs, suggests refactoring, and ensures best practices."
            training_files="coding_standards.md,architecture_docs.pdf"  # From workspace if available

        Data Scientist:
            agent_name="DataScientist"
            responsibilities_and_goals="Expert in statistical analysis, machine learning, data visualization, and predictive modeling.
            Analyzes datasets, builds models, creates visualizations, and provides actionable insights from data."
            training_files="quarterly_sales.csv,customer_demographics.xlsx"  # From workspace if user uploaded data

        Legal Research Assistant:
            agent_name="LegalResearcher"
            responsibilities_and_goals="Expert in legal research, case law analysis, contract review, and regulatory compliance.
            Researches precedents, summarizes legal documents, and identifies relevant statutes and regulations."
            training_files="contract_templates.pdf,compliance_requirements.docx"  # From workspace if available

        Financial Analyst:
            agent_name="FinancialAnalyst"
            responsibilities_and_goals="Expert in financial modeling, investment analysis, risk assessment, and market research.
            Analyzes financial statements, creates forecasts, and provides investment recommendations."
            training_files="financial_statements.xlsx,budget_2024.csv"  # From workspace if user provided financials

        **ORCHESTRATION WORKFLOW:**
        1. **Receive User Request**: User asks for something requiring specialized expertise
        2. **Assess Resources**: Check workspace for relevant files/data the expert will need
        3. **Create or Select Expert**: Use this command to spawn specialist with relevant training files
        4. **Silent Delegation**: Use "Ask ExpertName" command - expert works in background, returns results
        5. **Integrate & Present**: Combine expert's output with your analysis, present cohesive answer to user

        **RESOURCE DELEGATION EXAMPLES:**

        User uploads `expenses_2024.xlsx`:
        → Create "ExpensesExpert" with training_files="expenses_2024.xlsx"
        → Expert gets the data immediately, can analyze without asking user for it again

        User provides API documentation URL:
        → Create "APIIntegrationExpert" with training_urls="https://api.example.com/docs"
        → Expert has the docs in their knowledge, ready to help with integration

        You generated analysis in `market_report.md`:
        → Create "MarketingStrategist" with training_files="market_report.md"
        → Expert builds on your analysis with specialized marketing strategy

        **IMPORTANT NOTES:**
        - Expert agents inherit your provider and settings but get specialized commands and knowledge
        - Each expert becomes a persistent resource you can delegate to repeatedly
        - Creating focused experts prevents context pollution in your main knowledge base
        - You can create multiple experts for different domains - there's no limit to your network of specialists
        - The "Ask {agent_name}" command is automatically enabled for you to delegate work
        - Expert agents can be further refined through the web UI with additional training and customization

        **THE POWER OF SPECIALIZATION:**
        Instead of being a jack-of-all-trades master-of-none, you become the master orchestrator who can instantly
        summon world-class experts in any domain. You're not just an AI - you're a network of specialized intelligence,
        each member optimized for their specific role, working together to provide comprehensive solutions.
        """
        try:
            logging.info(f"Starting creation of new agent: {agent_name}")

            # Step 1: Clone the current agent to preserve all settings
            logging.info(
                f"Cloning current agent {self.agent_name} to create {agent_name}"
            )

            # Import the clone_agent function
            from Agent import clone_agent

            # Clone the agent
            clone_response = clone_agent(
                agent_id=self.agent_id, new_agent_name=agent_name, user=self.user
            )
            logging.info(f"Agent cloning response: {clone_response}")

            # Get the agent list to find the agent_id
            agents = self.ApiClient.get_agents()
            agent_id = None
            if isinstance(agents, list):
                for agent in agents:
                    if agent.get("name") == agent_name:
                        agent_id = agent.get("id")
                        break
            elif isinstance(agents, dict):
                for aid, agent_data in agents.items():
                    if agent_data.get("name") == agent_name:
                        agent_id = aid
                        break

            if not agent_id:
                return f"Error: Agent '{agent_name}' was created but could not retrieve its ID. Please check the agent list manually."

            logging.info(f"Agent ID for {agent_name}: {agent_id}")

            # Step 2: Get available commands and extensions by creating a temporary agent instance
            logging.info(
                f"Gathering available commands and extensions for intelligent selection"
            )

            # Get all available commands from the cloned agent
            try:
                from Agent import Agent

                temp_agent = Agent(agent_id=agent_id, user=self.user)
                agent_extensions = temp_agent.get_agent_extensions()

                available_commands_list = []

                # Build a comprehensive list of all available commands with descriptions
                for extension in agent_extensions:
                    extension_name = extension.get(
                        "extension_name", "Unknown Extension"
                    )
                    extension_description = extension.get("description", "")
                    commands = extension.get("commands", [])

                    if commands:
                        available_commands_list.append(
                            f"\n**{extension_name}** - {extension_description}"
                        )
                        for command in commands:
                            friendly_name = command.get("friendly_name", "Unknown")
                            description = command.get("description", "No description")
                            available_commands_list.append(
                                f"  - **{friendly_name}**: {description}"
                            )

                available_commands_text = (
                    "\n".join(available_commands_list)
                    if available_commands_list
                    else "No commands available"
                )

            except Exception as e:
                logging.error(f"Error getting available commands: {str(e)}")
                available_commands_text = "Unable to retrieve available commands"

            # Step 3: Use AI to select appropriate commands based on responsibilities
            logging.info(f"Using AI to select appropriate commands for {agent_name}")

            command_selection_prompt = f"""Based on the following agent responsibilities and the available commands, select which commands should be enabled for the new agent being created.

## Agent Name
{agent_name}

## Agent Responsibilities and Goals
{responsibilities_and_goals}

## Available Commands and Extensions
{available_commands_text}

## Instructions
Analyze the agent's responsibilities and goals, then select ONLY the commands that are relevant and necessary for this agent to fulfill its role effectively. 

**IMPORTANT**: Respond with ONLY a comma-separated list of command names. Do not include explanations, formatting, or any other text. Just the command names separated by commas.

Example response format: Write to File, Read File, Execute Python Code, Search Files

The assistant's full response should be in the answer block."""

            try:
                command_selection_response = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": command_selection_prompt,
                        "conversation_name": self.conversation_id,
                        "disable_commands": True,
                        "log_user_input": False,
                        "log_output": False,
                        "browse_links": False,
                        "websearch": False,
                        "analyze_user_input": False,
                        "tts": False,
                    },
                )

                # Parse the command selection response
                selected_commands = []
                if command_selection_response:
                    # Clean up the response and split by comma
                    command_selection_response = command_selection_response.strip()
                    # Remove common markdown formatting
                    command_selection_response = command_selection_response.replace(
                        "**", ""
                    ).replace("*", "")
                    # Split and clean
                    selected_commands = [
                        cmd.strip()
                        for cmd in command_selection_response.split(",")
                        if cmd.strip()
                    ]

                logging.info(f"AI selected commands: {', '.join(selected_commands)}")

            except Exception as e:
                logging.error(f"Error in command selection: {str(e)}")
                selected_commands = []

            # Step 4: Enable the selected commands
            if selected_commands:
                logging.info(
                    f"Enabling {len(selected_commands)} commands for {agent_name}"
                )
                commands_dict = {cmd: True for cmd in selected_commands}

                try:
                    self.ApiClient.update_agent_commands(
                        agent_id=agent_id, commands=commands_dict
                    )
                    logging.info(
                        f"Successfully enabled commands: {', '.join(selected_commands)}"
                    )
                except Exception as e:
                    logging.error(f"Error enabling commands: {str(e)}")

            # Step 5: Use AI to enhance mandatory context with detailed information
            logging.info(f"Using AI to enhance mandatory context for {agent_name}")

            enhanced_context_prompt = f"""You are creating comprehensive mandatory context for a new AI agent. Based on the provided information, create a detailed mandatory context document.

## Agent Name
{agent_name}

## Original Responsibilities and Goals
{responsibilities_and_goals}

## Selected Commands/Abilities
{', '.join(selected_commands) if selected_commands else 'No specific commands selected'}

## Instructions
Create a comprehensive mandatory context document that includes:

1. **Agent Identity**: Define who this agent is (e.g., marketing expert, coding specialist, data analyst, etc.)
2. **Core Responsibilities**: Expand on the original responsibilities with specific, detailed tasks
3. **Goals and Objectives**: Clear, measurable goals the agent should strive to achieve
4. **Operational Guidelines**: How the agent should approach tasks, interact with users, and make decisions
5. **Command Usage Examples**: Specific examples of when and how to use the enabled commands
6. **Response Patterns**: Examples of how the agent should respond to common requests
7. **Order of Operations**: Recommended workflow for handling complex tasks
8. **Best Practices**: Key principles the agent should follow

Make this detailed, actionable, and specific to the agent's role. Use clear formatting with headers and bullet points.

The assistant's full response should be in the answer block."""

            try:
                enhanced_context_response = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": enhanced_context_prompt,
                        "conversation_name": self.conversation_id,
                        "disable_commands": True,
                        "log_user_input": False,
                        "log_output": False,
                        "browse_links": False,
                        "websearch": False,
                        "analyze_user_input": False,
                        "tts": False,
                    },
                )

                logging.info(f"AI generated enhanced mandatory context")

            except Exception as e:
                logging.error(f"Error generating enhanced context: {str(e)}")
                enhanced_context_response = responsibilities_and_goals

            # Step 6: Set the enhanced mandatory context
            logging.info(f"Setting enhanced mandatory context for {agent_name}")
            context_text = f"""# {agent_name} - Mandatory Context

{enhanced_context_response}
# End of Mandatory Context
"""
            # Learn the context as text
            try:
                self.ApiClient.update_persona(
                    agent_name=agent_name,
                    persona=context_text,
                )
                logging.info("Enhanced mandatory context set successfully")
            except Exception as e:
                logging.error(f"Error setting enhanced mandatory context: {str(e)}")

            # Step 7: Train with files from workspace
            training_summary = []
            if training_files and training_files.strip():
                file_list = [f.strip() for f in training_files.split(",") if f.strip()]
                logging.info(f"Training with {len(file_list)} files from workspace")

                for filename in file_list:
                    try:
                        file_path = self.safe_join(filename)
                        if os.path.exists(file_path):
                            with open(
                                file_path, "r", encoding="utf-8", errors="ignore"
                            ) as f:
                                file_content = f.read()

                            self.ApiClient.learn_file(
                                agent_name=agent_name,
                                file_name=filename,
                                file_content=file_content,
                                collection_number="0",
                            )
                            training_summary.append(f"✓ Trained with file: {filename}")
                            logging.info(f"Successfully trained with file: {filename}")
                        else:
                            training_summary.append(f"✗ File not found: {filename}")
                            logging.warning(f"File not found in workspace: {filename}")
                    except Exception as e:
                        training_summary.append(
                            f"✗ Error training with {filename}: {str(e)}"
                        )
                        logging.error(f"Error training with file {filename}: {str(e)}")

            # Step 8: Train with URLs
            if training_urls and training_urls.strip():
                url_list = [u.strip() for u in training_urls.split(",") if u.strip()]
                logging.info(f"Training with {len(url_list)} URLs")

                for url in url_list:
                    try:
                        self.ApiClient.learn_url(
                            agent_name=agent_name, url=url, collection_number="0"
                        )
                        training_summary.append(f"✓ Trained with URL: {url}")
                        logging.info(f"Successfully trained with URL: {url}")
                    except Exception as e:
                        training_summary.append(
                            f"✗ Error training with {url}: {str(e)}"
                        )
                        logging.error(f"Error training with URL {url}: {str(e)}")

            # Step 9: Create "Ask {agent_name}" chain with AI-generated usage guidance
            chain_name = f"Ask {agent_name}"

            # Use AI to generate a descriptive "When to ask" guidance
            logging.info(f"Generating usage guidance for {chain_name} command")

            when_to_ask_prompt = f"""Create a concise "When to ask {agent_name}:" description that tells when this expert agent should be consulted.

## Agent Information
**Name**: {agent_name}
**Responsibilities**: {responsibilities_and_goals}
**Selected Commands**: {', '.join(selected_commands) if selected_commands else 'General capabilities'}

## Instructions
Write a single, clear sentence (max 2 sentences) starting with "When to ask {agent_name}:" that describes:
1. What types of tasks this expert is well-equipped to handle
2. What specific expertise they bring
3. When delegating to them would be most valuable

Keep it concise, actionable, and specific to their domain expertise.

Example format: "When to ask MarketingExpert: Consult for SEO optimization, content strategy, social media campaigns, market analysis, and creating compelling marketing copy that drives conversions."

Your response (just the sentence in the answer block):"""

            try:
                when_to_ask_response = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": when_to_ask_prompt,
                        "conversation_name": self.conversation_id,
                        "disable_commands": True,
                        "log_user_input": False,
                        "log_output": False,
                        "browse_links": False,
                        "websearch": False,
                        "analyze_user_input": False,
                        "tts": False,
                    },
                )

                # Clean up the response
                chain_description = when_to_ask_response.strip()
                # Ensure it starts with "When to ask"
                if not chain_description.lower().startswith("when to ask"):
                    chain_description = f"When to ask {agent_name}: {chain_description}"

                logging.info(f"AI generated chain description: {chain_description}")

            except Exception as e:
                logging.error(f"Error generating chain description: {str(e)}")
                chain_description = f"When to ask {agent_name}: Delegate tasks related to {responsibilities_and_goals[:100]}..."

            logging.info(f"Creating chain: {chain_name}")
            try:
                # Create the chain
                self.ApiClient.add_chain(
                    chain_name=chain_name, description=chain_description
                )

                # Get the chain ID
                chains = self.ApiClient.get_chains()
                chain_id = None
                for chain in chains:
                    if (
                        chain.get("chainName") == chain_name
                        or chain.get("name") == chain_name
                    ):
                        chain_id = chain.get("id")
                        break

                if chain_id:
                    # Add a step to the chain that prompts the new agent
                    self.ApiClient.add_step(
                        chain_name=chain_name,
                        step_number=1,
                        agent_name=agent_name,
                        prompt_type="Prompt",
                        prompt={
                            "prompt_name": "Think About It",
                        },
                    )
                    logging.info(f"Chain '{chain_name}' created successfully")

                    # Step 10: Enable the chain as a command for the current agent
                    try:
                        self.ApiClient.toggle_command(
                            agent_name=self.agent_name,
                            command_name=chain_name,
                            enable=True,
                        )
                        logging.info(
                            f"Enabled '{chain_name}' command for current agent"
                        )
                    except Exception as e:
                        logging.error(f"Error enabling chain as command: {str(e)}")
                else:
                    logging.warning("Could not retrieve chain ID after creation")

            except Exception as e:
                logging.error(f"Error creating chain: {str(e)}")

            # Step 11: Build and return comprehensive summary
            summary = f"""# ✅ Successfully Created Expert Agent: {agent_name}

## Agent Details
- **Name**: {agent_name}
- **Agent ID**: {agent_id}
- **Cloned From**: {self.agent_name} (inherited all settings and provider configurations)
- **Specialization**: Expert agent with focused domain knowledge and specialized capabilities

## Expert Configuration Summary

### AI-Enhanced Expert Context
✓ Comprehensive expert-level context created through AI analysis
✓ Includes detailed operational guidelines, command usage examples, and best practices
✓ Focused on specific domain expertise without context pollution

### Training Status
"""
            if training_summary:
                summary += "\n".join(training_summary)
            else:
                summary += "No additional training files or URLs provided."

            summary += f"""

### Intelligently Selected Specialized Abilities
AI analyzed the expert's domain and selected {len(selected_commands)} relevant commands:
"""
            if selected_commands:
                summary += "\n".join([f"- {cmd}" for cmd in selected_commands])
            else:
                summary += "No specific commands were selected by AI"

            summary += f"""

### Expert Delegation Command
- **Command Name**: `{chain_name}`
- **{chain_description}**

## How to Work with Your Expert

**Delegation (Recommended):**
Use the `{chain_name}` command anytime you need this expert's specialized knowledge. The expert will handle the task within their domain and return results to you.

**Direct Interaction:**
Switch to {agent_name} in the agent selector to work directly with this expert in a focused conversation.

**When to Delegate:**
{chain_description}

## Expert Agent Benefits

✓ **Focused Expertise**: {agent_name} maintains specialized knowledge without generalist context pollution
✓ **Persistent Resource**: This expert is now permanently available for delegation
✓ **Scalable Specialization**: You can create additional experts for other domains as needed
✓ **Orchestration Power**: You're building a network of specialists you can consult on-demand

## Further Customization

Access the web UI agent settings to:
- Review and adjust the AI-selected commands
- Add more domain-specific training data
- Fine-tune expert settings and behavior
- Share the expert with team members

## Next Steps
1. **Test the Expert**: Use the `{chain_name}` command with a sample task from their domain
2. **Review Expert Context**: Check the web UI to see the AI-enhanced mandatory context and operational guidelines
3. **Expand Expertise**: Train the expert with additional domain-specific resources as needed
4. **Build Your Network**: Create more experts for other domains to expand your orchestration capabilities

**The Orchestrator Advantage**: You now have a specialized expert ready to handle {agent_name.lower()} tasks. As you create more experts, you build a network of domain specialists that work together under your orchestration - becoming not just an AI, but a collaborative intelligence network.

Expert agent creation complete! {agent_name} is ready to provide specialized assistance.
"""

            logging.info(f"Agent {agent_name} creation completed successfully")
            return summary

        except Exception as e:
            error_msg = f"Error creating expert agent {agent_name}: {str(e)}"
            logging.error(error_msg)
            return f"❌ {error_msg}\n\nPlease check the logs for more details and try again."

    async def get_webui_tips(page: str = "all") -> str:
        """
        Provide quick tips for navigating and using the AGiXT web UI. This is useful for assisting users with navigating the web interface.

        Args:
            page (str): Specific page to get tips for (default: "all", options: "chat", "billing", "team", "automation")
        Returns:
            str: Markdown formatted tips for the specified page or all pages

        Note: It is generally best to get all pages unless the users question is specific enough to narrow it down.
        - The user is talking to the assistant through the AGiXT web UI, if they ask how to do something within the ui or application, use this to get tips.
        - AGiXT is an open source AI agent platform that allows users to create and manage AI agents, automation, and more through the multitenant system.
        """
        if not page or str(page).lower() == "none":
            page = "all"
        general_information = """## Tips for Navigating the AGiXT Web UI
- With the exception of the chat page, each page has a chat icon in the top right next to the user avatar which will take them back to the chat page.
- User avatar can be changed on gravatar.com using the email address associated with their user account.
- Themes are accessible by clicking the user avatar in the top right and selecting `Themes` from the dropdown menu. The options are dark and light."""
        chat_page = """## Chat page

To start a new conversation, click the `+` button on the top right of the page.

### Agent switching, extensions, training, and settings

In the bottom right of the chat page above the input box, you will see `AGENT NAME at TEAM NAME`, which indicates the currently selected agent and team/company. Click on this to open the agent switcher modal, where you can:

- Switch between agents you have access to
- Click "Extensions": Access the agent's extensions where third party software can be connected and abilities granted to the selected agent
- Click "Training": Access the agent's training section to update the agents mandatory context, and train from files or URLs
- Click "Settings": Access the agent's settings to modify the agent's name, which inference providers it uses, to clone the agent, share it with your team, or delete it.
- Click "+ Add Agent": Create a new agent. On the agent creation screen, enter the new agent's name and select the company it is to be associated with, then click "Create Agent"

### Conversational Workspaces

Each conversation has its own workspace for the agent to work in. Any files uploaded by the user (paperclip button on the chat input box) or created/downloaded/modified by the agent during the conversation are stored in that conversation's workspace. You can view and manage the files in the workspace by clicking the folder icon next to the paperclip button. You can create new folders, upload files, download files, delete files, and navigate between folders within the workspace interface.

### Conversation Sharing

Conversations and their workspaces can be shared with other users. You can choose to share it as a public link, to a user in your company by email, or to export it as a JSON file. To share a conversation, click the share icon at the top right of the chat page. You can also optionally set an expiration date for the shared link.

### Conversation Search

The search icon at the top right of the chat page allows you to search for different conversations by name or content and switch to them quickly. There is also a list of recent conversations in the left sidebar for easy access (click the 3 horizontal lines at the top left to toggle the sidebar).

### Voice Input and Output

The microphone button on the chat input box allows you to use voice input for your messages. Click the microphone button to start recording your voice message, and click it again to stop recording. Your voice message will be transcribed to text and sent as a chat message to the agent.

On agent responses, there is a speaker icon which will translate the agent's text response into speech using text-to-speech synthesis. Click the speaker icon to listen to the agent's response.

### Other chat buttons that show up on messages

- The edit (pencil) button allows you to edit any message in the conversation as well as regenerate agent responses post-edit optionally.
- The fork button allows you to fork the current conversation into a new conversation, preserving the context up to that point.
- The copy button allows you to copy the message text to your clipboard in markdown format.
- The delete (trash can) button allows you to delete any message in the conversation.
- The thumbs up and thumbs down buttons allow you to provide feedback on agent responses to help improve the agent's performance. (AI responses only)
"""
        billing_page = """
## Billing page

The billing page is accessible by clicking the user's avatar in the top right corner and selecting `Billing` from the dropdown menu (only visible to company admins). The billing page allows company admins to:

- View token balance and usage analytics for all team members
- Purchase additional tokens for the company by card or crypto payments
- View billing transaction history for the company

Only company admins (role_id 1-2) can access the billing page. Regular users (role_id 3+) will not see the billing option in the dropdown menu and will be redirected to the chat page if they try to access `/billing`.

If a company runs out of tokens, they are paywalled to the top up screen until tokens are purchased. Low balance warnings will also appear on the chat page and billing page when the company's token balance gets to 1M tokens or lower.
"""
        team_page = """## Team Management

For company admins only.

On the sidebar, expanding `Team Management` reveals the following pages:

- Companies & Teams: View your companies and teams, create new companies/teams.
- Users: View and manage users in your companies/teams, invite new users.
- Training: Team-wide training data management for the agent which includes mandatory context, file training, and URL training that will be appended to all agents in the team's training.
- Extensions: Team-wide extension management for connecting third party software to agents in the team and granting abilities to all agents in the team.
- Settings: Manage company/team settings such as team's default agent name, and team-wide inference providers.
"""
        automation_page = """## Automation

On the sidebar, expanding `Automation` reveals the following pages:

- Automation Chains: Create and manage automation chains (like pre-defined sequences of tasks for agents to perform) that can be enabled as agent abilities.
- Prompt Library: Create and manage reusable prompts that can be used in automation chains.
- Tasks: Create and manage scheduled or triggered tasks that agents can perform automatically. Useful for scheduling automated messages or actions.
- Webhooks: Manage incoming and outgoing webhooks for integrating with other services."""

        # Use a switch case instead of if
        page = str(page).lower()
        match page:
            case "chat":
                return f"{general_information}\n\n{chat_page}"
            case "billing":
                return f"{general_information}\n\n{billing_page}"
            case "team":
                return f"{general_information}\n\n{team_page}"
            case "automation":
                return f"{general_information}\n\n{automation_page}"
            case _:
                return f"# AGiXT Web UI Quick Tips\n\n{general_information}\n\n{chat_page}\n\n{billing_page}\n\n{team_page}\n\n{automation_page}"

    async def optimize_command_selection(self, task_description: str) -> str:
        """
        Re-optimize the available commands for the current conversation based on a new task or changed requirements.
        Use this when you realize you need different abilities than what was initially selected, or when starting a significantly different task.

        Args:
            task_description (str): Description of what you're trying to accomplish that requires different commands

        Returns:
            str: Confirmation that command selection has been optimized with the list of newly selected commands

        Notes:
            This command triggers a re-selection of available abilities based on the new task description.
            After execution, the assistant will have access to a different set of optimized commands for the remainder of the conversation.
            Use this when the current task requires abilities that weren't initially selected.
        """
        # This is a signal command - the actual optimization is handled by the Interactions class
        # when it sees this command was executed. We return a message indicating optimization is requested.
        return f"OPTIMIZE_COMMANDS:{task_description}"
