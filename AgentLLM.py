import argparse
import re
import regex
from collections import deque
from typing import List
from Config.Agent import Agent
from commands.web_requests import web_requests
from commands.web_selenium import web_selenium
from duckduckgo_search import ddg
from Commands import Commands
import json
from json.decoder import JSONDecodeError
from CustomPrompt import CustomPrompt
from Memories import Memories


class AgentLLM:
    def __init__(self, agent_name: str = "AgentLLM", primary_objective=None):
        self.agent_name = agent_name
        self.CFG = Agent(self.agent_name)
        self.primary_objective = primary_objective
        self.task_list = deque([])
        self.commands = Commands(self.agent_name)
        self.available_commands = self.commands.get_available_commands()
        self.web_requests = web_requests()
        self.agent_config = self.CFG.load_agent_config(self.agent_name)
        self.output_list = []
        self.memories = Memories(self.agent_name, self.CFG)
        self.stop_running_event = None

    def get_output_list(self):
        return self.output_list

    def get_commands_string(self):
        if len(self.available_commands) == 0:
            return "No commands."

        enabled_commands = filter(
            lambda command: command.get("enabled", True), self.available_commands
        )
        if not enabled_commands:
            return "No commands."
        
        commands = {}
        for command in enabled_commands:
            command_name = f"_{command['name']}"
            commands[command_name] = {"_": command["friendly_name"]}
            for arg in command["args"]:
                if arg == "url":
                    commands[command_name][arg] = "http://example.com"
                elif arg == "filename":
                    commands[command_name][arg] = "example.txt"
                else:
                    commands[command_name][arg] = command["args"][arg]
        return json.dumps({"commands": commands}, indent=4)


    def validation_agent(self, json_string: str):
        try:
            json_string = self.run(task=json_string, prompt="jsonformatter")
            pattern = regex.compile(r"\{(?:[^{}]|(?R))*\}")
            cleaned_json = pattern.findall(json_string)
            if len(cleaned_json) == 0:
                return False
            if isinstance(cleaned_json, list):
                cleaned_json = cleaned_json[0]
            response = json.loads(cleaned_json)
            return response
        except JSONDecodeError as e:
            return False

    def custom_format(self, string, **kwargs):
        if isinstance(string, list):
            string = "".join(str(x) for x in string)

        def replace(match):
            key = match.group(1)
            value = kwargs.get(key, match.group(0))
            if isinstance(value, list):
                return "".join(str(x) for x in value)
            else:
                return str(value)

        pattern = r"(?<!{){([^{}\n]+)}(?!})"
        result = re.sub(pattern, replace, string)
        return result

    def format_prompt(
        self,
        task: str,
        top_results: int = 3,
        prompt="",
        **kwargs,
    ):
        if prompt == "chat":
            prompt = task
        elif prompt in ["execute", "task", "priority", "instruct"]:
            prompt = CustomPrompt().get_model_prompt(prompt_name=prompt, model=self.CFG.AI_MODEL)
        else:
            prompt = CustomPrompt().get_prompt(prompt_name=prompt, model=self.CFG.AI_MODEL)
        if top_results == 0:
            context = "None"
        else:
            context = self.memories.context_agent(
                query=task, top_results_num=top_results
            )
        command_list = self.get_commands_string()
        return self.custom_format(
            prompt,
            task=task,
            agent_name=self.agent_name,
            COMMANDS=command_list,
            context=context,
            objective=self.primary_objective,
            command_list=command_list,
            **kwargs,
        )
    
    def decode_json(response, silent = False):
        match = re.findall(r"```(?:json|python|javascript|)\n(.+(?:\n.+)+)\n```", response)
        if (match):
            response = match[0]
        try:
            return json.loads(response.strip())
        except ValueError as e:
            if not silent:
                return {"exception": e}

    def decode_tasks(response):
        lines = response.split("\n") if "\n" in response else [response]
        new_tasks = [
            re.sub(r"^.*?(\d)", r"\1", line)
            for line in lines
            if line.strip() and re.search(r"\d", line[:10])
        ] or [response]
        return new_tasks

    def run(
        self,
        task: str,
        prompt: str = "",
        context_results: int = 3,
        websearch: bool = False,
        websearch_depth: int = 8,
        **kwargs,
    ):
        formatted_prompt = self.format_prompt(
            task=task,
            top_results=context_results,
            prompt=prompt,
            **kwargs,
        )
        #if websearch:
        #    self.websearch_to_memory(task=task, depth=websearch_depth)
        response = self.CFG.instruct(formatted_prompt)
        if prompt == "task":
            return AgentLLM.decode_json(response, True) or AgentLLM.decode_tasks(response)
        if prompt == "priority":
            return AgentLLM.decode_tasks(response)
        if prompt != "chat":
            response = AgentLLM.decode_json(response)
    
        result_parts = []
        if "plan" in response:
            result_parts.append(f"\n\nPLAN:\n{response['plan']}")
        if "response" in response:
            result_parts.append(f"\n\nRESULT:\n{response['response']}")
        if  "commands" in response:
            result_parts.append(f"\n\nCOMMANDS:\n{json.dumps(response['commands'], indent=4)}\n")
            result_parts.append(f"\n\nExecute commands:\n")
            for line in self.execute_commands(response['commands']):
                result_parts.append(line)

        messages = "".join(result_parts)
        if (messages):
            print(messages)
            self.update_output_list(messages)
            if not self.CFG.NO_MEMORY:
                self.store_result(task, messages)
                self.CFG.log_interaction("USER", task)
                self.CFG.log_interaction(self.agent_name, messages)

        return response
    
    def execute_commands(self, commands):
        result_parts = []
        for command_name, command_args in commands.items():
            if command_name[0] == "_":
                result = self.commands.execute_command(
                    command_name[1:],
                    self.execute_args(command_args)
                )
                result_parts.append(
                    f"\n{command_name}: {result}"
                )
        return result_parts;

    def execute_args(self, command_args):
        for arg, value in command_args.items():
            if type(value) == object and not type(value) == list:
                for key, val in value.items():
                    if key[0] == "_":
                        command_args[arg] = self.commands.execute_command(
                            key[1:],
                            self.execute_args(val)
                        )
                        break
        return command_args;

    def smart_instruct(
        self,
        task: str = "Write a tweet about AI.",
        shots: int = 3,
    ):
        answers = []
        # Do multi shots of prompt to get N different answers to be validated
        for i in range(shots):
            answers.append(
                self.run(
                    task=task,
                    prompt="SmartInstruct-StepByStep",
                    context_results=6,
                    websearch=True,
                    websearch_depth=8,
                )
            )
        answer_str = ""
        for i, answer in enumerate(answers):
            answer_str += f"Answer {i + 1}:\n{answer}\n\n"
        researcher = self.run(task=answer_str, prompt="SmartInstruct-Researcher")
        resolver = self.run(task=researcher, prompt="SmartInstruct-Resolver")
        return resolver

    def smart_chat(
        self,
        task: str = "Write a tweet about AI.",
        shots: int = 3,
    ):
        answers = []
        # Do multi shots of prompt to get N different answers to be validated
        for i in range(shots):
            answers.append(
                self.run(
                    task=task,
                    prompt="SmartChat-StepByStep",
                    context_results=6,
                    websearch=True,
                    websearch_depth=8,
                )
            )
        answer_str = ""
        for i, answer in enumerate(answers):
            answer_str += f"Answer {i + 1}:\n{answer}\n\n"
        researcher = self.run(
            task=answer_str, prompt="SmartChat-Researcher", context_results=6
        )
        resolver = self.run(
            task=researcher, prompt="SmartChat-Resolver", context_results=6
        )
        return resolver

    def websearch_to_memory(
        self, task: str = "What are the latest breakthroughs in AI?", depth: int = 8
    ):
        results = self.run(task=task, prompt="WebSearch")
        results = results[results.find("[") : results.rfind("]") + 1]
        while results is None or results == "":
            # Don't take no for an answer. Keep asking until you get a response.
            results = self.run(task=task, prompt="WebSearch")
            results = results[results.find("[") : results.rfind("]") + 1]
        results = results.replace("[", "").replace("]", "")
        results = results.split(",")
        results = [result.replace('"', "") for result in results]
        for result in results:
            links = ddg(result, max_results=depth)
            if links is not None:
                for link in links:
                    collected_data = web_selenium.scrape_text_with_selenium(link)
                    if collected_data is not None:
                        self.memories.store_result(task, collected_data)

    def get_status(self):
        try:
            return not self.stop_running_event.is_set()
        except:
            return False

    def update_output_list(self, output):
        print(
            self.CFG.save_task_output(self.agent_name, output, self.primary_objective)
        )

    def task_creation_agent(
        self, result: str, task_description: str, task_list: List[str]
    ):
        return self.run(
            task=self.primary_objective,
            prompt="task",
            result=result,
            task_description=task_description,
            tasks=", ".join(task_list),
        )

    def prioritization_agent(self):
        task_names = [t["task_name"] for t in self.task_list]
        if not task_names:
            return
        next_task_id = len(self.task_list) + 1

        new_tasks = self.run(
            task=self.primary_objective,
            prompt="priority",
            task_names=", ".join(task_names),
            next_task_id=next_task_id,
        )
        self.task_list = deque()
        for task_string in new_tasks:
            task_parts = task_string.strip().split(".", 1)
            if len(task_parts) == 2:
                task_id = task_parts[0].strip()
                task_name = task_parts[1].strip()
                self.task_list.append({"task_id": task_id, "task_name": task_name})

    def run_task(self, stop_event, objective):
        self.primary_objective = objective
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
            result = self.run(task=task["task_name"], prompt="execute")
            try:
                json_result = json.dumps(result, indent=4)
                self.update_output_list(f"\nTask Result:\n{json_result}\n\n")
            except:
                self.update_output_list(f"\nTask Result (json error):\n{result}\n\n")
            if "response" in result:
                result = result["response"]
            else:
                result = ""
            new_tasks = self.task_creation_agent(
                result,
                task["task_name"],
                [t["task_name"] for t in self.task_list],
            )
            new_tasks_list = "\n".join(new_tasks)
            self.update_output_list(f"\nNew Tasks:\n{new_tasks_list}\n")
            for new_task in new_tasks:
                self.task_list.append({"task_id": len(self.task_list) + 1, "task_name": new_task})
            #self.prioritization_agent()
        self.update_output_list("All tasks completed or stopped.")

    def run_chain_step(self, step_data_list):
        for step_data in step_data_list:
            for prompt_type, prompt in step_data.items():
                if prompt_type == "instruction":
                    self.run(prompt, prompt="instruct")
                elif prompt_type == "task":
                    self.run_task(prompt)
                elif prompt_type == "command":
                    command = prompt.strip()
                    command_name, command_args = None, {}
                    # Extract command name and arguments using regex
                    command_regex = re.search(r"(\w+)\((.*)\)", command)
                    if command_regex:
                        command_name, args_str = command_regex.groups()
                        if args_str:
                            # Parse arguments string into a dictionary
                            args_str = args_str.replace("'", '"')
                            args_str = args_str.replace("None", "null")
                            try:
                                command_args = json.loads(args_str)
                            except JSONDecodeError as e:
                                # error parsing args, send command_name to None so trying to execute command won't crash
                                command_name = None
                                print(f"Error: {e}")

                    # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                    if command_name is not None:
                        for available_command in self.available_commands:
                            if available_command["friendly_name"] == command_name:
                                command_name = available_command["name"]
                                break
                        self.commands.execute_command(command_name, command_args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=str, default="Write a tweet about AI.")
    parser.add_argument("--agent_name", type=str, default="Agent-LLM")
    parser.add_argument("--option", type=str, default="")
    parser.add_argument("--shots", type=int, default=3)
    args = parser.parse_args()
    prompt = args.prompt
    agent_name = args.agent_name
    option = args.option
    # Options are instruct, smartinstruct, smartchat, and chat.
    shots = args.shots
    agent = AgentLLM(agent_name)
    if option == "instruct":
        agent.run(prompt, prompt="instruct", websearch=True, websearch_depth=4)
    elif option == "smartinstruct":
        agent.smart_instruct(prompt, shots)
    elif option == "smartchat":
        agent.smart_chat(prompt, shots)
    else:
        agent.run(
            prompt, prompt="chat", context_results=5, websearch=True, websearch_depth=4
        )
