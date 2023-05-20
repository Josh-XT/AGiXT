import re
import asyncio
from Commands import Commands
from CustomPrompt import CustomPrompt
from Memories import Memories
from Learning import Learning
from Agents import Agents
from Config.Agent import Agent
from collections import deque
from datetime import datetime


class AGiXT:
    def __init__(self, agent_name: str = "AGiXT"):
        self.agent_name = agent_name
        self.CFG = Agent(self.agent_name)
        self.primary_objective = None
        self.task_list = deque([])
        self.commands = Commands(self.agent_name)
        self.available_commands = self.commands.get_available_commands()
        self.agent_config = self.CFG.load_agent_config(self.agent_name)
        self.memories = Memories(self.agent_name, self.CFG)
        self.stop_running_event = None
        self.worker_agents = Agents(self.agent_name)

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
        top_results: int = 5,
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
            try:
                context = self.memories.context_agent(
                    query=task, top_results_num=top_results
                )
            except:
                context = "None."
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
        context_results: int = 5,
        websearch: bool = False,
        websearch_depth: int = 3,
        async_exec: bool = False,
        learn_file: str = "",
        **kwargs,
    ):
        if learn_file != "":
            learning_file = Learning(self.agent_name).read_file(
                task=task, file_path=learn_file
            )
            if learning_file == False:
                return "Failed to read file."
        formatted_prompt, unformatted_prompt, tokens = self.format_prompt(
            task=task,
            top_results=context_results,
            prompt=prompt,
            **kwargs,
        )
        if websearch:
            if async_exec:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    self.worker_agents.websearch_agent(task=task, depth=websearch_depth)
                )
            else:
                self.worker_agents.websearch_agent(task=task, depth=websearch_depth)
        if int(tokens) > int(self.CFG.MAX_TOKENS):
            if context_results > 0:
                context_results = context_results - 1
            if context_results == 0:
                print("Warning: No context injected due to max tokens.")
            return self.run(
                task=task,
                prompt=prompt,
                context_results=context_results,
                websearch=websearch,
                websearch_depth=websearch_depth,
                async_exec=async_exec,
                **kwargs,
            )
        self.response = self.CFG.instruct(formatted_prompt, tokens=tokens)
        # Handle commands if the prompt contains the {COMMANDS} placeholder
        # We handle command injection that DOESN'T allow command execution by using {command_list} in the prompt
        if "{COMMANDS}" in unformatted_prompt:
            self.response = self.worker_agents.execution_agent(
                execution_response=self.response,
                task=task,
                context_results=context_results,
                **kwargs,
            )
        print(f"Response: {self.response}")
        self.memories.store_result(task, self.response)
        self.CFG.log_interaction("USER", task)
        self.CFG.log_interaction(self.agent_name, self.response)
        return self.response

    def smart_instruct(
        self,
        task: str = "Write a tweet about AI.",
        shots: int = 3,
        async_exec: bool = False,
        learn_file: str = "",
        **kwargs,
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
                async_exec=async_exec,
                learn_file=learn_file,
                **kwargs,
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
                        **kwargs,
                    )
                )
        answer_str = ""
        for i, answer in enumerate(answers):
            answer_str += f"Answer {i + 1}:\n{answer}\n\n"
        researcher = self.run(
            task=answer_str,
            prompt="SmartInstruct-Researcher",
            shots=shots,
            **kwargs,
        )
        resolver = self.run(
            task=researcher,
            prompt="SmartInstruct-Resolver",
            shots=shots,
            **kwargs,
        )
        execution_response = self.run(
            task=task,
            prompt="SmartInstruct-Execution",
            previous_response=resolver,
            **kwargs,
        )
        clean_response_agent = self.run(
            task=task,
            prompt="SmartInstruct-CleanResponse",
            resolver_response=resolver,
            execution_response=execution_response,
            **kwargs,
        )
        return clean_response_agent

    def smart_chat(
        self,
        task: str = "Write a tweet about AI.",
        shots: int = 3,
        async_exec: bool = False,
        learn_file: str = "",
        **kwargs,
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
                async_exec=async_exec,
                learn_file=learn_file,
                **kwargs,
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
                        **kwargs,
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
            **kwargs,
        )
        resolver = self.run(
            task=researcher,
            prompt="SmartChat-Resolver",
            context_results=6,
            shots=shots,
            **kwargs,
        )
        clean_response_agent = self.run(
            task=task,
            prompt="SmartChat-CleanResponse",
            resolver_response=resolver,
            **kwargs,
        )
        return clean_response_agent
