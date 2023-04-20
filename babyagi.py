#!/usr/bin/env python3
import argparse
import time
import re
import os
from collections import deque
from typing import Dict, List
from Config import Config
from AgentLLM import AgentLLM
class babyagi:
    def __init__(self, primary_objective=None, initial_task=None, agent_name="default"):
        self.CFG = Config()
        self.primary_objective = self.CFG.OBJECTIVE if primary_objective == None else primary_objective
        self.initial_task = self.CFG.INITIAL_TASK if initial_task == None else initial_task
        self.load_prompts()
        self.initialize_task_list()
        self.prompter = AgentLLM(agent_name)
        self.commands = self.prompter.get_agent_commands()
        self.output_list = []
        self.running = False
        self.agent_name = agent_name

    def set_agent_name(self, agent_name):
        self.agent_name = agent_name

    def get_status(self):
        return self.running

    def load_prompts(self):
        if not os.path.exists(f"model-prompts/{self.CFG.AI_MODEL}"):
            self.CFG.AI_MODEL = "default"
        with open(f"model-prompts/{self.CFG.AI_MODEL}/execute.txt", "r") as f:
            self.execute_prompt = f.read()
        with open(f"model-prompts/{self.CFG.AI_MODEL}/task.txt", "r") as f:
            self.task_prompt = f.read()
        with open(f"model-prompts/{self.CFG.AI_MODEL}/priority.txt", "r") as f:
            self.priority_prompt = f.read()

    def initialize_task_list(self):
        self.task_list = deque([])

    def display_objective_and_initial_task(self):
        self.output_list.append(f"Objective: {self.primary_objective}")
        self.output_list.append(f"Initial task: {self.initial_task}")
        print("\033[94m\033[1m" + "\n*****OBJECTIVE*****\n" + "\033[0m\033[0m")
        print(f"{self.primary_objective}")
        print("\033[93m\033[1m" + "\nInitial task:" + "\033[0m\033[0m" + f" {self.initial_task}")

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
        response = self.prompter.run(prompt, commands_enabled=False)
        self.output_list.append(f"Task creation agent response: {response}")
        if response is None:
            return []  # Return an empty list when the response is None
        new_tasks = response.split("\n") if "\n" in response else [response]
        return [{"task_name": task_name} for task_name in new_tasks]

    def prioritization_agent(self, this_task_id: int = 1):
        task_names = [t["task_name"] for t in self.task_list]
        next_task_id = this_task_id + 1
        prompt = self.priority_prompt
        prompt = prompt.replace("{objective}", self.primary_objective)
        prompt = prompt.replace("{next_task_id}", str(next_task_id))
        prompt = prompt.replace("{task_names}", ", ".join(task_names))
        response = self.prompter.run(prompt, commands_enabled=False)
        self.output_list.append(f"Prioritization agent response: {response}")
        new_tasks = response.split("\n") if "\n" in response else [response]
        self.task_list = deque()
        for task_string in new_tasks:
            task_parts = task_string.strip().split(".", 1)
            if len(task_parts) == 2:
                task_id = task_parts[0].strip()
                task_name = task_parts[1].strip()
                self.task_list.append({"task_id": task_id, "task_name": task_name})
        self.display_task_list()

    def display_task_list(self):
        self.output_list.append(f"Task list:\n\n{self.task_list}")
        print("\033[95m\033[1m" + "\n*****TASK LIST*****\n" + "\033[0m\033[0m")
        for task in self.task_list:
            print(f"{task['task_id']}. {task['task_name']}")

    def execution_agent(self, objective, task, task_id, context=None):
        prompt = self.execute_prompt
        prompt = prompt.replace("{objective}", objective)
        prompt = prompt.replace("{task}", task)
        prompt = prompt.replace("{COMMANDS}", "".join(self.commands))
        print(f"PROMPT: {prompt}")
        if context is not None:
            context = list(context)  # Convert set to list
        prompt = prompt.replace("{context}", str(context))
        if task_id == 0:
            self.response = self.prompter.run(prompt, commands_enabled=False)
        else:
            self.response = self.prompter.run(prompt)
        print("\033[91m\033[1m" + "\n*****EXECUTION AGENT*****\n" + "\033[0m\033[0m")
        print(f"{task_id}: {task}")
        print("\033[93m\033[1m" + "\n*****RESPONSE*****\n" + "\033[0m\033[0m")
        print(self.response)
        self.output_list.append(f"Execution agent response:\n\n{self.response}")
        print(self.output_list)
        return self.response

    def display_result(self, task):
        self.display_task_list()
        self.output_list.append(f"Task:\n\n{task['task_id']}: {task['task_name']}")
        self.output_list.append(f"Result:\n\n{self.response}")
        print("\033[92m\033[1m" + "\n*****NEXT TASK*****\n" + "\033[0m\033[0m")
        print(f"{task['task_id']}: {task['task_name']}")
        print("\033[93m\033[1m" + "\n*****RESULT*****\n" + "\033[0m\033[0m")
        print(self.response)

    def execute_next_task(self):
        if self.task_list:
            task = self.task_list.popleft()
        else:
            task = {"task_id": 0, "task_name": self.initial_task}
        this_task_id = task["task_id"]
        if type(this_task_id) != int:
            this_task_id = ''.join(re.findall(r'\d+', this_task_id))
            try:
                this_task_id = int(this_task_id)
            except:
                this_task_id = 2
        this_task_name = task["task_name"]
        if this_task_name == "":
            return self.execute_next_task()
        self.response = self.execution_agent(self.primary_objective, this_task_name, this_task_id)
        new_tasks = self.task_creation_agent(
            self.primary_objective,
            { "data": self.response },
            this_task_name,
            [t["task_name"] for t in self.task_list],
        )
        task_id_counter = this_task_id
        for new_task in new_tasks:
            task_id_counter += 1
            new_task.update({"task_id": task_id_counter})
            self.task_list.append(new_task)
        self.prioritization_agent(this_task_id)
        return task

    def get_output(self):
        return self.output_list

    def stop_running(self):
        self.running = False

    def run(self):  # Main loop
        # Add the first task
        self.add_initial_task()
        self.running = True
        while self.running:
            task = self.execute_next_task()
            self.display_result(task)
            if not self.task_list:
                self.output_list.append(f"\n\nAll tasks complete.")
                print("\033[91m\033[1m" + "\n*****ALL TASKS COMPLETE*****\n" + "\033[0m\033[0m")
                break
            time.sleep(0.5)  # Sleep before checking the task list again

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task Management System")
    parser.add_argument("primary_objective", help="Specify the primary objective for the Task Management System")
    args = parser.parse_args()
    task_manager = babyagi(primary_objective=args.primary_objective)
    task_manager.display_objective_and_initial_task()
    task_manager.run()
