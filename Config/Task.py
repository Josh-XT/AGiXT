import os
import uuid
from Config import Config


class Task(Config):
    def __init__(self):
        self.AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo").lower()
        if not os.path.exists(f"model-prompts/{self.AI_MODEL}"):
            self.AI_MODEL = "default"
        with open(f"model-prompts/{self.AI_MODEL}/execute.txt", "r") as f:
            self.EXECUTION_PROMPT = f.read()
        with open(f"model-prompts/{self.AI_MODEL}/task.txt", "r") as f:
            self.TASK_PROMPT = f.read()
        with open(f"model-prompts/{self.AI_MODEL}/priority.txt", "r") as f:
            self.PRIORITY_PROMPT = f.read()

    def get_task_output(self, agent_name, primary_objective=None):
        if primary_objective is None:
            return "No primary objective specified."
        task_output_file = os.path.join(
            "agents", agent_name, "tasks", f"{primary_objective}.txt"
        )
        if os.path.exists(task_output_file):
            with open(task_output_file, "r") as f:
                task_output = f.read()
        else:
            task_output = ""
        return task_output

    def save_task_output(self, agent_name, task_output, primary_objective=None):
        # Check if agents/{agent_name}/tasks/task_name.txt exists
        # If it does, append to it
        # If it doesn't, create it
        if "tasks" not in os.listdir(os.path.join("agents", agent_name)):
            os.makedirs(os.path.join("agents", agent_name, "tasks"))
        if primary_objective is None:
            primary_objective = str(uuid.uuid4())
        task_output_file = os.path.join(
            "agents", agent_name, "tasks", f"{primary_objective}.txt"
        )
        with open(
            task_output_file,
            "a" if os.path.exists(task_output_file) else "w",
            encoding="utf-8",
        ) as f:
            f.write(task_output)
        return task_output
