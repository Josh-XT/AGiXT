from AGiXT import AGiXT
import re
import os
import json
import yaml
from Agent import Agent
from collections import deque


class Tasks:
    def __init__(self, agent_name: str = "AGiXT"):
        self.agent_name = agent_name
        self.ai = AGiXT(self.agent_name)
        self.primary_objective = None
        self.task_list = deque([])
        self.output_list = []
        self.stop_running_event = False
        if not os.path.exists(f"agents/{self.agent_name}/tasks"):
            os.makedirs(f"agents/{self.agent_name}/tasks")

    def load_task(self):
        out_file = re.sub(r"[^\w\s]", "", self.primary_objective)
        out_file = out_file[:25]
        try:
            with open(f"agents/{self.agent_name}/{out_file}.json", "r") as f:
                task_state = json.load(f)

            self.task_list = deque(task_state["task_list"])
            self.output_list = task_state["tasks"]
            self.primary_objective = task_state["primary_objective"]
            print(f"Successfully loaded task '{out_file}'.")

        except FileNotFoundError:
            print(f"No saved task found with the name '{out_file}'.")
        except Exception as e:
            print(f"An error occurred while loading the task: {e}")

    def get_status(self):
        if self.task_list:
            return True
        else:
            return False

    def update_task(self, task_id, task_name, task_output):
        # Check if the task exists at agents/{agent_name}/tasks/{self.primary_objective}.json
        # We need to stip out symbols except spaces in primary objective and truncate the primary objective to 15 characters
        out_file = re.sub(r"[^\w\s]", "", self.primary_objective)
        out_file = out_file[:25]
        output_file = os.path.join(
            "agents", self.agent_name, "tasks", f"{out_file}.json"
        )
        if os.path.exists(output_file):
            # If it does, load it
            with open(output_file, "r") as f:
                data = json.load(f)
        else:
            # If it doesn't, create it
            data = {
                "primary_objective": self.primary_objective,
                "task_list": list(self.task_list),
                "tasks": [],
            }
        # Check if task is in the data["tasks"] list
        data["tasks"].append(
            {
                "task_id": task_id,
                "task_name": task_name,
                "task_output": task_output,
            }
        )
        # Save the data to agents/{agent_name}/tasks/{self.primary_objective}.json
        with open(output_file, "w") as f:
            json.dump(data, f)
        return data

    def get_task_output(self):
        out_file = re.sub(r"[^\w\s]", "", self.primary_objective)
        out_file = out_file[:25]
        try:
            with open(f"agents/{self.agent_name}/tasks/{out_file}.json", "r") as f:
                task_output = json.load(f)

            print(f"Successfully loaded task output for '{out_file}'.")
            return task_output

        except FileNotFoundError:
            print(f"No saved task output found with the name '{out_file}'.")
            return None
        except Exception as e:
            print(f"An error occurred while loading the task output: {e}")
            return None

    def get_tasks_files(self):
        files = os.listdir(os.path.join("agents", self.agent_name, "tasks"))
        files = [file[:-5] for file in files]
        return files

    def stop_tasks(self):
        if self.stop_running_event is not None:
            self.stop_running_event = True
        self.task_list.clear()

    def instruction_agent(self, task, **kwargs):
        if "task_name" in task:
            task = task["task_name"]

        resolver = self.ai.run(
            task=task,
            prompt="SmartInstruct-StepByStep"
            if self.primary_objective is None
            else "SmartTask-StepByStep",
            context_results=6,
            objective=self.primary_objective,
            **kwargs,
        )
        # Check if agent has commands before trying to run execution agent
        if Agent(self.agent_name).get_commands_string() != None:
            execution_response = self.ai.run(
                task=task,
                prompt="SmartInstruct-Execution"
                if self.primary_objective is None
                else "SmartTask-Execution",
                previous_response=resolver,
                objective=self.primary_objective,
                **kwargs,
            )
            return f"RESPONSE:\n{resolver}\n\nCommand Execution Response{execution_response}"
        else:
            return f"RESPONSE:\n{resolver}"

    def run_task(
        self,
        objective: str = "",
        async_exec: bool = False,
        smart: bool = False,
        load_task: str = "",
        **kwargs,
    ):
        initial_task = "Break down the objective into a list of small achievable tasks in the form of instructions that lead up to achieving the ultimate goal of the objective."
        if load_task != "":
            self.load_task(load_task)
            print(f"Loaded task '{load_task}'.\n\n")
        else:
            self.primary_objective = objective
            self.task_list = deque(
                [
                    {
                        "task_id": 1,
                        "task_name": initial_task,
                    }
                ]
            )
            print(f"Starting task with objective: {self.primary_objective}.\n\n")

        while not self.stop_running_event and self.task_list != deque([]):
            task = self.task_list.popleft()
            if task["task_name"] in ["None", "None.", ""]:
                self.stop_tasks()
                continue
            print(f"\nExecuting task {task['task_id']}: {task['task_name']}\n")
            if smart != True:
                result = self.instruction_agent(task=task["task_name"], **kwargs)
            else:
                result = self.ai.smart_instruct(
                    task=task["task_name"],
                    shots=3,
                    async_exec=async_exec,
                    objective=self.primary_objective,
                    **kwargs,
                )
            self.update_task(task["task_id"], task["task_name"], result)
            print(f"\nTask Result:\n\n{result}\n")
            if task["task_name"] == initial_task:
                lines = result.split("\n") if "\n" in result else [result]
                new_tasks = []
                for line in lines:
                    match = re.match(r"(\d+)\.\s+(.*)", line)
                    if match:
                        task_id, task_name = match.groups()
                        new_tasks.append(
                            {"task_id": int(task_id), "task_name": task_name.strip()}
                        )
                self.task_list = deque(new_tasks)
        if not self.task_list:
            self.stop_tasks()
        print("All tasks completed or stopped.")
