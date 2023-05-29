import re
import os
import asyncio
import regex
import json
import time
import spacy
from datetime import datetime
from Agent import Agent
from Prompts import Prompts
from extensions.searxng import searxng
from urllib.parse import urlparse
import logging


class AGiXT:
    def __init__(self, agent_name: str = "AGiXT"):
        self.agent_name = agent_name
        self.agent = Agent(self.agent_name)
        self.agent_commands = self.agent.get_commands_string()
        self.stop_running_event = None
        self.browsed_links = []
        self.failures = 0
        self.nlp = None

    def load_spacy_model(self):
        if not self.nlp:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except:
                spacy.cli.download("en_core_web_sm")
                self.nlp = spacy.load("en_core_web_sm")
        self.nlp.max_length = 99999999999999999999999

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

    def get_step_response(self, chain_name, step_number):
        try:
            with open(os.path.join("chains", f"{chain_name}_responses.json"), "r") as f:
                responses = json.load(f)
            return responses.get(str(step_number))
        except:
            return ""

    def format_prompt(
        self,
        task: str = "",
        top_results: int = 5,
        prompt="",
        chain_name="",
        step_number=0,
        **kwargs,
    ):
        cp = Prompts()
        if prompt == "":
            prompt = task
        else:
            try:
                prompt = cp.get_prompt(prompt_name=prompt, model=self.agent.AI_MODEL)
            except:
                prompt = prompt
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
            COMMANDS=self.agent_commands,
            context=context,
            command_list=command_list,
            date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            **kwargs,
        )
        if "{STEP" in formatted_prompt:
            # get the response from the step number
            step_response = self.get_step_response(
                chain_name=chain_name, step_number=step_number
            )
            # replace the {STEPx} with the response
            formatted_prompt = formatted_prompt.replace(
                f"{{STEP{step_number}}}", step_response
            )
        if not self.nlp:
            self.load_spacy_model()
        tokens = len(self.nlp(formatted_prompt))
        logging.info(f"FORMATTED PROMPT: {formatted_prompt}")
        return formatted_prompt, prompt, tokens

    def run(
        self,
        task: str = "",
        prompt: str = "",
        context_results: int = 5,
        websearch: bool = False,
        websearch_depth: int = 3,
        async_exec: bool = False,
        learn_file: str = "",
        chain_name: str = "",
        step_number: int = 0,
        **kwargs,
    ):
        logging.info(f"KWARGS: {kwargs}")
        if learn_file != "":
            learning_file = self.agent.memories.mem_read_file(file_path=learn_file)
            if learning_file == False:
                return "Failed to read file."
        formatted_prompt, unformatted_prompt, tokens = self.format_prompt(
            task=task,
            top_results=context_results,
            prompt=prompt,
            chain_name=chain_name,
            step_number=step_number,
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
        except Exception as e:
            logging.info(f"Error: {e}")
            logging.info(f"PROMPT CONTENT: {formatted_prompt}")
            logging.info(f"TOKENS: {tokens}")
            self.failures += 1
            if self.failures == 5:
                self.failures == 0
                logging.info("Failed to get a response 5 times in a row.")
                return None
            logging.info(f"Retrying in 10 seconds...")
            time.sleep(10)
            if context_results > 0:
                context_results = context_results - 1
            self.response = self.run(
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
        logging.info(f"Response: {self.response}")
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
            logging.info("INVALID JSON RESPONSE")
            logging.info(execution_response)
            logging.info("... Trying again.")
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
        logging.info(
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
                            try:
                                # Check if the command is a valid command in the self.avent.available_commands list
                                command_output = self.agent.execute(
                                    command_name, command_args
                                )
                                logging.info("Running Command Execution Validation...")
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
                                    task,
                                    command_name,
                                    command_args,
                                    command_output,
                                    **kwargs,
                                )

                            logging.info(
                                f"Command {command_name} executed successfully with args {command_args}."
                            )
                            response = f"\nExecuted Command:{command_name} with args {command_args}.\nCommand Output: {command_output}\n"
                            return response

                else:
                    if command_name == "None.":
                        return "\nNo commands were executed.\n"
                    else:
                        return f"\Command not recognized: {command_name} ."
        except:
            logging.info("\nERROR IN EXECUTION_AGENT, validated_response:\n")
            logging.info(validated_response)
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
                        try:
                            url = link["href"]
                        except:
                            url = link
                    else:
                        url = link
                    url = re.sub(r"^.*?(http)", r"http", url)
                    # Check if url is an actual url
                    if url.startswith("http"):
                        logging.info(f"Scraping: {url}")
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
                                        logging.info(
                                            f"Issues reading {url}. Moving on..."
                                        )

        results = self.run(task=task, prompt="WebSearch")
        results = results.split("\n")
        for result in results:
            search_string = result.lstrip("0123456789. ")
            try:
                searx_server = self.agent.PROVIDER_SETTINGS["SEARXNG_INSTANCE_URL"]
            except:
                searx_server = ""
            try:
                links = searxng(SEARXNG_INSTANCE_URL=searx_server).search(search_string)
                if len(links) > depth:
                    links = links[:depth]
            except:
                links = None
            if links is not None:
                await resursive_browsing(task, links)
