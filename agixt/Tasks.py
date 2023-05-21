from AGiXT import AGiXT
import re
from Config.Agent import Agent
from collections import deque


class Tasks:
    def __init__(self, agent_name: str = "AGiXT"):
        self.agent_name = agent_name
        self.agent = Agent(self.agent_name)
        self.primary_objective = None
        self.task_list = deque([])
        self.output_list = []
        self.stop_running_event = None

    def get_status(self):
        try:
            return not self.stop_running_event.is_set()
        except:
            return False

    def get_output_list(self):
        return self.output_list

    def update_output_list(self, output):
        print(
            self.agent.save_task_output(self.agent_name, output, self.primary_objective)
        )

    def run_task(
        self,
        stop_event,
        objective,
        async_exec: bool = False,
        learn_file: str = "",
        smart: bool = False,
        **kwargs,
    ):
        self.primary_objective = objective
        if learn_file != "":
            learned_file = self.agent.memories.read_file(
                task=objective, file_path=learn_file
            )
            if learned_file == True:
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
        if len(self.task_list) == 0:
            self.task_list.append(
                {
                    "task_id": 1,
                    "task_name": "Develop a task list to complete the objective if necessary.  The plan is 'None' if not necessary.",
                }
            )
        self.stop_running_event = stop_event
        while not stop_event.is_set():
            if self.task_list == []:
                break
            if len(self.task_list) > 0:
                task = self.task_list.popleft()
            if task["task_name"] == "None" or task["task_name"] == "None.":
                break
            self.update_output_list(
                f"\nExecuting task {task['task_id']}: {task['task_name']}\n"
            )
            if smart:
                result = self.smart_instruct(
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
            task_list = [t["task_name"] for t in self.task_list]
            new_tasks = AGiXT(self.agent_name).task_agent(
                result=result, task_description=task["task_name"], task_list=task_list
            )
            self.update_output_list(f"\nNew Tasks:\n\n{new_tasks}\n")
            for new_task in new_tasks:
                new_task.update({"task_id": len(self.task_list) + 1})
                self.task_list.append(new_task)
            task_names = [t["task_name"] for t in self.task_list]
            if not task_names:
                return
            next_task_id = len(self.task_list) + 1
            response = AGiXT(self.agent_name).run(
                task=self.primary_objective,
                prompt="priority",
                task_names=", ".join(task_names),
                next_task_id=next_task_id,
            )

            lines = response.split("\n") if "\n" in response else [response]
            new_tasks = [
                re.sub(r"^.*?(\d)", r"\1", line)
                for line in lines
                if line.strip() and re.search(r"\d", line[:10])
            ] or [response]
            self.task_list = deque()
            for task_string in new_tasks:
                task_parts = task_string.strip().split(".", 1)
                if len(task_parts) == 2:
                    task_id = task_parts[0].strip()
                    task_name = task_parts[1].strip()
                    self.task_list.append({"task_id": task_id, "task_name": task_name})
        self.update_output_list("All tasks completed or stopped.")
