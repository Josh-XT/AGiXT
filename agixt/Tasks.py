from AGiXT import AGiXT
import re
import os
import json
import uuid
import yaml
from pathlib import Path
from Agent import Agent
from collections import deque


class Tasks:
    def __init__(self, agent_name: str = "AGiXT"):
        self.agent_name = agent_name
        self.agent = Agent(self.agent_name)
        self.primary_objective = None
        self.task_list = deque([])
        self.output_list = []
        self.stop_running_event = None

    def save_task(self):
        task_name = re.sub(
            r"[^\w\s]", "", self.primary_objective
        )  # remove non-alphanumeric & non-space characters
        task_name = task_name[:15]  # truncate to 15 characters

        # ensure the directories exist
        directory = Path(f"agents/{self.agent_name}")
        directory.mkdir(parents=True, exist_ok=True)

        # serialize the task state and save to a file
        task_state = {
            "task_name": task_name,
            "task_list": list(self.task_list),
            "output_list": self.output_list,
            "primary_objective": self.primary_objective,
        }
        with open(f"agents/{self.agent_name}/{task_name}.yaml", "w") as f:
            yaml.dump(task_state, f)

    def load_task(self, task_name):
        task_name = re.sub(
            r"[^\w\s]", "", task_name
        )  # remove non-alphanumeric & non-space characters
        task_name = task_name[:15]  # truncate to 15 characters

        try:
            with open(f"agents/{self.agent_name}/{task_name}.json", "r") as f:
                task_state = json.load(f)

            self.task_list = deque(task_state["task_list"])
            self.output_list = task_state["output_list"]
            self.primary_objective = task_state["primary_objective"]
            print(f"Successfully loaded task '{task_name}'.")

        except FileNotFoundError:
            print(f"No saved task found with the name '{task_name}'.")
        except Exception as e:
            print(f"An error occurred while loading the task: {e}")

    def get_status(self):
        try:
            return not self.stop_running_event.is_set()
        except:
            return False

    def get_output_list(self):
        return self.output_list

    def save_task_output(self, agent_name, task_output):
        # Check if agents/{agent_name}/tasks/task_name.txt exists
        # If it does, append to it
        # If it doesn't, create it
        if "tasks" not in os.listdir(os.path.join("agents", agent_name)):
            os.makedirs(os.path.join("agents", agent_name, "tasks"))
        if self.primary_objective is None:
            self.primary_objective = str(uuid.uuid4())
        task_output_file = os.path.join(
            "agents", agent_name, "tasks", f"{self.primary_objective}.yaml"
        )
        with open(
            task_output_file,
            "a" if os.path.exists(task_output_file) else "w",
            encoding="utf-8",
        ) as f:
            yaml.dump(task_output, f)
        return task_output

    def get_task_output(self):
        task_name = re.sub(
            r"[^\w\s]", "", self.primary_objective
        )  # remove non-alphanumeric & non-space characters
        task_name = task_name[:15]  # truncate to 15 characters

        try:
            with open(f"agents/{self.agent_name}/tasks/{task_name}.yaml", "r") as f:
                task_output = yaml.safe_load(f)

            print(f"Successfully loaded task output for '{task_name}'.")
            return task_output

        except FileNotFoundError:
            print(f"No saved task output found with the name '{task_name}'.")
            return None
        except Exception as e:
            print(f"An error occurred while loading the task output: {e}")
            return None

    def update_output_list(self, output):
        print(self.save_task_output(self.agent_name, output, self.primary_objective))

    def stop_tasks(self):
        if self.stop_running_event is not None:
            self.stop_running_event.set()
        self.task_list.clear()

    def run_task(
        self,
        objective,
        async_exec: bool = False,
        learn_file: str = "",
        smart: bool = False,
        load_task: str = "",
        **kwargs,
    ):
        if load_task != "":
            self.load_task(load_task)
            self.update_output_list(f"Loaded task '{load_task}'.\n\n")
        else:
            if self.task_list == deque([]) or self.task_list == []:
                self.task_list = deque(
                    [
                        {
                            "task_id": 1,
                            "task_name": "Develop a task list to complete the objective if necessary.  The plan is 'None' if not necessary.",
                        }
                    ]
                )
            self.primary_objective = objective
            if learn_file != "":
                learned_file = self.agent.memories.read_file(
                    task=objective, file_path=learn_file
                )
                if learned_file:
                    self.update_output_list(
                        f"Read file {learn_file} into memory for task {objective}.\n\n"
                    )
                else:
                    self.update_output_list(
                        f"Failed to read file {learn_file} into memory.\n\n"
                    )

            self.update_output_list(
                f"Starting task with objective: {self.primary_objective}.\n\n"
            )

        while not self.stop_running_event.is_set() and self.task_list:
            task = self.task_list.popleft()

            if task["task_name"] in ["None", "None.", ""]:
                self.stop_tasks()
                continue

            self.update_output_list(
                f"\nExecuting task {task['task_id']}: {task['task_name']}\n"
            )

            if smart:
                result = AGiXT(self.agent_name).smart_instruct(
                    task=task["task_name"],
                    shots=3,
                    async_exec=async_exec,
                    **kwargs,
                )
            else:
                result = AGiXT(self.agent_name).instruction_agent(
                    task=task["task_name"], **kwargs
                )

            self.update_output_list(f"\nTask Result:\n\n{result}\n")

            task_agent = AGiXT(self.agent_name).task_agent(
                result=result,
                task_description=task["task_name"],
                task_list=self.task_list,
            )
            new_tasks = deque(task_agent)
            self.update_output_list(f"\nNew Tasks:\n\n{new_tasks}\n")

            for new_task in new_tasks:
                new_task_id = len(self.task_list) + 1
                new_task.update({"task_id": new_task_id})
                self.task_list.append(new_task)

        if not self.task_list:
            self.stop_tasks()
        if self.stop_running_event.is_set():
            self.save_task()
        self.update_output_list("All tasks completed or stopped.")
