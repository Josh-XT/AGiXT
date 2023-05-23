import re
import asyncio
import regex
import json
from datetime import datetime
from Agent import Agent
from CustomPrompt import CustomPrompt
from duckduckgo_search import ddg
from urllib.parse import urlparse


class AGiXT:
    def __init__(self, agent_name: str = "AGiXT"):
        self.agent_name = agent_name
        self.agent = Agent(self.agent_name)
        self.stop_running_event = None
        self.browsed_links = []

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
            prompt = cp.get_prompt(prompt_name=prompt, model=self.agent.AI_MODEL)
        if top_results == 0:
            context = "None"
        else:
            try:
                context = self.agent.memories.context_agent(
                    query=task, top_results_num=top_results
                )
            except:
                context = "None."
        command_list = self.agent.get_commands_string()
        formatted_prompt = self.custom_format(
            prompt,
            task=task,
            agent_name=self.agent_name,
            COMMANDS=command_list,
            context=context,
            command_list=command_list,
            date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            **kwargs,
        )
        tokens = len(self.agent.memories.nlp(formatted_prompt))
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
            learning_file = self.agent.memories.read_file(file_path=learn_file)
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
                    self.websearch_agent(task=task, depth=websearch_depth)
                )
            else:
                self.websearch_agent(task=task, depth=websearch_depth)
        try:
            self.response = self.agent.instruct(formatted_prompt, tokens=tokens)
        except:
            if context_results > 0:
                context_results = context_results - 1
            if context_results == 0:
                print("Warning: No context injected due to max tokens.")
            return self.run(
                task=task,
                prompt=prompt,
                context_results=context_results,
                async_exec=async_exec,
                **kwargs,
            )

        # Handle commands if the prompt contains the {COMMANDS} placeholder
        # We handle command injection that DOESN'T allow command execution by using {command_list} in the prompt
        if "{COMMANDS}" in unformatted_prompt:
            execution_response = self.execution_agent(
                execution_response=self.response,
                task=task,
                context_results=context_results,
                **kwargs,
            )
            return_response = ""
            try:
                self.response = json.loads(self.response)
                if "response" in self.response:
                    return_response = self.response["response"]
                if "commands" in self.response:
                    if self.response["commands"] != {}:
                        return_response += (
                            f"\n\nCommands Executed:\n{self.response['commands']}"
                        )
                if execution_response:
                    return_response += (
                        f"\n\nCommand Execution Response:\n{execution_response}"
                    )
            except:
                return_response = self.response
            self.response = return_response
        print(f"Response: {self.response}")
        if self.response != "" and self.response != None:
            try:
                self.agent.memories.store_result(task, self.response)
            except:
                pass
            self.agent.log_interaction("USER", task)
            self.agent.log_interaction(self.agent_name, self.response)
        return self.response

    def smart_instruct(
        self,
        task: str = "Write a tweet about AI.",
        shots: int = 3,
        async_exec: bool = False,
        learn_file: str = "",
        objective: str = None,
        **kwargs,
    ):
        answers = []
        # Do multi shots of prompt to get N different answers to be validated
        answers.append(
            self.run(
                task=task,
                prompt="SmartInstruct-StepByStep"
                if objective == None
                else "SmartTask-StepByStep",
                context_results=6,
                websearch=True,
                websearch_depth=3,
                shots=shots,
                async_exec=async_exec,
                learn_file=learn_file,
                objective=objective,
                **kwargs,
            )
        )
        if shots > 1:
            for i in range(shots - 1):
                answers.append(
                    self.run(
                        task=task,
                        prompt="SmartInstruct-StepByStep"
                        if objective == None
                        else "SmartTask-StepByStep",
                        context_results=6,
                        shots=shots,
                        objective=objective,
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
            prompt="SmartInstruct-CleanResponse"
            if objective == None
            else "SmartTask-CleanResponse",
            resolver_response=resolver,
            execution_response=execution_response,
            objective=objective,
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

    # Worker Sub-Agents
    def validation_agent(self, task, execution_response, context_results, **kwargs):
        try:
            pattern = regex.compile(r"\{(?:[^{}]|(?R))*\}")
            cleaned_json = pattern.findall(execution_response)
            if len(cleaned_json) == 0:
                return False
            if isinstance(cleaned_json, list):
                cleaned_json = cleaned_json[0]
            response = json.loads(cleaned_json)
            return response
        except:
            print("INVALID JSON RESPONSE")
            print(execution_response)
            print("... Trying again.")
            if context_results != 0:
                context_results = context_results - 1
            else:
                context_results = 0
            execution_response = self.run(
                task=task, context_results=context_results, **kwargs
            )
            return self.validation_agent(
                task, execution_response, context_results, **kwargs
            )

    def revalidation_agent(
        self,
        task,
        command_name,
        command_args,
        command_output,
        context_results,
        **kwargs,
    ):
        print(
            f"Command {command_name} did not execute as expected with args {command_args}. Trying again.."
        )
        revalidate = self.run(
            task=task,
            prompt="ValidationFailed",
            command_name=command_name,
            command_args=command_args,
            command_output=command_output,
            **kwargs,
        )
        return self.execution_agent(revalidate, task, context_results, **kwargs)

    def execution_agent(self, execution_response, task, context_results, **kwargs):
        validated_response = self.validation_agent(
            task, execution_response, context_results, **kwargs
        )
        try:
            for command_name, command_args in validated_response["commands"].items():
                # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                if command_name is not None:
                    for available_command in self.agent.available_commands:
                        if command_name in [
                            available_command["friendly_name"],
                            available_command["name"],
                        ]:
                            command_name = available_command["name"]
                            break
                    try:
                        command_output = self.agent.execute(command_name, command_args)
                        print("Running Command Execution Validation...")
                        validate_command = self.run(
                            task=task,
                            prompt="Validation",
                            command_name=command_name,
                            command_args=command_args,
                            command_output=command_output,
                            **kwargs,
                        )
                    except:
                        return self.revalidation_agent(
                            task, command_name, command_args, command_output, **kwargs
                        )

                    if validate_command.startswith("Y"):
                        print(
                            f"Command {command_name} executed successfully with args {command_args}."
                        )
                        response = f"\nExecuted Command:{command_name} with args {command_args}.\nCommand Output: {command_output}\n"
                        return response
                    else:
                        revalidate = self.run(
                            task=task,
                            prompt="ValidationFailed",
                            command_name=command_name,
                            command_args=command_args,
                            command_output=command_output,
                            **kwargs,
                        )
                        return self.execution_agent(
                            execution_response, task, context_results, **kwargs
                        )
                else:
                    if command_name == "None.":
                        return "\nNo commands were executed.\n"
                    else:
                        return f"\Command not recognized: {command_name} ."
        except:
            print("\nERROR IN EXECUTION_AGENT, validated_response:\n")
            print(validated_response)
            return "\nNo commands were executed.\n"

    async def websearch_agent(
        self, task: str = "What are the latest breakthroughs in AI?", depth: int = 3
    ):
        async def resursive_browsing(task, links):
            try:
                words = links.split()
                links = [
                    word for word in words if urlparse(word).scheme in ["http", "https"]
                ]
            except:
                links = links
            if links is not None:
                for link in links:
                    if "href" in link:
                        url = link["href"]
                    else:
                        url = link
                    url = re.sub(r"^.*?(http)", r"http", url)
                    # Check if url is an actual url
                    if url.startswith("http"):
                        print(f"Scraping: {url}")
                        if url not in self.browsed_links:
                            self.browsed_links.append(url)
                            (
                                collected_data,
                                link_list,
                            ) = await self.agent.memories.read_website(url)
                            if link_list is not None:
                                if len(link_list) > 0:
                                    if len(link_list) > 5:
                                        link_list = link_list[:3]
                                    try:
                                        pick_a_link = self.run(
                                            task=task,
                                            prompt="Pick-a-Link",
                                            links=link_list,
                                        )
                                        if not pick_a_link.startswith("None"):
                                            await resursive_browsing(task, pick_a_link)
                                    except:
                                        print(f"Issues reading {url}. Moving on...")

        results = self.run(task=task, prompt="WebSearch")
        results = results.split("\n")
        for result in results:
            search_string = result.lstrip("0123456789. ")
            links = ddg(search_string, max_results=depth)
            if links is not None:
                await resursive_browsing(task, links)
