import re
import os
import regex
import json
import time
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

db_connected = True if os.getenv("DB_CONNECTED", "false").lower() == "true" else False
if db_connected:
    from db.Agent import Agent
    from db.Prompts import Prompts
    from db.Chain import Chain
    from db.History import log_interaction
else:
    from fb.Agent import Agent
    from fb.Prompts import Prompts
    from fb.Chain import Chain
    from fb.History import log_interaction

from Embedding import get_tokens
from concurrent.futures import Future
from agixtsdk import AGiXTSDK
from Websearch import Websearch

ApiClient = AGiXTSDK(
    base_uri="http://localhost:7437", api_key=os.getenv("AGIXT_API_KEY")
)
chain = Chain()
cp = Prompts()


class Interactions:
    def __init__(self, agent_name: str = ""):
        if agent_name != "":
            self.agent_name = agent_name
            self.agent = Agent(self.agent_name)
            self.agent_commands = self.agent.get_commands_string()
            self.memories = self.agent.get_memories()
            self.websearch = Websearch(agent=self.agent, memories=self.memories)
        else:
            self.agent_name = ""
            self.agent = None
            self.agent_commands = ""
            self.memories = None
        self.stop_running_event = None
        self.browsed_links = []
        self.failures = 0

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

    async def format_prompt(
        self,
        user_input: str = "",
        top_results: int = 5,
        prompt="",
        chain_name="",
        step_number=0,
        **kwargs,
    ):
        if prompt == "":
            prompt = user_input
        else:
            try:
                prompt = cp.get_prompt(
                    prompt_name=prompt,
                    prompt_category=self.agent.AGENT_CONFIG["settings"]["AI_MODEL"],
                )
            except:
                prompt = prompt
        logging.info(f"CONTEXT RESULTS: {top_results}")
        if top_results == 0:
            context = ""
        else:
            # try:
            context = await self.memories.context_agent(
                query=user_input, top_results_num=top_results
            )
            # except:
            # context = ""
        command_list = self.agent.get_commands_string()
        if chain_name != "":
            try:
                for arg, value in kwargs.items():
                    if "{STEP" in value:
                        # get the response from the step number
                        step_response = chain.get_step_response(
                            chain_name=chain_name, step_number=step_number
                        )
                        # replace the {STEPx} with the response
                        value = value.replace(f"{{STEP{step_number}}}", step_response)
                        kwargs[arg] = value
            except:
                logging.info("No args to replace.")
            if "{STEP" in prompt:
                step_response = chain.get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                prompt = prompt.replace(f"{{STEP{step_number}}}", step_response)
            if "{STEP" in user_input:
                step_response = chain.get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                user_input = user_input.replace(f"{{STEP{step_number}}}", step_response)
        try:
            working_directory = self.agent.AGENT_CONFIG["settings"]["WORKING_DIRECTORY"]
        except:
            working_directory = "./WORKSPACE"
        if "helper_agent_name" not in kwargs:
            if "helper_agent_name" in self.agent.AGENT_CONFIG["settings"]:
                helper_agent_name = self.agent.AGENT_CONFIG["settings"][
                    "helper_agent_name"
                ]
            else:
                helper_agent_name = self.agent_name
        formatted_prompt = self.custom_format(
            string=prompt,
            user_input=user_input,
            agent_name=self.agent_name,
            COMMANDS=self.agent_commands,
            context=context,
            command_list=command_list,
            date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            working_directory=working_directory,
            helper_agent_name=helper_agent_name,
            **kwargs,
        )

        tokens = get_tokens(formatted_prompt)
        logging.info(f"FORMATTED PROMPT: {formatted_prompt}")
        return formatted_prompt, prompt, tokens

    async def run(
        self,
        user_input: str = "",
        prompt: str = "",
        context_results: int = 5,
        websearch: bool = False,
        websearch_depth: int = 3,
        chain_name: str = "",
        step_number: int = 0,
        shots: int = 1,
        disable_memory: bool = False,
        conversation_name: str = "",
        browse_links: bool = False,
        **kwargs,
    ):
        shots = int(shots)
        disable_memory = True if str(disable_memory).lower() != "true" else False
        browse_links = True if str(browse_links).lower() == "true" else False
        if conversation_name != "":
            conversation_name = f"{self.agent_name} History"
        if "WEBSEARCH_TIMEOUT" in self.agent.PROVIDER_SETTINGS:
            try:
                websearch_timeout = int(
                    self.agent.PROVIDER_SETTINGS["WEBSEARCH_TIMEOUT"]
                )
            except:
                websearch_timeout = 0
        else:
            websearch_timeout = 0
        if browse_links != False:
            links = re.findall(r"(?P<url>https?://[^\s]+)", user_input)
            if links is not None and len(links) > 0:
                for link in links:
                    if link not in self.websearch.browsed_links:
                        logging.info(f"Browsing link: {link}")
                        self.websearch.browsed_links.append(link)
                        text_content, link_list = await self.memories.read_website(
                            url=link
                        )
                        if link_list is not None and len(link_list) > 0:
                            i = 0
                            for sublink in link_list:
                                if sublink[1] not in self.websearch.browsed_links:
                                    logging.info(f"Browsing link: {sublink[1]}")
                                    if i <= 10:
                                        (
                                            text_content,
                                            link_list,
                                        ) = await self.memories.read_website(
                                            url=sublink[1]
                                        )
                                        i = i + 1
        if websearch:
            if user_input == "":
                if "primary_objective" in kwargs and "task" in kwargs:
                    search_string = f"Primary Objective: {kwargs['primary_objective']}\n\nTask: {kwargs['task']}"
                else:
                    search_string = ""
            else:
                search_string = user_input
            if search_string != "":
                await self.websearch.websearch_agent(
                    user_input=search_string,
                    depth=websearch_depth,
                    timeout=websearch_timeout,
                )
        formatted_prompt, unformatted_prompt, tokens = await self.format_prompt(
            user_input=user_input,
            top_results=int(context_results),
            prompt=prompt,
            chain_name=chain_name,
            step_number=step_number,
            **kwargs,
        )
        try:
            # Workaround for non-threaded providers
            run_response = await self.agent.instruct(formatted_prompt, tokens=tokens)
            self.response = (
                run_response.result()
                if isinstance(run_response, Future)
                else run_response
            )
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
            self.response = ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name=prompt,
                prompt_args={
                    "chain_name": chain_name,
                    "step_number": step_number,
                    "shots": shots,
                    "disable_memory": disable_memory,
                    "user_input": user_input,
                    "context_results": context_results,
                    "conversation_name": conversation_name,
                    **kwargs,
                },
            )

        # Handle commands if the prompt contains the {COMMANDS} placeholder
        # We handle command injection that DOESN'T allow command execution by using {command_list} in the prompt
        if "{COMMANDS}" in unformatted_prompt:
            execution_response = await self.execution_agent(
                execution_response=self.response,
                user_input=user_input,
                context_results=context_results,
                **kwargs,
            )
            return_response = ""
            if "AUTONOMOUS_EXECUTION" in self.agent.AGENT_CONFIG["settings"]:
                autonomous = (
                    True
                    if self.agent.AGENT_CONFIG["settings"]["AUTONOMOUS_EXECUTION"]
                    == True
                    else False
                )
            else:
                autonomous = False

            if autonomous == True:
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
            else:
                return_response = f"{self.response}\n\n{execution_response}"
            self.response = return_response
        logging.info(f"Response: {self.response}")
        if self.response != "" and self.response != None:
            if disable_memory != True:
                try:
                    await self.memories.store_result(
                        input=user_input, result=self.response
                    )
                except:
                    pass
            if user_input != "":
                log_interaction(
                    agent_name=self.agent_name,
                    conversation_name=conversation_name,
                    role="USER",
                    message=user_input,
                )
            else:
                log_interaction(
                    agent_name=self.agent_name,
                    conversation_name=conversation_name,
                    role="USER",
                    message=formatted_prompt,
                )
            log_interaction(
                agent_name=self.agent_name,
                conversation_name=conversation_name,
                role=self.agent_name,
                message=self.response,
            )

        if shots > 1:
            responses = [self.response]
            for shot in range(shots - 1):
                shot_response = ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name=prompt,
                    prompt_args={
                        "chain_name": chain_name,
                        "step_number": step_number,
                        "user_input": user_input,
                        "context_results": context_results,
                        "conversation_name": conversation_name,
                        **kwargs,
                    },
                )
                time.sleep(1)
                responses.append(shot_response)
            return "\n".join(
                [
                    f"Response {shot + 1}:\n{response}"
                    for shot, response in enumerate(responses)
                ]
            )
        return self.response

    # Worker Sub-Agents
    async def validation_agent(
        self, user_input, execution_response, context_results, **kwargs
    ):
        try:
            pattern = regex.compile(r"\{(?:[^{}]|(?R))*\}")
            cleaned_json = pattern.findall(execution_response)
            if len(cleaned_json) == 0:
                return {}
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
            execution_response = ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="JSONFormatter",
                prompt_args={
                    "user_input": user_input,
                    "context_results": context_results,
                    **kwargs,
                },
            )
            return await self.validation_agent(
                user_input=user_input,
                execution_response=execution_response,
                context_results=context_results,
                **kwargs,
            )

    def create_command_suggestion_chain(self, agent_name, command_name, command_args):
        chains = ApiClient.get_chains()
        chain_name = f"{agent_name} Command Suggestions"
        if chain_name in chains:
            step = (
                int(ApiClient.get_chain(chain_name=chain_name)["steps"][-1]["step"]) + 1
            )
        else:
            ApiClient.add_chain(chain_name=chain_name)
            step = 1
        ApiClient.add_step(
            chain_name=chain_name,
            agent_name=agent_name,
            step_number=step,
            prompt_type="Command",
            prompt={
                "command_name": command_name,
                **command_args,
            },
        )
        return f"The command has been added to a chain called '{agent_name} Command Suggestions' for you to review and execute manually."

    async def execution_agent(
        self, execution_response, user_input, context_results, **kwargs
    ):
        validated_response = await self.validation_agent(
            user_input=user_input,
            execution_response=execution_response,
            context_results=context_results,
            **kwargs,
        )
        if "commands" in validated_response:
            for command_name, command_args in validated_response["commands"].items():
                # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                if command_name is not None:
                    for available_command in self.agent.available_commands:
                        if command_name == available_command["friendly_name"]:
                            # Check if the command is a valid command in the self.avent.available_commands list
                            try:
                                if bool(self.agent.AUTONOMOUS_EXECUTION) == True:
                                    command_output = await self.agent.execute(
                                        command_name=command_name,
                                        command_args=command_args,
                                    )
                                else:
                                    command_output = (
                                        self.create_command_suggestion_chain(
                                            agent_name=self.agent_name,
                                            command_name=command_name,
                                            command_args=command_args,
                                        )
                                    )
                            except Exception as e:
                                logging.info("Command validation failed, retrying...")
                                validate_command = ApiClient.prompt_agent(
                                    agent_name=self.agent_name,
                                    prompt_name="ValidationFailed",
                                    prompt_args={
                                        "command_name": command_name,
                                        "command_args": command_args,
                                        "command_output": e,
                                        "user_input": user_input,
                                        "context_results": context_results,
                                        **kwargs,
                                    },
                                )
                                return await self.execution_agent(
                                    execution_response=validate_command,
                                    user_input=user_input,
                                    context_results=context_results,
                                    **kwargs,
                                )
                            logging.info(
                                f"Command {command_name} executed successfully with args {command_args}. Command Output: {command_output}"
                            )
                            response = f"\nExecuted Command:{command_name} with args {command_args}.\nCommand Output: {command_output}\n"
                            return response
                else:
                    if command_name == "None.":
                        return "\nNo commands were executed.\n"
                    else:
                        return f"\Command not recognized: `{command_name}`."
        else:
            return "\nNo commands were executed.\n"
