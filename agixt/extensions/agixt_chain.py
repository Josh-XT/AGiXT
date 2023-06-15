from Chain import Chain
from Extensions import Extensions
from Interactions import Interactions
import datetime


class agixt_chain(Extensions):
    def __init__(self, **kwargs):
        self.chains = Chain().get_chains()
        self.commands = {
            "Create Task Chain": self.create_task_chain,
            "Create Smart Task Chain": self.create_smart_task_chain,
        }
        if self.chains != None:
            for chain in self.chains:
                if "name" in chain:
                    self.commands.update(
                        {f"Run Chain: {chain['name']}": self.run_chain}
                    )

    async def create_task_chain(
        self,
        agent: str,
        primary_objective: str,
        numbered_list_of_tasks: str,
        short_chain_description: str,
    ):
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        task_list = numbered_list_of_tasks.split("\n")
        task_list = [
            task.lstrip("0123456789.")  # Strip leading digits and periods
            for task in task_list
            if task
            and task[0]
            in [str(i) for i in range(10)]  # Check for task starting with a digit (0-9)
        ]
        chain_name = f"AI Generated Task - {short_chain_description} - {timestamp}"
        chain = Chain()
        chain.add_chain(chain_name=chain_name)
        i = 1
        for task in task_list:
            chain.add_chain_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Prompt",
                prompt={
                    "prompt_name": "Task Execution",
                    "primary_objective": primary_objective,
                    "task": task,
                    "websearch": True,
                    "websearch_depth": 3,
                    "context_results": 5,
                },
            )
            i += 1
        return chain_name

    async def create_smart_task_chain(
        self,
        agent: str,
        primary_objective: str,
        numbered_list_of_tasks: str,
        short_chain_description: str,
    ):
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        task_list = numbered_list_of_tasks.split("\n")
        task_list = [
            task.lstrip("0123456789.")  # Strip leading digits and periods
            for task in task_list
            if task
            and task[0]
            in [str(i) for i in range(10)]  # Check for task starting with a digit (0-9)
        ]
        chain_name = (
            f"AI Generated Smart Task - {short_chain_description} - {timestamp}"
        )
        chain = Chain()
        chain.add_chain(chain_name=chain_name)
        i = 1
        for task in task_list:
            chain.add_chain_step(
                chain_name=chain_name,
                agent_name=agent,
                step_number=i,
                prompt_type="Chain",
                prompt={
                    "chain": "Smart Instruct",
                    "input": f"Primary Objective: {primary_objective}\nYour Task: {task}",
                },
            )
            i += 1
        return chain_name

    async def run_chain(self, chain: str = "", input: str = ""):
        await Interactions(agent_name="").run_chain(chain_name=chain, user_input=input)
        return "Chain started successfully."
