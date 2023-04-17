import time
import re
from collections import deque
from typing import Dict, List
from Config import Config
from AgentLLM import AgentLLM
class babyagi:
    def __init__(self, primary_objective=None, initial_task=None):
        self.CFG = Config()
        self.primary_objective = self.CFG.OBJECTIVE if primary_objective == None else primary_objective
        self.initial_task = self.CFG.INITIAL_TASK if initial_task == None else initial_task
        with open(f"model-prompts/{self.CFG.AI_MODEL}/execute.txt", "r") as f:
            self.execute_prompt = f.read()
        with open(f"model-prompts/{self.CFG.AI_MODEL}/task.txt", "r") as f:
            self.task_prompt = f.read()
        with open(f"model-prompts/{self.CFG.AI_MODEL}/priority.txt", "r") as f:
            self.priority_prompt = f.read()
        # Task list
        self.task_list = deque([])
        self.output_list = []
        self.prompter = AgentLLM()

        # Print OBJECTIVE
        print("\033[94m\033[1m" + "\n*****OBJECTIVE*****\n" + "\033[0m\033[0m")
        print(f"{primary_objective}")
        print("\033[93m\033[1m" + "\nInitial task:" + "\033[0m\033[0m" + f" {initial_task}")
    def add_initial_task(self):
        self.task_list.append({"task_id": 1, "task_name": self.initial_task})
    def set_objective(self, new_objective):
        self.primary_objective = new_objective

    def task_creation_agent(self, objective: str, result: Dict, task_description: str, task_list: List[str]):
        prompt = self.task_prompt
        prompt = prompt.replace("{objective}", objective)
        prompt = prompt.replace("{result}", str(result))
        prompt = prompt.replace("{task_description}", task_description)
        prompt = prompt.replace("{tasks}", ", ".join(task_list))
        response = self.prompter.run(prompt)
        if response is None:
            return []  # Return an empty list when the response is None
        new_tasks = response.split("\n") if "\n" in response else [response]
        return [{"task_name": task_name} for task_name in new_tasks]

    def prioritization_agent(self, this_task_id: int):
        task_names = [t["task_name"] for t in self.task_list]
        next_task_id = int(this_task_id) + 1
        prompt = self.priority_prompt
        prompt = prompt.replace("{objective}", self.primary_objective)
        prompt = prompt.replace("{next_task_id}", str(next_task_id))
        prompt = prompt.replace("{task_names}", ", ".join(task_names))
        response = self.prompter.run(prompt)
        new_tasks = response.split("\n") if "\n" in response else [response]
        self.task_list = deque()
        for task_string in new_tasks:
            task_parts = task_string.strip().split(".", 1)
        if len(task_parts) == 2:
            task_id = task_parts[0].strip()
            task_name = task_parts[1].strip()
            self.task_list.append({"task_id": task_id, "task_name": task_name})
        print("\033[95m\033[1m" + "\n*****TASK LIST*****\n" + "\033[0m\033[0m")
        for task in self.task_list:
            print(f"{task['task_id']}. {task['task_name']}")

    def execution_agent(self, objective: str, task: str) -> str:
        # Executes a task based on the given objective and previous context.
        # Returns the result of the task.
        context = self.prompter.context_agent(query=objective, top_results_num=5, long_term_access=True)
        prompt = self.execute_prompt
        prompt = prompt.replace("{objective}", objective)
        prompt = prompt.replace("{task}", task)
        prompt = prompt.replace("{context}", str(context))
        self.response = self.prompter.run(prompt)
        return self.response

    def execute_next_task(self):
        if self.task_list:
            task = self.task_list.popleft()
        else:
            task = {"task_id": 0, "task_name": self.initial_task}
        this_task_id = task["task_id"]
        if type(this_task_id) != int:
            this_task_id = ''.join(re.findall(r'\d+', this_task_id))
        this_task_name = task["task_name"]
        self.response = self.execution_agent(self.primary_objective, task["task_name"])
        new_tasks = self.task_creation_agent(
            self.primary_objective,
            { "data": self.response },
            this_task_name,
            [t["task_name"] for t in self.task_list],
        )
        task_id_counter = int(this_task_id)
        for new_task in new_tasks:
            task_id_counter += 1
            new_task.update({"task_id": task_id_counter})
            self.task_list.append(new_task)
        self.prioritization_agent(this_task_id)
        return task

    def run(self):
        # Add the first task
        self.add_initial_task()

        # Main loop
        while True:
            task = self.execute_next_task()
            if task:
                print("\033[95m\033[1m" + "\n*****TASK LIST*****\n" + "\033[0m\033[0m")
                for t in self.task_list:
                    task_id = t["task_id"]
                    task_name = t["task_name"]
                    print(f"{task_id}: {task_name}")
                print("\033[92m\033[1m" + "\n*****NEXT TASK*****\n" + "\033[0m\033[0m")
                print(f"{task['task_id']}: {task['task_name']}")
                print("\033[93m\033[1m" + "\n*****RESULT*****\n" + "\033[0m\033[0m")
                print(self.response)
            else:
                print("\033[91m\033[1m" + "\n*****ALL TASKS COMPLETE*****\n" + "\033[0m\033[0m")
                break
            time.sleep(1)  # Sleep before checking the task list again