from Chain import Chain
from Extensions import Extensions
from Interactions import Interactions


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
        short_task_description: str,
    ):
        task_list = numbered_list_of_tasks.split("\n")
        task_list = [
            task
            for task in task_list
            if task and task[0] in [str(i) for i in range(len(task_list))]
        ]
        chain_name = f"AI Generated Task - {short_task_description}"
        chain = Chain()
        chain.add_chain(chain_name=chain_name)
        for task in task_list:
            if "task_name" in task:
                chain.add_chain_step(
                    chain_name=chain_name,
                    agent_name=agent,
                    step_number=1,
                    prompt_type="Prompt",
                    prompt={
                        "prompt_name": "Task Execution",
                        "user_input": primary_objective,
                        "task": task["task_name"],
                        "websearch": True,
                        "websearch_depth": 3,
                        "context_results": 5,
                    },
                )
        return chain_name

    async def create_smart_task_chain(
        self,
        agent: str,
        primary_objective: str,
        numbered_list_of_tasks: str,
        short_task_description: str,
    ):
        task_list = numbered_list_of_tasks.split("\n")
        task_list = [
            task
            for task in task_list
            if task and task[0] in [str(i) for i in range(len(task_list))]
        ]
        chain_name = f"AI Generated Smart Task - {short_task_description}"
        chain = Chain()
        chain.add_chain(chain_name=chain_name)
        for task in task_list:
            if "task_name" in task:
                chain.add_chain_step(
                    chain_name=chain_name,
                    agent_name=agent,
                    step_number=1,
                    prompt_type="Chain",
                    prompt={
                        "chain_name": "Smart Instruct",
                        "user_input": f"Primary Objective: {primary_objective}\nYour Task: {task['task_name']}",
                    },
                )
        return chain_name

    async def run_chain(self, chain_name: str = "", user_input: str = ""):
        await Interactions(agent_name="").run_chain(
            chain_name=chain_name, user_input=user_input
        )
        return "Chain started successfully."
