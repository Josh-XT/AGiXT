import argparse
import re
import regex
from collections import deque
from typing import List, Dict
from Config.Agent import Agent
from datetime import datetime
from commands.web_requests import web_requests
from playwright.async_api import async_playwright
from duckduckgo_search import ddg
from Commands import Commands
import json
from json.decoder import JSONDecodeError
from CustomPrompt import CustomPrompt
from Memories import Memories
import asyncio


def run_asyncio_coroutine(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


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

        friendly_names = map(
            lambda command: f"{command['friendly_name']} - {command['name']}({command['args']})",
            enabled_commands,
        )
        return "\n".join(friendly_names)

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
        cp = CustomPrompt()
        if prompt == "":
            prompt = task
        else:
            prompt = cp.get_prompt(prompt_name=prompt, model=self.CFG.AI_MODEL)
        if top_results == 0:
            context = "None"
        else:
            context = self.memories.context_agent(
                query=task, top_results_num=top_results
            )
        command_list = self.get_commands_string()
        formatted_prompt = self.custom_format(
            prompt,
            task=task,
            agent_name=self.agent_name,
            COMMANDS=command_list,
            context=context,
            objective=self.primary_objective,
            command_list=command_list,
            date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            **kwargs,
        )
        tokens = len(self.memories.nlp(formatted_prompt))
        return formatted_prompt, prompt, tokens

    def run(
        self,
        task: str,
        prompt: str = "",
        context_results: int = 3,
        websearch: bool = False,
        websearch_depth: int = 3,
        **kwargs,
    ):
        formatted_prompt, unformatted_prompt, tokens = self.format_prompt(
            task=task,
            top_results=context_results,
            prompt=prompt,
            **kwargs,
        )
        if websearch:
            run_asyncio_coroutine(
                self.websearch_to_memory(task=task, depth=websearch_depth)
            )
            # self.websearch_to_memory(task=task, depth=websearch_depth)
        self.response = self.CFG.instruct(formatted_prompt, tokens=tokens)
        # Handle commands if in response
        if "{COMMANDS}" in unformatted_prompt:
            valid_json = self.validation_agent(self.response)
            while not valid_json:
                print("INVALID JSON RESPONSE")
                print(self.response)
                print("... Trying again.")
                if context_results != 0:
                    context_results = context_results - 1
                else:
                    context_results = 0
                formatted_prompt, unformatted_prompt, tokens = self.format_prompt(
                    task=task,
                    top_results=context_results,
                    prompt=prompt,
                    **kwargs,
                )
                self.response = self.CFG.instruct(formatted_prompt, tokens=tokens)
                valid_json = self.validation_agent(self.response)
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
            print(f"Pre-Validation Response: {self.response}")
        self.memories.store_result(task, self.response)
        # Second shot to validate response
        context_results = 3
        formatted_prompt, unformatted_prompt, tokens = self.format_prompt(
            task=task,
            top_results=context_results,
            prompt="validate",
            previous_response=self.response,
            **kwargs,
        )
        response = self.CFG.instruct(formatted_prompt, tokens=tokens)
        if "{COMMANDS}" in unformatted_prompt:
            valid_json = self.validation_agent(response)
            while not valid_json:
                print("INVALID JSON RESPONSE")
                print(response)
                print("... Trying again.")
                if context_results != 0:
                    context_results = context_results - 1
                else:
                    context_results = 0
                valid_json = self.validation_agent(response)
            if "response" in valid_json:
                self.response = valid_json["response"]
            if "commands" in valid_json:
                commands_used = valid_json["commands"]
                if len(commands_used) > 0:
                    self.response += f"\n\nCommands Used:\n\n{commands_used}"
            print(f"Post-Validation Response: {self.response}")
        else:
            print(f"Response: {self.response}")
        self.memories.store_result(task, self.response)
        self.CFG.log_interaction("USER", task)
        self.CFG.log_interaction(self.agent_name, self.response)
        return self.response

    def smart_instruct(
        self,
        task: str = "Write a tweet about AI.",
        shots: int = 3,
    ):
        answers = []
        # Do multi shots of prompt to get N different answers to be validated
        answers.append(
            self.run(
                task=task,
                prompt="SmartInstruct-StepByStep",
                context_results=6,
                websearch=True,
                websearch_depth=3,
                shots=shots,
            )
        )
        if shots > 1:
            for i in range(shots - 1):
                answers.append(
                    self.run(
                        task=task,
                        prompt="SmartInstruct-StepByStep",
                        context_results=6,
                        shots=shots,
                    )
                )
        answer_str = ""
        for i, answer in enumerate(answers):
            answer_str += f"Answer {i + 1}:\n{answer}\n\n"
        researcher = self.run(
            task=answer_str, prompt="SmartInstruct-Researcher", shots=shots
        )
        resolver = self.run(
            task=researcher, prompt="SmartInstruct-Resolver", shots=shots
        )
        return resolver

    def smart_chat(
        self,
        task: str = "Write a tweet about AI.",
        shots: int = 3,
    ):
        answers = []
        answers.append(
            self.run(
                task=task,
                prompt="SmartChat-StepByStep",
                context_results=6,
                websearch=True,
                websearch_depth=3,
                shots=shots,
            )
        )
        # Do multi shots of prompt to get N different answers to be validated
        if shots > 1:
            for i in range(shots - 1):
                answers.append(
                    self.run(
                        task=task,
                        prompt="SmartChat-StepByStep",
                        context_results=6,
                        shots=shots,
                    )
                )
        answer_str = ""
        for i, answer in enumerate(answers):
            answer_str += f"Answer {i + 1}:\n{answer}\n\n"
        researcher = self.run(
            task=answer_str,
            prompt="SmartChat-Researcher",
            context_results=6,
            shots=shots,
        )
        resolver = self.run(
            task=researcher, prompt="SmartChat-Resolver", context_results=6, shots=shots
        )
        return resolver

    async def websearch_to_memory(
        self, task: str = "What are the latest breakthroughs in AI?", depth: int = 3
    ):
        results = self.run(task=task, prompt="WebSearch")
        results = results.split("\n")
        for result in results:
            search_string = result.lstrip("0123456789. ")
            links = ddg(search_string, max_results=depth)
            if links is not None:
                for link in links:
                    print(f"Scraping: {link['href']}")
                    collected_data = await self.scrape_text_with_playwright(
                        link["href"]
                    )
                    if collected_data is not None:
                        self.memories.store_result(task, collected_data)

    async def scrape_text_with_playwright(self, url):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(url)
                content = await page.content()
                await browser.close()
                return content
        except:
            return None

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
            result = self.smart_instruct(task=task["task_name"], shots=3)
            # result = self.run(task=task["task_name"], prompt="execute")
            self.update_output_list(f"\nTask Result:\n\n{result}\n")
            task_list = [t["task_name"] for t in self.task_list]
            new_tasks = self.task_creation_agent(
                result=result, task_description=task["task_name"], task_list=task_list
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
                elif prompt_type == "chat":
                    self.run(prompt, prompt="chat")
                elif prompt_type == "smart_instruct":
                    self.smart_instruct(task=prompt, shots=3)
                elif prompt_type == "smart_chat":
                    self.smart_chat(task=prompt, shots=3)
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
                else:
                    self.run(task=prompt, prompt=prompt_type)


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
