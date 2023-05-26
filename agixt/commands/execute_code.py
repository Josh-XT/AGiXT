from Commands import Commands
from Config import Config
import os
import subprocess
import docker
from docker.errors import ImageNotFound
import logging

CFG = Config()


class execute_code(Commands):
    def __init__(self, **kwargs):
        self.commands = {
            "Execute Python File": self.execute_python_file,
            "Execute Shell": self.execute_shell,
        }

    def execute_python_file(self, file: str):
        logging.info(f"Executing file '{file}' in workspace '{CFG.WORKING_DIRECTORY}'")

        if not file.endswith(".py"):
            return "Error: Invalid file type. Only .py files are allowed."

        file_path = os.path.join(CFG.WORKING_DIRECTORY, file)

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

        try:
            client = docker.from_env()

            image_name = "python:3.10"
            try:
                client.images.get(image_name)
                logging.info(f"Image '{image_name}' found locally")
            except ImageNotFound:
                logging.info(
                    f"Image '{image_name}' not found locally, pulling from Docker Hub"
                )
                low_level_client = docker.APIClient()
                for line in low_level_client.pull(image_name, stream=True, decode=True):
                    status = line.get("status")
                    progress = line.get("progress")
                    if status and progress:
                        logging.info(f"{status}: {progress}")
                    elif status:
                        logging.info(status)

            container = client.containers.run(
                image_name,
                f"python {file}",
                volumes={
                    os.path.abspath(CFG.WORKING_DIRECTORY): {
                        "bind": "/workspace",
                        "mode": "ro",
                    }
                },
                working_dir="/workspace",
                stderr=True,
                stdout=True,
                detach=True,
            )

            container.wait()
            logs = container.logs().decode("utf-8")
            container.remove()

            return logs

        except Exception as e:
            return f"Error: {str(e)}"

    def execute_shell(self, command_line: str) -> str:
        current_dir = os.getcwd()
        os.chdir(current_dir)
        logging.info(
            f"Executing command '{command_line}' in working directory '{os.getcwd()}'"
        )
        result = subprocess.run(command_line, capture_output=True, shell=True)
        output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

        os.chdir(current_dir)

        return output

    @staticmethod
    def we_are_running_in_a_docker_container() -> bool:
        return os.path.exists("/.dockerenv")
