import argparse
import re
import spacy
from collections import deque
from typing import List, Dict
from Config.Agent import Agent
from commands.web_requests import web_requests
from Commands import Commands
import json
from json.decoder import JSONDecodeError
import spacy
from spacy.cli import download
from CustomPrompt import CustomPrompt
from Memories import Memories

try:
    nlp = spacy.load("en_core_web_sm")
except:
    print("Downloading spacy model...")
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")


class AgentLLM:
    def __init__(self, agent_name: str = "AgentLLM", primary_objective=None):
        self.agent_name = agent_name
        self.CFG = Agent(self.agent_name)
        self.memories = Memories(self.agent_name, nlp=nlp)
        self.primary_objective = primary_objective
        self.task_list = deque([])
        self.commands = Commands(self.agent_name)
        self.available_commands = self.commands.get_available_commands()
        self.web_requests = web_requests()
        self.agent_config = self.CFG.load_agent_config(self.agent_name)
        self.output_list = []
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

        friendly_names = map(
            lambda command: f"{command['friendly_name']} - {command['name']}({command['args']})",
            enabled_commands,
        )
        return "\n".join(friendly_names)

    def validate_json(self, json_string: str):
        try:
            clean_response = re.findall(
                r"```(?:json|css|vbnet|javascript)\n([\s\S]*?)\n```", json_string
            )
            clean_response = clean_response[0] if clean_response else json_string
            response = json.loads(clean_response)
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
        long_term_access: bool = False,
        max_context_tokens: int = 128,
        prompt="",
        **kwargs,
    ):
        cp = CustomPrompt()
        if prompt == "":
            prompt = task
        elif prompt in ["execute", "task", "priority", "instruct"]:
            prompt = cp.get_model_prompt(prompt_name=prompt, model=self.CFG.AI_MODEL)
        else:
            prompt = CustomPrompt().get_prompt(prompt)
        if top_results == 0:
            context = "None"
        else:
            context = self.memories.context_agent(
                query=task,
                top_results_num=top_results,
                long_term_access=long_term_access,
                max_tokens=max_context_tokens,
            )
        formatted_prompt = self.custom_format(
            prompt,
            task=task,
            agent_name=self.agent_name,
            COMMANDS=self.get_commands_string(),
            context=context,
            objective=self.primary_objective,
            **kwargs,
        )
        tokens = len(nlp(formatted_prompt))
        return formatted_prompt, prompt, tokens

    def run(
        self,
        task: str,
        max_context_tokens: int = 128,
        long_term_access: bool = False,
        prompt: str = "",
        context_results: int = 3,
        **kwargs,
    ):
        formatted_prompt, unformatted_prompt, tokens = self.format_prompt(
            task=task,
            top_results=context_results,
            long_term_access=long_term_access,
            max_context_tokens=max_context_tokens,
            prompt=prompt,
            **kwargs,
        )
        self.response = self.CFG.instruct(formatted_prompt, tokens=tokens)
        # Handle commands if in response
        if "{COMMANDS}" in unformatted_prompt:
            valid_json = self.validate_json(self.response)
            while not valid_json:
                print("INVALID JSON RESPONSE")
                print(self.response)
                print("Invalid JSON response. Trying again.")
                # Begin context decay
                if context_results != 0:
                    context_results = context_results - 1
                else:
                    context_results = 0
                formatted_prompt, unformatted_prompt, tokens = self.format_prompt(
                    task=task,
                    top_results=context_results,
                    long_term_access=long_term_access,
                    max_context_tokens=max_context_tokens,
                    prompt=prompt,
                    **kwargs,
                )
                self.response = self.CFG.instruct(formatted_prompt, tokens=tokens)
                valid_json = self.validate_json(self.response)
            if valid_json:
                self.response = valid_json
            response_parts = []
            if "thoughts" in self.response:
                response_parts.append(f"\n\nTHOUGHTS:\n\n{self.response['thoughts']}")
            if "plan" in self.response:
                response_parts.append(f"\n\nPLAN:\n\n{self.response['plan']}")
            if "summary" in self.response:
                response_parts.append(f"\n\nSUMMARY:\n\n{self.response['summary']}")
            if "response" in self.response:
                response_parts.append(f"\n\nRESPONSE:\n\n{self.response['response']}")
            if "commands" in self.response:
                response_parts.append(f"\n\nCOMMANDS:\n\n{self.response['commands']}")
                for command_name, command_args in self.response["commands"].items():
                    # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                    if command_name is not None:
                        for available_command in self.available_commands:
                            if command_name in [
                                available_command["friendly_name"],
                                available_command["name"],
                            ]:
                                command_name = available_command["name"]
                                break
                        response_parts.append(
                            f"\n\n{self.commands.execute_command(command_name, command_args)}"
                        )
                    else:
                        if command_name == "None.":
                            response_parts.append(f"\n\nNo commands were executed.")
                        else:
                            response_parts.append(
                                f"\n\nCommand not recognized: {command_name}"
                            )
            self.response = "".join(response_parts)
        if not self.CFG.NO_MEMORY:
            self.memories.store_result(task, self.response)
            self.CFG.log_interaction("USER", task)
            self.CFG.log_interaction(self.agent_name, self.response)
        print(f"Response: {self.response}")
        return self.response

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
        self, result: Dict, task_description: str, task_list: List[str]
    ) -> List[Dict]:
        response = self.run(
            task=self.primary_objective,
            prompt="task",
            result=result,
            task_description=task_description,
            tasks=", ".join(task_list),
        )

        lines = response.split("\n") if "\n" in response else [response]
        new_tasks = [
            re.sub(r"^.*?(\d)", r"\1", line)
            for line in lines
            if line.strip() and re.search(r"\d", line[:10])
        ] or [response]
        return [{"task_name": task_name} for task_name in new_tasks]

    def prioritization_agent(self):
        task_names = [t["task_name"] for t in self.task_list]
        if not task_names:
            return
        next_task_id = len(self.task_list) + 1

        response = self.run(
            task=self.primary_objective,
            prompt="priority",
            tasks=", ".join(task_names),
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

    def run_task(self, stop_event, objective):
        self.primary_objective = objective
        self.update_output_list(
            f"Starting task with objective: {self.primary_objective}.\n\n"
        )
        if len(self.task_list) == 0:
            self.task_list.append({"task_id": 1, "task_name": "Develop a task list."})
        self.stop_running_event = stop_event
        while not stop_event.is_set():
            if self.task_list == []:
                break
            if len(self.task_list) > 0:
                task = self.task_list.popleft()
            self.update_output_list(
                f"\nExecuting task {task['task_id']}: {task['task_name']}\n"
            )
            result = self.run(task=task["task_name"], prompt="execute")
            self.update_output_list(f"\nTask Result:\n\n{result}\n")
            new_tasks = self.task_creation_agent(
                {"data": result},
                task["task_name"],
                [t["task_name"] for t in self.task_list],
            )
            self.update_output_list(f"\nNew Tasks:\n\n{new_tasks}\n")
            for new_task in new_tasks:
                new_task.update({"task_id": len(self.task_list) + 1})
                self.task_list.append(new_task)
            self.prioritization_agent()
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
    parser.add_argument("--prompt", type=str, default="What is the weather like today?")
    parser.add_argument("--max_context_tokens", type=int, default=128)
    parser.add_argument("--long_term_access", type=bool, default=False)
    parser.add_argument("--agent_name", type=str, default="Agent-LLM")
    args = parser.parse_args()
    prompt = args.prompt
    max_context_tokens = int(args.max_context_tokens)
    long_term_access = args.long_term_access
    agent_name = args.agent_name

    # Run AgentLLM
    AgentLLM(agent_name).run(
        task=prompt,
        max_context_tokens=max_context_tokens,
        long_term_access=long_term_access,
    )
